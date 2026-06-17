"""Envoi de notifications push via le service Expo Push.

Utilise uniquement la librairie standard (urllib) pour ne pas ajouter de
dependance. L'envoi est tolerant aux pannes : toute erreur est journalisee
mais ne doit jamais interrompre le flux metier (assignation, annulation...).
"""
import json
import logging
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = 'https://exp.host/--/api/v2/push/send'
_TIMEOUT_SECONDS = 10
# Expo limite a 100 messages par requete.
_MAX_BATCH = 100


def _looks_like_expo_token(token):
    return isinstance(token, str) and token.startswith(('ExponentPushToken[', 'ExpoPushToken['))


def send_expo_push(tokens, title, body, data=None, priority='high'):
    """Envoie une notification push a une liste de jetons Expo.

    Args:
        tokens: iterable de jetons (str).
        title: titre de la notification.
        body: corps du message.
        data: dict optionnel transmis a l'app (ex: {'mission_id': 12}).
        priority: 'default' ou 'high'.

    Returns:
        bool: True si au moins un lot a ete transmis sans erreur reseau.
    """
    valid_tokens = [t for t in (tokens or []) if _looks_like_expo_token(t)]
    if not valid_tokens:
        return False

    sent_ok = False
    for start in range(0, len(valid_tokens), _MAX_BATCH):
        batch = valid_tokens[start:start + _MAX_BATCH]
        messages = [
            {
                'to': token,
                'title': title,
                'body': body,
                'data': data or {},
                'sound': 'default',
                'priority': priority,
                'channelId': 'default',
            }
            for token in batch
        ]

        payload = json.dumps(messages).encode('utf-8')
        request = urllib.request.Request(
            EXPO_PUSH_URL,
            data=payload,
            headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Accept-Encoding': 'gzip, deflate',
            },
            method='POST',
        )

        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
                raw = response.read().decode('utf-8')
                result = json.loads(raw)
                sent_ok = True
                _log_receipts(result, batch)
        except urllib.error.URLError as exc:
            logger.warning("Echec envoi push Expo (reseau): %s", exc)
        except Exception as exc:  # pragma: no cover - garde-fou
            logger.warning("Echec envoi push Expo: %s", exc)

    return sent_ok


def _log_receipts(result, batch):
    """Journalise les jetons rejetes (ex: DeviceNotRegistered) pour nettoyage."""
    receipts = result.get('data') if isinstance(result, dict) else None
    if not isinstance(receipts, list):
        return
    for token, receipt in zip(batch, receipts):
        if isinstance(receipt, dict) and receipt.get('status') == 'error':
            error_code = (receipt.get('details') or {}).get('error')
            logger.info("Push rejete pour %s : %s", token[:30], error_code)
            if error_code == 'DeviceNotRegistered':
                _deactivate_token(token)


def _deactivate_token(token):
    """Desactive un jeton devenu invalide cote Expo."""
    try:
        from apps.fleet.models import DriverPushToken
        DriverPushToken.objects.filter(token=token).update(is_active=False)
    except Exception:
        pass
