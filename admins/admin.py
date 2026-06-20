from django.contrib import admin
from django.utils.html import format_html
from .models import PanelAdmin, SyncLog


@admin.register(PanelAdmin)
class PanelAdminAdmin(admin.ModelAdmin):
    list_display = (
        'username', 'is_sudo', 'is_active',
        'user_count', 'active_user_count',
        'limit_gb', 'used_gb', 'remaining_gb', 'hidden_gb',
        'last_synced_at',
    )
    list_filter = ('is_sudo', 'is_active')
    search_fields = ('username',)
    readonly_fields = (
        'total_user_limit', 'total_user_used', 'admin_remaining',
        'user_count', 'active_user_count', 'raw_data',
        'created_at', 'updated_at', 'last_synced_at',
    )

    def limit_gb(self, obj):
        return f"{obj.total_user_limit_gb} GB"
    limit_gb.short_description = "Limit"

    def used_gb(self, obj):
        return f"{obj.total_user_used_gb} GB"
    used_gb.short_description = "Used"

    def remaining_gb(self, obj):
        return f"{obj.admin_remaining_gb} GB"
    remaining_gb.short_description = "Remaining"

    def hidden_gb(self, obj):
        val = obj.hidden_traffic_gb
        color = 'red' if val > 0 else 'green'
        return format_html('<span style="color:{}">{} GB</span>', color, val)
    hidden_gb.short_description = "Hidden"


@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'status', 'admins_synced', 'duration_seconds', 'short_error')
    list_filter = ('status',)
    readonly_fields = ('created_at', 'status', 'admins_synced', 'error_message', 'duration_seconds')

    def short_error(self, obj):
        if obj.error_message:
            return obj.error_message[:80] + ('...' if len(obj.error_message) > 80 else '')
        return '—'
    short_error.short_description = "Error"
