import logging
import requests
from urllib.parse import quote
from django.conf import settings

logger = logging.getLogger('admins')


class PanelAPIError(Exception):
    pass


class PanelAPIClient:
    def __init__(self):
        self.base_url = settings.PANEL_BASE_URL.rstrip('/')
        self.username = settings.PANEL_USERNAME
        self.password = settings.PANEL_PASSWORD
        self._token = None
        self._session = requests.Session()
        self._session.verify = False

    def authenticate(self):
        try:
            resp = self._session.post(
                f"{self.base_url}/api/admin/token",
                data={"username": self.username, "password": self.password},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data.get('access_token')
            if not self._token:
                raise PanelAPIError(f"No access_token in response: {data}")
            logger.info("Panel authentication successful for '%s'.", self.username)
            return self._token
        except requests.RequestException as e:
            raise PanelAPIError(f"Authentication failed: {e}") from e

    def login(self):
        """Authenticate and return True on success, False on failure."""
        try:
            self.authenticate()
            return True
        except PanelAPIError:
            return False

    def _get_headers(self):
        if not self._token:
            self.authenticate()
        return {"Authorization": f"Bearer {self._token}"}

    def _get(self, path, params=None, retry=True):
        url = f"{self.base_url}{path}"
        try:
            resp = self._session.get(url, headers=self._get_headers(), params=params, timeout=30)
            if resp.status_code == 401 and retry:
                self._token = None
                resp = self._session.get(url, headers=self._get_headers(), params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            raise PanelAPIError(f"GET {path} failed: {e}") from e

    def get_admins(self):
        data = self._get('/api/admins')
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get('admins', data.get('items', []))
        return []

    def get_users(self, admin_username=None, limit=4096):
        params = {'limit': limit}
        if admin_username:
            params['admin'] = admin_username
        data = self._get('/api/users', params=params)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get('users', data.get('items', []))
        return []

    def set_admin_limit(self, username: str, limit_gb: float) -> bool:
        """Thin wrapper kept for backward-compat. Returns bool."""
        limit_bytes = int(limit_gb * 1024 ** 3) if limit_gb > 0 else 0
        ok, _ = self.set_admin_data_limit(username, limit_bytes)
        return ok

    def set_admin_data_limit(self, username: str, limit_bytes: int) -> tuple:
        """Set admin data_limit on Pasargad. Returns (success: bool, message: str)."""
        if not self._token:
            self.authenticate()
        enc = quote(username, safe='')
        payload = {"data_limit": int(limit_bytes) if limit_bytes and limit_bytes > 0 else None}
        try:
            resp = self._session.put(
                f"{self.base_url}/api/admin/{enc}",
                headers=self._get_headers(),
                json=payload,
                timeout=30,
            )
            if resp.status_code == 401:
                self._token = None
                resp = self._session.put(
                    f"{self.base_url}/api/admin/{enc}",
                    headers=self._get_headers(),
                    json=payload,
                    timeout=30,
                )
            if resp.status_code in (200, 204):
                return True, "Limit updated on Pasargad"
            msg = f"HTTP {resp.status_code}: {resp.text[:120]}"
            logger.error("set_admin_data_limit %s: %s", username, msg)
            return False, msg
        except Exception as e:
            logger.error("set_admin_data_limit %s failed: %s", username, e)
            return False, f"Error: {str(e)[:120]}"

    def get_admin_user_stats(self, admin_username):
        """
        Fetch users for one admin and compute:
          - total_user_limit (sum of user data_limit)
          - total_user_used  (sum of user used_traffic)
          - per-status counts
        """
        try:
            users = self.get_users(admin_username=admin_username)
        except PanelAPIError:
            users = []

        total_limit = 0
        total_used = 0
        counts = {'active': 0, 'on_hold': 0, 'limited': 0, 'disabled': 0, 'expired': 0}

        for user in users:
            total_limit += user.get('data_limit') or 0
            total_used += user.get('used_traffic') or 0
            status = user.get('status', 'active')
            if status in counts:
                counts[status] += 1

        return {
            'total_user_limit': total_limit,
            'total_user_used': total_used,
            'active_user_count': counts['active'],
            'on_hold_users': counts['on_hold'],
            'limited_users': counts['limited'],
            'disabled_users': counts['disabled'],
            'expired_users': counts['expired'],
        }

    def disable_admin(self, username: str) -> bool:
        """Disable all users under an admin and mark the admin as disabled."""
        enc = quote(username, safe='')
        ok = True
        try:
            resp = self._session.post(
                f"{self.base_url}/api/admin/{enc}/users/disable",
                headers=self._get_headers(),
                timeout=15,
            )
            if resp.status_code not in (200, 204):
                ok = False
        except requests.RequestException as e:
            logger.error("disable_admin users call failed for %s: %s", username, e)
            ok = False
        try:
            resp2 = self._session.put(
                f"{self.base_url}/api/admin/{enc}",
                headers=self._get_headers(),
                json={"status": "disabled"},
                timeout=15,
            )
            if resp2.status_code not in (200, 204):
                ok = False
        except requests.RequestException as e:
            logger.error("disable_admin status call failed for %s: %s", username, e)
            ok = False
        return ok

    def enable_admin(self, username: str) -> bool:
        """Re-enable a previously blocked admin account."""
        enc = quote(username, safe='')
        try:
            resp = self._session.put(
                f"{self.base_url}/api/admin/{enc}",
                headers=self._get_headers(),
                json={"status": "active"},
                timeout=15,
            )
            return resp.status_code in (200, 204)
        except requests.RequestException as e:
            logger.error("enable_admin failed for %s: %s", username, e)
            return False

    def disable_all_users(self, admin_username: str) -> bool:
        """Disable all users belonging to an admin."""
        if not self._token:
            self.authenticate()
        enc = quote(admin_username, safe='')
        try:
            resp = self._session.post(
                f"{self.base_url}/api/admin/{enc}/users/disable",
                headers=self._get_headers(),
                timeout=30,
            )
            if resp.status_code in (200, 204):
                return True
            users = self.get_users(admin_username=admin_username)
            if not users:
                return False
            success_count = 0
            for user in users:
                uname = user.get("username")
                if not uname:
                    continue
                r = self._session.put(
                    f"{self.base_url}/api/user/{quote(uname, safe='')}",
                    headers=self._get_headers(),
                    json={"status": "disabled"},
                    timeout=10,
                )
                if r.status_code in (200, 204):
                    success_count += 1
            return success_count > 0
        except Exception as e:
            logger.error("disable_all_users for %s failed: %s", admin_username, e)
            return False

    def enable_all_users(self, admin_username: str) -> bool:
        """Enable all users belonging to an admin."""
        if not self._token:
            self.authenticate()
        enc = quote(admin_username, safe='')
        try:
            resp = self._session.post(
                f"{self.base_url}/api/admin/{enc}/users/enable",
                headers=self._get_headers(),
                timeout=30,
            )
            if resp.status_code in (200, 204):
                return True
            users = self.get_users(admin_username=admin_username)
            if not users:
                return False
            success_count = 0
            for user in users:
                uname = user.get("username")
                if not uname:
                    continue
                r = self._session.put(
                    f"{self.base_url}/api/user/{quote(uname, safe='')}",
                    headers=self._get_headers(),
                    json={"status": "active"},
                    timeout=10,
                )
                if r.status_code in (200, 204):
                    success_count += 1
            return success_count > 0
        except Exception as e:
            logger.error("enable_all_users for %s failed: %s", admin_username, e)
            return False

    def sync_all_admins(self):
        """
        Returns list of dicts ready for model update_or_create.
        Uses admin-level fields (total_users, used_traffic, data_limit) directly
        from the admin object, and fetches per-user status counts separately.
        """
        raw_admins = self.get_admins()
        results = []

        for admin_data in raw_admins:
            uname = admin_data.get('username')
            if not uname:
                continue

            # Admin-level fields from the panel API
            data_limit = admin_data.get('data_limit')           # None = unlimited
            has_data_limit = data_limit is not None
            admin_limit_bytes = int(data_limit) if has_data_limit else 0
            used_traffic = admin_data.get('used_traffic') or 0   # total used by this admin's users
            total_users = admin_data.get('total_users') or 0
            status = admin_data.get('status', 'active')

            # Remaining quota for limited admins
            if has_data_limit:
                admin_remaining = max(0, admin_limit_bytes - used_traffic)
            else:
                admin_remaining = 0

            # Per-user breakdown (requires one API call per admin)
            user_stats = self.get_admin_user_stats(uname)

            results.append({
                'username': uname,
                'is_sudo': admin_data.get('is_owner', admin_data.get('is_sudo', False)),
                'is_active': not admin_data.get('is_disabled', False),
                'status': status,
                'has_data_limit': has_data_limit,
                'admin_limit_bytes': admin_limit_bytes,
                'admin_remaining': admin_remaining,
                # Use admin-level used_traffic (includes deleted users) for accuracy
                'total_user_used': used_traffic,
                'total_user_limit': user_stats['total_user_limit'],
                'user_count': total_users,
                'active_user_count': user_stats['active_user_count'],
                'on_hold_users': user_stats['on_hold_users'],
                'limited_users': user_stats['limited_users'],
                'disabled_users': user_stats['disabled_users'],
                'expired_users': user_stats['expired_users'],
                'raw_data': admin_data,
            })

        logger.info("Fetched stats for %d admins.", len(results))
        return results
