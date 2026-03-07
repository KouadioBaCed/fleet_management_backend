from rest_framework import generics, status, viewsets
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .serializers import (
    UserSerializer,
    UserCreateSerializer,
    UserProfileSerializer,
    ChangePasswordSerializer,
    CustomTokenObtainPairSerializer,
    RegisterOrganizationSerializer,
    OrganizationSerializer,
    UserPreferencesSerializer,
    UserListSerializer,
    AdminUserCreateSerializer,
    AdminUserUpdateSerializer,
    UserRoleUpdateSerializer,
    UserStatusUpdateSerializer,
    SignupInitiateSerializer,
    SignupCompleteSerializer,
    VerifyTokenSerializer,
)
from .models import Organization, UserPreferences, EmailVerificationToken
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from .permissions import IsOrganizationAdmin, IsOrganizationMember

User = get_user_model()


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Vue personnalisée pour l'obtention du token JWT

    Workflow:
    1. Saisir email/mot de passe
    2. Validation des identifiants
    3. Vérification organisation active
    4. Génération et stockage token JWT
    5. Retour des infos user + organization + tokens
    """
    serializer_class = CustomTokenObtainPairSerializer


class RegisterOrganizationView(generics.CreateAPIView):
    """
    Vue pour l'enregistrement d'une nouvelle organisation avec son administrateur

    Cette vue permet de créer:
    1. Une nouvelle organisation
    2. Un utilisateur admin associé à cette organisation
    3. Retourne les tokens JWT pour connexion automatique
    """
    permission_classes = [AllowAny]
    serializer_class = RegisterOrganizationSerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()

        user = result['user']
        organization = result['organization']

        # Générer les tokens JWT
        refresh = RefreshToken.for_user(user)

        return Response({
            'message': 'Organisation créée avec succès',
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'full_name': user.get_full_name(),
                'role': user.role,
            },
            'organization': {
                'id': str(organization.id),
                'name': organization.name,
                'slug': organization.slug,
            }
        }, status=status.HTTP_201_CREATED)


class RegisterView(generics.CreateAPIView):
    """Vue pour l'enregistrement d'un nouvel utilisateur dans une organisation existante"""
    queryset = User.objects.all()
    permission_classes = [AllowAny]
    serializer_class = UserCreateSerializer


@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def profile_view(request):
    """Vue pour obtenir et mettre à jour le profil de l'utilisateur"""
    if request.method == 'GET':
        serializer = UserProfileSerializer(request.user, context={'request': request})
        return Response(serializer.data)

    elif request.method in ['PUT', 'PATCH']:
        serializer = UserProfileSerializer(
            request.user,
            data=request.data,
            partial=request.method == 'PATCH',
            context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password_view(request):
    """Vue pour changer le mot de passe de l'utilisateur"""
    serializer = ChangePasswordSerializer(data=request.data)

    if serializer.is_valid():
        user = request.user

        # Vérifier l'ancien mot de passe
        if not user.check_password(serializer.validated_data['old_password']):
            return Response(
                {"old_password": ["Mot de passe incorrect."]},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Définir le nouveau mot de passe
        user.set_password(serializer.validated_data['new_password'])
        user.save()

        return Response(
            {"message": "Mot de passe changé avec succès."},
            status=status.HTTP_200_OK
        )

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    """
    Vue pour la déconnexion de l'utilisateur

    Workflow:
    1. Clic sur déconnexion (frontend)
    2. Envoi du refresh token au backend
    3. Blacklist du refresh token (invalidation côté serveur)
    4. Suppression token local (frontend)
    5. Redirection vers Login (frontend)
    """
    try:
        refresh_token = request.data.get('refresh')

        if not refresh_token:
            return Response(
                {"detail": "Le token de rafraîchissement est requis."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Blacklister le refresh token
        token = RefreshToken(refresh_token)
        token.blacklist()

        return Response(
            {"message": "Déconnexion réussie."},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"detail": "Erreur lors de la déconnexion.", "error": str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def delete_account_view(request):
    """
    Vue pour supprimer définitivement le compte de l'utilisateur.

    Workflow:
    1. L'utilisateur confirme la suppression avec son mot de passe
    2. Vérification du mot de passe
    3. Suppression du compte et des données associées
    4. Déconnexion automatique

    POST /api/auth/delete-account/
    Body: { "password": "..." }
    """
    user = request.user
    password = request.data.get('password')

    if not password:
        return Response(
            {"error": "Le mot de passe est requis pour confirmer la suppression."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Vérifier le mot de passe
    if not user.check_password(password):
        return Response(
            {"error": "Mot de passe incorrect."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Vérifier si l'utilisateur est le seul admin de son organisation
    if user.role == 'admin' and user.organization:
        admin_count = User.objects.filter(
            organization=user.organization,
            role='admin',
            is_active=True
        ).count()

        if admin_count <= 1:
            return Response({
                "error": "Vous êtes le seul administrateur de votre organisation. "
                         "Veuillez nommer un autre administrateur avant de supprimer votre compte, "
                         "ou supprimez l'organisation entière."
            }, status=status.HTTP_400_BAD_REQUEST)

    # Stocker le nom pour le message
    user_name = user.get_full_name() or user.username

    # Supprimer le compte
    user.delete()

    return Response({
        "message": f"Le compte de '{user_name}' a été supprimé définitivement."
    }, status=status.HTTP_200_OK)


@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def preferences_view(request):
    """
    Vue pour obtenir et mettre à jour les préférences utilisateur

    GET: Retourne les préférences actuelles (crée des préférences par défaut si elles n'existent pas)
    PUT/PATCH: Met à jour les préférences
    """
    # Récupérer ou créer les préférences
    preferences, created = UserPreferences.objects.get_or_create(user=request.user)

    if request.method == 'GET':
        serializer = UserPreferencesSerializer(preferences)
        return Response(serializer.data)

    elif request.method in ['PUT', 'PATCH']:
        serializer = UserPreferencesSerializer(
            preferences,
            data=request.data,
            partial=request.method == 'PATCH'
        )
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': 'Préférences mises à jour avec succès',
                'preferences': serializer.data
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ============================================
# Inscription par email
# ============================================

@api_view(['POST'])
@permission_classes([AllowAny])
def signup_initiate_view(request):
    """
    Initie le processus d'inscription en envoyant un email de vérification.

    POST /api/auth/signup/initiate/
    Body: {
        "email": "user@example.com",
        "first_name": "John",
        "last_name": "Doe",
        "organization_name": "Ma Société"
    }
    """
    serializer = SignupInitiateSerializer(data=request.data)

    if serializer.is_valid():
        email = serializer.validated_data['email']
        first_name = serializer.validated_data['first_name']
        last_name = serializer.validated_data['last_name']
        organization_name = serializer.validated_data['organization_name']

        # Supprimer les anciens tokens non utilisés pour cet email
        EmailVerificationToken.objects.filter(email=email, is_used=False).delete()

        # Créer un nouveau token
        token = EmailVerificationToken.objects.create(
            email=email,
            token=EmailVerificationToken.generate_token(),
            first_name=first_name,
            last_name=last_name,
            organization_name=organization_name,
            expires_at=timezone.now() + timedelta(hours=24),
        )

        # Construire l'URL de vérification
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
        verification_url = f"{frontend_url}/verify-email?token={token.token}"

        # Envoyer l'email
        subject = 'YaswaCar - Vérifiez votre adresse email'
        html_message = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #6A8A82; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
                .header h1 {{ color: white; margin: 0; }}
                .content {{ background-color: #f9f9f9; padding: 30px; border-radius: 0 0 8px 8px; }}
                .button {{ display: inline-block; background-color: #6A8A82; color: white; padding: 12px 30px; text-decoration: none; border-radius: 6px; margin: 20px 0; }}
                .button:hover {{ background-color: #5a7a72; }}
                .footer {{ text-align: center; margin-top: 20px; color: #888; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🚗 YaswaCar</h1>
                </div>
                <div class="content">
                    <h2>Bonjour {first_name} {last_name},</h2>
                    <p>Merci de vous inscrire sur YaswaCar pour votre organisation <strong>{organization_name}</strong>.</p>
                    <p>Pour activer votre compte et créer votre mot de passe, cliquez sur le bouton ci-dessous :</p>
                    <p style="text-align: center;">
                        <a href="{verification_url}" class="button" style="color: white;">Activer mon compte</a>
                    </p>
                    <p>Ou copiez ce lien dans votre navigateur :</p>
                    <p style="word-break: break-all; background: #eee; padding: 10px; border-radius: 4px; font-size: 12px;">
                        {verification_url}
                    </p>
                    <p><strong>Ce lien expire dans 24 heures.</strong></p>
                    <p>Si vous n'avez pas demandé cette inscription, ignorez cet email.</p>
                </div>
                <div class="footer">
                    <p>© 2024 YaswaCar - Gestion de Flotte</p>
                </div>
            </div>
        </body>
        </html>
        """
        plain_message = strip_tags(html_message)

        try:
            send_mail(
                subject=subject,
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                html_message=html_message,
                fail_silently=False,
            )
        except Exception as e:
            # Log l'erreur mais ne pas exposer les détails au client
            print(f"Erreur d'envoi email: {e}")
            return Response({
                'error': "Erreur lors de l'envoi de l'email. Veuillez réessayer."
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            'message': 'Email de vérification envoyé avec succès.',
            'email': email,
        }, status=status.HTTP_200_OK)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def signup_verify_token_view(request):
    """
    Vérifie si un token est valide et retourne les informations associées.

    POST /api/auth/signup/verify-token/
    Body: { "token": "..." }
    """
    serializer = VerifyTokenSerializer(data=request.data)

    if serializer.is_valid():
        token_obj = serializer.token_obj
        return Response({
            'valid': True,
            'email': token_obj.email,
            'first_name': token_obj.first_name,
            'last_name': token_obj.last_name,
            'organization_name': token_obj.organization_name,
        }, status=status.HTTP_200_OK)

    return Response({
        'valid': False,
        'errors': serializer.errors,
    }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
@transaction.atomic
def signup_complete_view(request):
    """
    Complète l'inscription après vérification de l'email.

    POST /api/auth/signup/complete/
    Body: {
        "token": "...",
        "username": "johndoe",
        "password": "...",
        "password_confirm": "...",
        "phone_number": "+243..."
    }
    """
    serializer = SignupCompleteSerializer(data=request.data)

    if serializer.is_valid():
        result = serializer.save()
        user = result['user']
        organization = result['organization']

        # Générer les tokens JWT
        refresh = RefreshToken.for_user(user)

        return Response({
            'message': 'Compte créé avec succès !',
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'full_name': user.get_full_name(),
                'role': user.role,
            },
            'organization': {
                'id': str(organization.id),
                'name': organization.name,
                'slug': organization.slug,
            }
        }, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ============================================
# Gestion des utilisateurs (Admin uniquement)
# ============================================

class UserManagementViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour la gestion des utilisateurs par les administrateurs.

    Fonctionnalités:
    - Liste des utilisateurs de l'organisation
    - Création de comptes (admin, superviseur, driver)
    - Modification des utilisateurs
    - Changement de rôle
    - Activation/Désactivation de comptes
    - Suppression de comptes

    Permissions:
    - Toutes les actions nécessitent d'être admin de l'organisation
    """
    permission_classes = [IsAuthenticated, IsOrganizationAdmin]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['username', 'email', 'first_name', 'last_name', 'phone_number']
    ordering_fields = ['date_joined', 'last_login', 'first_name', 'last_name', 'role']
    ordering = ['-date_joined']
    filterset_fields = ['role', 'is_active', 'is_active_duty']

    def get_queryset(self):
        """Retourne uniquement les utilisateurs de l'organisation de l'admin"""
        return User.objects.filter(
            organization=self.request.user.organization
        ).select_related('organization')

    def get_serializer_class(self):
        """Retourne le serializer approprié selon l'action"""
        if self.action == 'list':
            return UserListSerializer
        elif self.action == 'create':
            return AdminUserCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return AdminUserUpdateSerializer
        elif self.action == 'change_role':
            return UserRoleUpdateSerializer
        elif self.action == 'toggle_status':
            return UserStatusUpdateSerializer
        return UserListSerializer

    def perform_create(self, serializer):
        """Associe automatiquement l'utilisateur créé à l'organisation de l'admin"""
        serializer.save(organization=self.request.user.organization)

    def create(self, request, *args, **kwargs):
        """Crée un nouvel utilisateur dans l'organisation"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        user = serializer.instance
        response_serializer = UserListSerializer(user)

        return Response({
            'message': f"Utilisateur '{user.get_full_name() or user.username}' créé avec succès.",
            'user': response_serializer.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """Met à jour un utilisateur"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()

        # Empêcher un admin de se désactiver lui-même
        if instance == request.user and request.data.get('is_active') is False:
            return Response({
                'error': "Vous ne pouvez pas désactiver votre propre compte."
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        response_serializer = UserListSerializer(instance)
        return Response({
            'message': f"Utilisateur '{instance.get_full_name() or instance.username}' mis à jour.",
            'user': response_serializer.data
        })

    def destroy(self, request, *args, **kwargs):
        """Supprime un utilisateur (ou le désactive selon la politique)"""
        instance = self.get_object()

        # Empêcher un admin de se supprimer lui-même
        if instance == request.user:
            return Response({
                'error': "Vous ne pouvez pas supprimer votre propre compte."
            }, status=status.HTTP_400_BAD_REQUEST)

        user_name = instance.get_full_name() or instance.username
        instance.delete()

        return Response({
            'message': f"Utilisateur '{user_name}' supprimé avec succès."
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def change_role(self, request, pk=None):
        """
        Change le rôle d'un utilisateur.

        POST /api/users/{id}/change_role/
        Body: {"role": "admin|supervisor|driver"}
        """
        instance = self.get_object()

        # Empêcher un admin de changer son propre rôle
        if instance == request.user:
            return Response({
                'error': "Vous ne pouvez pas modifier votre propre rôle."
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.update(instance, serializer.validated_data)

        role_labels = {
            'admin': 'Administrateur',
            'supervisor': 'Superviseur',
            'driver': 'Chauffeur'
        }
        new_role_label = role_labels.get(instance.role, instance.role)

        return Response({
            'message': f"Rôle de '{instance.get_full_name() or instance.username}' changé en '{new_role_label}'.",
            'user': UserListSerializer(instance).data
        })

    @action(detail=True, methods=['post'])
    def toggle_status(self, request, pk=None):
        """
        Active ou désactive un compte utilisateur.

        POST /api/users/{id}/toggle_status/
        Body: {"is_active": true|false}
        """
        instance = self.get_object()

        # Empêcher un admin de se désactiver lui-même
        if instance == request.user:
            return Response({
                'error': "Vous ne pouvez pas modifier le statut de votre propre compte."
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.update(instance, serializer.validated_data)

        status_label = "activé" if instance.is_active else "désactivé"

        return Response({
            'message': f"Compte de '{instance.get_full_name() or instance.username}' {status_label}.",
            'user': UserListSerializer(instance).data
        })

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """
        Retourne des statistiques sur les utilisateurs de l'organisation.

        GET /api/users/stats/
        """
        queryset = self.get_queryset()

        total_users = queryset.count()
        active_users = queryset.filter(is_active=True).count()
        inactive_users = queryset.filter(is_active=False).count()

        by_role = {
            'admins': queryset.filter(role='admin').count(),
            'supervisors': queryset.filter(role='supervisor').count(),
            'drivers': queryset.filter(role='driver').count(),
        }

        on_duty = queryset.filter(is_active_duty=True).count()

        return Response({
            'total_users': total_users,
            'active_users': active_users,
            'inactive_users': inactive_users,
            'by_role': by_role,
            'on_duty': on_duty,
        })
