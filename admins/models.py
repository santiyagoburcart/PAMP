from django.db import models
from django.utils import timezone


def _fmt_bytes(b):
    b = b or 0
    if b == 0:
        return "0 B"
    b_abs = abs(b)
    sign = "-" if b < 0 else ""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if b_abs < 1024.0:
            return f"{sign}{b_abs:.2f} {unit}"
        b_abs /= 1024.0
    return f"{sign}{b_abs:.2f} PB"


class PanelAdmin(models.Model):
    username = models.CharField(max_length=255, unique=True, db_index=True)
    is_sudo = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    status = models.CharField(max_length=50, default='active')

    # Admin's own traffic quota from panel (bytes). False = unlimited.
    has_data_limit = models.BooleanField(default=False)
    admin_limit_bytes = models.BigIntegerField(default=0)
    admin_remaining = models.BigIntegerField(default=0)

    # Traffic aggregated across all this admin's users (bytes)
    total_user_limit = models.BigIntegerField(default=0)
    total_user_used = models.BigIntegerField(default=0)

    # User counts by status
    user_count = models.IntegerField(default=0)
    active_user_count = models.IntegerField(default=0)
    limited_users = models.IntegerField(default=0)
    disabled_users = models.IntegerField(default=0)
    expired_users = models.IntegerField(default=0)
    on_hold_users = models.IntegerField(default=0)

    # PAMP enforcement fields
    pamp_blocked = models.BooleanField(default=False)
    pamp_blocked_at = models.DateTimeField(null=True, blank=True)

    raw_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Panel Admin"
        verbose_name_plural = "Panel Admins"
        ordering = ['username']

    def __str__(self):
        return self.username

    # ── compatibility aliases ──────────────────────────────────────────────
    @property
    def users_count(self):
        return self.user_count

    @property
    def active_users(self):
        return self.active_user_count

    @property
    def admin_used_bytes(self):
        return self.total_user_used

    # ── traffic calculations ───────────────────────────────────────────────
    @property
    def hidden_traffic(self):
        return self.total_user_limit - self.total_user_used - self.admin_remaining

    @property
    def hidden_traffic_bytes(self):
        return self.hidden_traffic

    @property
    def usage_percent(self):
        if self.total_user_limit == 0:
            return 0
        return round((self.total_user_used / self.total_user_limit) * 100, 1)

    # ── formatted display strings ──────────────────────────────────────────
    @property
    def admin_limit_fmt(self):
        return "Unlimited" if not self.has_data_limit else _fmt_bytes(self.admin_limit_bytes)

    @property
    def admin_remaining_fmt(self):
        return "Unlimited" if not self.has_data_limit else _fmt_bytes(self.admin_remaining)

    @property
    def admin_used_fmt(self):
        return _fmt_bytes(self.total_user_used)

    @property
    def total_user_limit_fmt(self):
        return _fmt_bytes(self.total_user_limit)

    @property
    def total_user_used_fmt(self):
        return _fmt_bytes(self.total_user_used)

    @property
    def hidden_traffic_fmt(self):
        return _fmt_bytes(self.hidden_traffic)

    # ── GB helpers ─────────────────────────────────────────────────────────
    def _to_gb(self, val):
        return round((val or 0) / (1024 ** 3), 2)

    @property
    def total_user_limit_gb(self):
        return self._to_gb(self.total_user_limit)

    @property
    def total_user_used_gb(self):
        return self._to_gb(self.total_user_used)

    @property
    def admin_remaining_gb(self):
        return self._to_gb(self.admin_remaining)

    @property
    def hidden_traffic_gb(self):
        return self._to_gb(self.hidden_traffic)

    @property
    def admin_limit_gb(self):
        return self._to_gb(self.admin_limit_bytes)


class AdminLimit(models.Model):
    panel_admin = models.OneToOneField(
        PanelAdmin, on_delete=models.CASCADE, related_name='limit_config'
    )
    limit_bytes = models.BigIntegerField(default=0)
    warning_sent_80 = models.BooleanField(default=False)
    is_blocked = models.BooleanField(default=False)
    blocked_at = models.DateTimeField(null=True, blank=True)
    telegram_username = models.CharField(max_length=100, blank=True)
    support_telegram = models.CharField(max_length=100, blank=True, default='@support')

    class Meta:
        verbose_name = "Admin Limit Config"
        verbose_name_plural = "Admin Limit Configs"

    @property
    def limit_gb(self):
        return self.limit_bytes / (1024 ** 3) if self.limit_bytes else 0

    def __str__(self):
        return f"{self.panel_admin.username} — {self.limit_gb:.1f} GB"


class SyncLog(models.Model):
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_PARTIAL = 'partial'

    STATUS_CHOICES = [
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_PARTIAL, 'Partial'),
    ]

    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    admins_synced = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)
    duration_seconds = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Sync Log"
        verbose_name_plural = "Sync Logs"
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.status.upper()}] {self.created_at.strftime('%Y-%m-%d %H:%M')} — {self.admins_synced} admins"


class SyncSettings(models.Model):
    interval_minutes = models.IntegerField(default=15)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Sync Settings'

    @classmethod
    def get_interval(cls):
        obj, _ = cls.objects.get_or_create(pk=1, defaults={'interval_minutes': 15})
        return obj.interval_minutes

    def __str__(self):
        return f"Sync every {self.interval_minutes} minutes"
