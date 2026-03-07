"""
Mixins pour les ViewSets de la flotte
Gère le filtrage automatique par organisation
"""


class OrganizationFilterMixin:
    """
    Mixin qui filtre automatiquement les querysets par organisation de l'utilisateur.
    Assigne automatiquement l'organisation lors de la création.
    """

    def get_queryset(self):
        """Filtre le queryset par l'organisation de l'utilisateur connecté"""
        queryset = super().get_queryset()

        # Si l'utilisateur n'est pas authentifié, retourner un queryset vide
        if not self.request.user.is_authenticated:
            return queryset.none()

        # Si l'utilisateur n'a pas d'organisation, retourner un queryset vide
        if not self.request.user.organization:
            return queryset.none()

        # Filtrer par organisation
        return queryset.filter(organization=self.request.user.organization)

    def perform_create(self, serializer):
        """Assigne automatiquement l'organisation de l'utilisateur lors de la création"""
        serializer.save(organization=self.request.user.organization)


class OrganizationReadOnlyMixin:
    """
    Mixin pour les vues en lecture seule filtrées par organisation
    """

    def get_queryset(self):
        """Filtre le queryset par l'organisation de l'utilisateur connecté"""
        queryset = super().get_queryset()

        if not self.request.user.is_authenticated:
            return queryset.none()

        if not self.request.user.organization:
            return queryset.none()

        return queryset.filter(organization=self.request.user.organization)
