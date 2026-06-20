from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.models import User


class PanelAdminBackend(BaseBackend):
    """Authenticate users directly against the Sigma panel API."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None

        from admins.panel_api import PanelAPIClient, PanelAPIError
        client = PanelAPIClient()
        client.username = username
        client.password = password

        if not client.login():
            return None

        user, _ = User.objects.get_or_create(username=username)
        user.set_unusable_password()
        user.save(update_fields=['password'])
        return user

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
