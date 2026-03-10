from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Organization, User, UserPreferences, EmailVerificationToken


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'email', 'phone', 'is_active', 'subscription_type', 'created_at']
    list_filter = ['is_active', 'subscription_type', 'created_at']
    search_fields = ['name', 'slug', 'email']
    readonly_fields = ['id', 'created_at', 'updated_at']
    ordering = ['-created_at']

 
@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'first_name', 'last_name', 'role', 'organization', 'is_active', 'is_active_duty', 'date_joined']
    list_filter = ['role', 'is_active', 'is_active_duty', 'organization', 'date_joined']
    search_fields = ['username', 'email', 'first_name', 'last_name', 'phone_number']
    ordering = ['-date_joined']

    fieldsets = BaseUserAdmin.fieldsets + (
        ('Informations supplémentaires', {
            'fields': ('organization', 'role', 'phone_number', 'profile_picture', 'is_active_duty')
        }),
    )

    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Informations supplémentaires', {
            'fields': ('organization', 'role', 'phone_number', 'is_active_duty')
        }),
    )


@admin.register(UserPreferences)
class UserPreferencesAdmin(admin.ModelAdmin):
    list_display = ['user', 'language', 'distance_unit', 'fuel_unit', 'theme', 'email_notifications', 'created_at']
    list_filter = ['language', 'distance_unit', 'theme', 'email_notifications']
    search_fields = ['user__username', 'user__email']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display = ['email', 'first_name', 'last_name', 'organization_name', 'is_used', 'is_expired', 'created_at', 'expires_at']
    list_filter = ['is_used', 'created_at']
    search_fields = ['email', 'first_name', 'last_name', 'organization_name']
    readonly_fields = ['id', 'token', 'created_at', 'is_expired']
    ordering = ['-created_at']

    def is_expired(self, obj):
        return obj.is_expired
    is_expired.boolean = True
    is_expired.short_description = 'Expiré'
