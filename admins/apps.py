from django.apps import AppConfig


class AdminsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'admins'
    verbose_name = 'Panel Admins'

    def ready(self):
        from django.contrib import admin

        class SecureAdminSite(admin.AdminSite):
            def has_permission(self, request):
                return request.user.is_active and request.user.is_superuser

        admin.site.__class__ = SecureAdminSite
