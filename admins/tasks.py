import logging
import time
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger('admins')


def track_deleted_users(panel_admin, current_users):
    """
    Compare current users to last snapshot. Accumulate used-traffic of deleted users
    into panel_admin.deleted_users_used_bytes, then refresh the snapshot table.
    Only the sold-volume field (total_user_limit) is affected — called by sync loop.
    """
    from .models import UserTrafficSnapshot

    current_map = {
        u['username']: (u.get('used_traffic') or 0)
        for u in current_users
        if u.get('username')
    }

    prev = {
        s.user_username: s.used_traffic_bytes
        for s in UserTrafficSnapshot.objects.filter(panel_admin=panel_admin)
    }

    deleted = set(prev.keys()) - set(current_map.keys())
    added = sum(prev[u] for u in deleted)

    if added > 0:
        panel_admin.deleted_users_used_bytes = (panel_admin.deleted_users_used_bytes or 0) + added
        panel_admin.save(update_fields=['deleted_users_used_bytes'])
        logger.info(
            "Snapshot: %s — %d deleted user(s), +%d bytes to sold volume",
            panel_admin.username, len(deleted), added,
        )

    if deleted:
        UserTrafficSnapshot.objects.filter(
            panel_admin=panel_admin, user_username__in=deleted
        ).delete()

    # Upsert snapshots for all currently live users
    for uname, used in current_map.items():
        UserTrafficSnapshot.objects.update_or_create(
            panel_admin=panel_admin,
            user_username=uname,
            defaults={'used_traffic_bytes': used},
        )


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

    # Auto-enforce data limits
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


def check_and_enforce_limits():
    """Block admins who have consumed their Pasargad data_limit; unblock when limit is raised."""
    from .models import PanelAdmin
    from .panel_api import PanelAPIClient

    limited = PanelAdmin.objects.filter(has_data_limit=True, admin_limit_bytes__gt=0)
    count = limited.count()
    if not count:
        logger.info("Enforcement: no limited admins, skipping")
        return

    logger.info("Enforcement: checking %d limited admin(s)", count)
    client = PanelAPIClient()
    client.authenticate()

    for admin in limited:
        used = admin.admin_used_bytes
        limit = admin.admin_limit_bytes
        pct = (used / limit * 100) if limit > 0 else 0

        if used >= limit and not admin.pamp_blocked:
            logger.warning("Enforcement: BLOCKING %s at %.1f%% (%d/%d)", admin.username, pct, used, limit)
            ok, msg = client.disable_admin(admin.username)
            if ok:
                admin.pamp_blocked = True
                admin.pamp_blocked_at = timezone.now()
                admin.save(update_fields=['pamp_blocked', 'pamp_blocked_at'])
            else:
                logger.error("Enforcement: disable_admin %s failed: %s", admin.username, msg)

        elif used < limit and admin.pamp_blocked:
            logger.info("Enforcement: UNBLOCKING %s at %.1f%%", admin.username, pct)
            ok, msg = client.enable_admin(admin.username)
            if ok:
                admin.pamp_blocked = False
                admin.pamp_blocked_at = None
                admin.save(update_fields=['pamp_blocked', 'pamp_blocked_at'])
            else:
                logger.error("Enforcement: enable_admin %s failed: %s", admin.username, msg)

    logger.info("Enforcement: done")
