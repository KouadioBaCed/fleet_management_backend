from rest_framework import permissions


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
