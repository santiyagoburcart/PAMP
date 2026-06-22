import logging
import time
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger('admins')


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def sync_panel_admins(self):
    from .models import PanelAdmin, SyncLog
    from .panel_api import PanelAPIClient, PanelAPIError
    from django.contrib.auth.models import User

    start = time.time()
    logger.info("Starting panel admin sync...")

    try:
        client = PanelAPIClient()
        admins_data = client.sync_all_admins()
    except PanelAPIError as exc:
        duration = time.time() - start
        SyncLog.objects.create(
            status=SyncLog.STATUS_FAILED,
            admins_synced=0,
            error_message=str(exc),
            duration_seconds=round(duration, 2),
        )
        logger.error("Panel sync failed: %s", exc)
        raise self.retry(exc=exc)

    synced = 0
    errors = []
    now = timezone.now()

    for data in admins_data:
        try:
            PanelAdmin.objects.update_or_create(
                username=data['username'],
                defaults={
                    'is_sudo': data['is_sudo'],
                    'is_active': data['is_active'],
                    'status': data['status'],
                    'has_data_limit': data['has_data_limit'],
                    'admin_limit_bytes': data['admin_limit_bytes'],
                    'admin_remaining': data['admin_remaining'],
                    'total_user_limit': data['total_user_limit'],
                    'total_user_used': data['total_user_used'],
                    'user_count': data['user_count'],
                    'active_user_count': data['active_user_count'],
                    'on_hold_users': data['on_hold_users'],
                    'limited_users': data['limited_users'],
                    'disabled_users': data['disabled_users'],
                    'expired_users': data['expired_users'],
                    'raw_data': data['raw_data'],
                    'last_synced_at': now,
                },
            )
            User.objects.get_or_create(username=data['username'])
            synced += 1
        except Exception as e:
            errors.append(f"{data['username']}: {e}")
            logger.warning("Error saving admin %s: %s", data['username'], e)

    # Remove admins that no longer exist on the panel
    synced_usernames = {data['username'] for data in admins_data if data.get('username')}
    deleted_count = PanelAdmin.objects.exclude(username__in=synced_usernames).delete()[0]
    if deleted_count:
        logger.info("Removed %d admins no longer on panel", deleted_count)

    # After saving all admin data, run PAMP limit enforcement
    try:
        check_and_enforce_limits()
    except Exception as e:
        logger.error("Limit enforcement error: %s", e)
        errors.append(f"enforcement: {e}")

    duration = time.time() - start
    status = SyncLog.STATUS_SUCCESS if not errors else SyncLog.STATUS_PARTIAL
    SyncLog.objects.create(
        status=status,
        admins_synced=synced,
        error_message='\n'.join(errors),
        duration_seconds=round(duration, 2),
    )

    logger.info("Sync complete: %d admins in %.1fs.", synced, duration)
    return f"Synced {synced} admins."


def _check_and_enforce_limits():
    """Check all admins with a PAMP limit set and block/unblock as needed."""
    from .models import PanelAdmin, AdminLimit
    from .panel_api import PanelAPIClient

    configs = AdminLimit.objects.select_related('panel_admin').filter(limit_bytes__gt=0)
    if not configs.exists():
        return

    client = PanelAPIClient()
    client.authenticate()

    for lc in configs:
        admin = lc.panel_admin
        used = admin.admin_used_bytes
        limit = lc.limit_bytes
        usage_pct = (used / limit) * 100 if limit > 0 else 0

        if usage_pct >= 100 and not admin.pamp_blocked:
            logger.warning("BLOCK: %s at %.1f%% (used=%d, limit=%d)", admin.username, usage_pct, used, limit)
            try:
                client.disable_admin(admin.username)
            except Exception as e:
                logger.error("disable_admin failed for %s: %s", admin.username, e)
            admin.pamp_blocked = True
            admin.pamp_blocked_at = timezone.now()
            admin.save(update_fields=['pamp_blocked', 'pamp_blocked_at'])
            if not lc.warning_sent_80:
                lc.warning_sent_80 = True
                lc.save(update_fields=['warning_sent_80'])

        elif usage_pct < 100 and admin.pamp_blocked:
            logger.info("UNBLOCK: %s at %.1f%%", admin.username, usage_pct)
            try:
                client.enable_admin(admin.username)
            except Exception as e:
                logger.error("enable_admin failed for %s: %s", admin.username, e)
            admin.pamp_blocked = False
            admin.pamp_blocked_at = None
            admin.save(update_fields=['pamp_blocked', 'pamp_blocked_at'])

        # 80% warning flag bookkeeping
        if usage_pct >= 80 and not lc.warning_sent_80:
            lc.warning_sent_80 = True
            lc.save(update_fields=['warning_sent_80'])
        elif usage_pct < 80 and lc.warning_sent_80:
            lc.warning_sent_80 = False
            lc.save(update_fields=['warning_sent_80'])
