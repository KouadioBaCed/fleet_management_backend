from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    CustomTokenObtainPairView,
    RegisterView,
    RegisterOrganizationView,
    profile_view,
    change_password_view,
    logout_view,
    delete_account_view,
    preferences_view,
    UserManagementViewSet,
    signup_initiate_view,
    signup_verify_token_view,
    signup_complete_view,
)

# Router pour la gestion des utilisateurs
router = DefaultRouter()
router.register(r'users', UserManagementViewSet, basename='user-management')

urlpatterns = [
    # Authentication
    path('login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('logout/', logout_view, name='logout'),
    path('refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Registration
    path('register/', RegisterView.as_view(), name='register'),
    path('register/organization/', RegisterOrganizationView.as_view(), name='register_organization'),

    # Signup with email verification
    path('signup/initiate/', signup_initiate_view, name='signup_initiate'),
    path('signup/verify-token/', signup_verify_token_view, name='signup_verify_token'),
    path('signup/complete/', signup_complete_view, name='signup_complete'),

    # Profile
    path('me/', profile_view, name='profile'),
    path('change-password/', change_password_view, name='change_password'),
    path('delete-account/', delete_account_view, name='delete_account'),

    # Preferences
    path('preferences/', preferences_view, name='preferences'),

    # User Management (Admin)
    path('', include(router.urls)),
]
