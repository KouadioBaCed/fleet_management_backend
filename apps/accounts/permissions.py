from rest_framework import permissions


class HasOrganizationModule(permissions.BasePermission):
    """Vérifie que l'organisation de l'utilisateur a accès au module requis.

    Le module requis est déterminé par, dans l'ordre :
      1. ``self.module_code`` (défini par la fabrique :func:`RequireModule`,
         pratique pour les vues fonctionnelles) ;
      2. l'attribut ``required_module`` de la vue (pratique pour les ViewSets).

    Si aucun module n'est requis, la permission est accordée (pas de gating).
    Si l'organisation ne possède pas le module, l'accès est refusé (HTTP 403).

    Cette vérification est la **garantie de sécurité côté serveur** : même si le
    frontend masque l'interface, l'API reste protégée.
    """

    module_code = None
    message = "Votre organisation n'a pas accès à ce module."

    def _required_module(self, view):
        return self.module_code or getattr(view, 'required_module', None)

    def has_permission(self, request, view):
        required = self._required_module(view)
        if not required:
            return True

        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False

        organization = getattr(user, 'organization', None)
        if not organization or not organization.is_active:
            return False

        return organization.has_module(required)

    def has_object_permission(self, request, view, obj):
        # La vérification au niveau objet est identique à celle de la vue :
        # l'accès au module conditionne l'accès à toutes ses ressources.
        return self.has_permission(request, view)


def RequireModule(code):
    """Fabrique une classe de permission liée à un module précis.

    Idéale pour les vues fonctionnelles ou ``APIView``::

        @permission_classes([IsAuthenticated, IsOrganizationMember, RequireModule(Modules.TRACKING)])
        def track_location(request): ...
    """
    return type(
        f'RequireModule_{code}',
        (HasOrganizationModule,),
        {'module_code': code},
    )


class IsAuthenticated(permissions.BasePermission):
    """
    Permission de base : utilisateur authentifié
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated


class IsOrganizationMember(permissions.BasePermission):
    """
    Permission vérifiant que l'utilisateur appartient à une organisation active
    """
    message = "Vous devez appartenir à une organisation active."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if not request.user.organization:
            return False
        return request.user.organization.is_active


class IsOrganizationAdmin(permissions.BasePermission):
    """
    Permission pour les administrateurs d'organisation uniquement
    """
    message = "Seuls les administrateurs peuvent effectuer cette action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if not request.user.organization:
            return False
        return request.user.role == 'admin' and request.user.organization.is_active


class IsOrganizationAdminOrSupervisor(permissions.BasePermission):
    """
    Permission pour les administrateurs et superviseurs d'organisation
    """
    message = "Seuls les administrateurs et superviseurs peuvent effectuer cette action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if not request.user.organization:
            return False
        return request.user.role in ['admin', 'supervisor'] and request.user.organization.is_active


class IsDriver(permissions.BasePermission):
    """
    Permission pour les conducteurs uniquement
    """
    message = "Cette action est réservée aux conducteurs."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role == 'driver'


class IsOrganizationObjectOwner(permissions.BasePermission):
    """
    Permission vérifiant que l'objet appartient à l'organisation de l'utilisateur
    """
    message = "Vous n'avez pas accès à cette ressource."

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        if not request.user.organization:
            return False

        # Vérifier si l'objet a un champ organization
        if hasattr(obj, 'organization'):
            return obj.organization == request.user.organization

        # Pour les objets liés via user (comme le profil)
        if hasattr(obj, 'user'):
            return obj.user.organization == request.user.organization

        return False


class ReadOnly(permissions.BasePermission):
    """
    Permission en lecture seule
    """
    def has_permission(self, request, view):
        return request.method in permissions.SAFE_METHODS


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Admin peut tout faire, les autres peuvent uniquement lire
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user and request.user.is_authenticated and request.user.role == 'admin'
