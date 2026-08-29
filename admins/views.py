import logging
import subprocess
import time
from datetime import datetime


from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView as _DjangoLoginView
from django.db.models import Sum
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.conf import settings as dj_settings

from .models import PanelAdmin, SyncLog, SyncSettings, PanelConfig, UISettings, _fmt_bytes
from .tasks import sync_panel_admins

logger = logging.getLogger('admins')


# ── helpers ────────────────────────────────────────────────────────────────

def _fmt_bytes_signed(b: int) -> str:
    """Format a byte count with an explicit +/- sign. Zero returns '0 GB'."""
    if b == 0:
        return "0 GB"
    sign = "+" if b > 0 else "-"
    val = abs(b)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if val < 1024:
            return f"{sign}{val:.2f} {unit}"
        val /= 1024
    return f"{sign}{val:.2f} PB"


def _enrich(panel_admin):
    """Return context dict with all formatted values for portal/detail views."""
    a = panel_admin
    hidden = a.total_user_limit - a.total_user_used - a.admin_remaining
    if a.is_unlimited:
        sold_fmt = "0 GB"
        sold_val = 0
    else:
        sold_val = a.sold_limit_bytes
        sold_fmt = _fmt_bytes_signed(sold_val)
    return {
        'obj': a,
        'panel_admin': a,
        'hidden_traffic_fmt': _fmt_bytes(hidden),
        'total_user_limit_fmt': a.total_user_limit_fmt,
        'total_user_used_fmt': a.total_user_used_fmt,
        'admin_limit_fmt': a.admin_limit_fmt,
        'admin_used_fmt': a.admin_used_fmt,
        'admin_remaining_fmt': a.admin_remaining_fmt,
        'usage_percent': a.usage_percent,
        'sold_limit_fmt': sold_fmt,
        'sold_limit_value': sold_val,
        'deleted_used_fmt': _fmt_bytes(a.deleted_users_used_bytes or 0),
        'deleted_used_bytes': a.deleted_users_used_bytes or 0,
    }


# ── helpers ─────────────────────────────────────────────────────────────────

def _get_version():
    try:
        with open(_os.path.join(dj_settings.BASE_DIR, 'VERSION')) as f:
            return f.read().strip()
    except Exception:
        return 'dev'


def _tpl(v1, v2):
    return v2 if UISettings.get_theme() == 'v2' else v1


class PAMPLoginView(_DjangoLoginView):
    template_name = 'admins/login.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['pamp_version'] = _get_version()
        return ctx


# ── main views ─────────────────────────────────────────────────────────────

@login_required
def dashboard(request):
    if not (request.user.is_superuser or request.user.is_staff):
        return redirect('portal')

    admins = PanelAdmin.objects.all()
    totals = admins.aggregate(
        total_limit=Sum('total_user_limit'),
        total_used=Sum('total_user_used'),
        total_remaining=Sum('admin_remaining'),
        total_users=Sum('user_count'),
        total_active=Sum('active_user_count'),
    )

    total_limit = totals['total_limit'] or 0
    total_used = totals['total_used'] or 0
    total_remaining = totals['total_remaining'] or 0
    total_hidden = total_limit - total_used - total_remaining

    # Build over-limit list — admins at/above 80% of their Pasargad data_limit
    over_limit_list = []
    for a in PanelAdmin.objects.all():
        if not a.admin_limit_bytes or a.admin_limit_bytes <= 0:
            continue
        pct = round((a.admin_used_bytes / a.admin_limit_bytes) * 100, 1)
        if pct < 80:
            continue
        over_limit_list.append({
            'username': a.username,
            'limit_fmt': _fmt_bytes(a.admin_limit_bytes),
            'used_fmt': _fmt_bytes(a.admin_used_bytes),
            'pct': pct,
            'state': 'over' if pct >= 100 else 'at_risk',
            'status_label': a.status_label,
            'status_color': a.status_color,
        })
    over_limit_list.sort(key=lambda x: x['pct'], reverse=True)

    context = {
        'admins': admins,
        'admin_count': admins.count(),
        'total_count': PanelAdmin.objects.count(),
        'active_count': PanelAdmin.objects.filter(status='active').count(),
        'disabled_count': PanelAdmin.objects.filter(status='disabled').count(),
        'pamp_limited_count': PanelAdmin.objects.filter(pamp_blocked=True).count(),
        'near_limit_count': len(over_limit_list),
        'total_limit_fmt': _fmt_bytes(total_limit),
        'total_used_fmt': _fmt_bytes(total_used),
        'total_remaining_fmt': _fmt_bytes(total_remaining),
        'total_users': totals['total_users'] or 0,
        'total_active': totals['total_active'] or 0,
        'last_sync': SyncLog.objects.first(),
        'recent_logs': SyncLog.objects.all()[:10],
        'sync_interval': SyncSettings.get_interval(),
        'over_limit_admins': over_limit_list,
        'pamp_version': _get_version(),
        'github_url': 'https://github.com/santiyagoburcart/PAMP',
        'panel_config': PanelConfig.get_config(),
    }
    return render(request, _tpl('admins/dashboard.html', 'v2/dashboard_v2.html'), context)


@login_required
def portal(request):
    theme = UISettings.get_theme()
    try:
        panel_admin = PanelAdmin.objects.get(username=request.user.username)
    except PanelAdmin.DoesNotExist:
        if theme == 'v2':
            return render(request, 'v2/portal_v2.html', {'not_found': True})
        return render(request, 'admins/portal_not_found.html')

    is_blocked = panel_admin.status == 'disabled' or panel_admin.pamp_blocked
    block_reason = 'disabled' if panel_admin.status == 'disabled' else ('pamp_limited' if panel_admin.pamp_blocked else None)
    try:
        support_telegram = panel_admin.limit_config.support_telegram or '@support'
    except Exception:
        support_telegram = '@support'

    if theme == 'v1' and is_blocked:
        return render(request, 'admins/portal_blocked.html', {
            'admin': panel_admin,
            'support_telegram': support_telegram,
            'reason': block_reason or 'disabled',
        })

    show_warning = False
    warning_pct = 0
    if panel_admin.has_data_limit and panel_admin.admin_limit_bytes > 0:
        warning_pct = round((panel_admin.admin_used_bytes / panel_admin.admin_limit_bytes) * 100, 1)
        show_warning = warning_pct >= 80

    context = _enrich(panel_admin)
    context.update({
        'show_warning': show_warning,
        'warning_pct': warning_pct,
        'is_blocked': is_blocked,
        'block_reason': block_reason,
        'support_telegram': support_telegram,
        'a': panel_admin,
    })
    return render(request, _tpl('admins/portal.html', 'v2/portal_v2.html'), context)


@login_required
def admin_detail(request, username):
    panel_admin = get_object_or_404(PanelAdmin, username=username)
    if not (request.user.is_superuser or request.user.is_staff or request.user.username == username):
        return redirect('portal')
    context = _enrich(panel_admin)
    return render(request, _tpl('admins/admin_detail.html', 'v2/admin_detail_v2.html'), context)


@login_required
def login_redirect(request):
    if request.user.is_superuser or request.user.is_staff:
        return redirect('dashboard')
    return redirect('portal')


# ── actions ────────────────────────────────────────────────────────────────

@login_required
def trigger_sync(request):
    if request.method == 'POST':
        # Run synchronously so the page reload after the popup reflects fresh data.
        # (.delay() returns immediately and the reload races the async Celery task.)
        result = sync_panel_admins.apply(throw=False)
        if result.failed():
            err = str(result.result)[:120]
            return HttpResponse(f'<div class="action-result error">✗ Sync failed: {err}</div>')
        return HttpResponse(f'<div class="action-result success">✓ {result.result}</div>')
    return redirect('dashboard')


@login_required
def set_limit(request, username):
    if request.method != 'POST':
        return HttpResponse(status=405)
    if not request.user.is_superuser:
        return HttpResponse('<div class="action-result error">✗ Permission denied</div>')

    action = request.POST.get('action')
    try:
        value_gb = float(request.POST.get('value_gb', 0))
    except (TypeError, ValueError):
        return HttpResponse('<div class="action-result error">✗ Invalid value</div>')

    from .panel_api import PanelAPIClient

    panel_admin = get_object_or_404(PanelAdmin, username=username)
    client = PanelAPIClient()
    client.authenticate()

    current_limit = panel_admin.admin_limit_bytes or 0
    gb = 1024 ** 3

    if action == 'set':
        new_limit_bytes = int(value_gb * gb)
    elif action == 'add':
        new_limit_bytes = int(current_limit + value_gb * gb)
    elif action == 'reduce':
        new_limit_bytes = max(0, int(current_limit - value_gb * gb))
    else:
        return HttpResponse('<div class="action-result error">✗ Unknown action</div>')

    success, message = client.set_admin_data_limit(username, new_limit_bytes)
    if not success:
        return HttpResponse(f'<div class="action-result error">✗ Failed: {message}</div>')

    panel_admin.admin_limit_bytes = new_limit_bytes
    panel_admin.has_data_limit = new_limit_bytes > 0
    panel_admin.admin_remaining = max(0, new_limit_bytes - panel_admin.admin_used_bytes)
    panel_admin.save(update_fields=['admin_limit_bytes', 'has_data_limit', 'admin_remaining'])

    new_gb = new_limit_bytes / gb
    label = "Unlimited" if new_limit_bytes <= 0 else (
        f"{new_gb:.0f} GB" if new_gb < 1000 else f"{new_gb / 1000:.1f} TB"
    )
    return HttpResponse(f'<div class="action-result success">✓ Limit set to {label} — {message}</div>')


@login_required
def remove_limit(request, username):
    """Remove admin limit — sets unlimited on Pasargad. Superuser only."""
    if not request.user.is_superuser:
        return HttpResponse('<div class="action-result error">✗ Permission denied</div>')
    if request.method != 'POST':
        return HttpResponse(status=405)

    from .panel_api import PanelAPIClient

    panel_admin = get_object_or_404(PanelAdmin, username=username)
    client = PanelAPIClient()
    client.authenticate()

    success, message = client.set_admin_data_limit(username, 0)
    if not success:
        return HttpResponse(f'<div class="action-result error">✗ Failed: {message}</div>')

    panel_admin.admin_limit_bytes = 0
    panel_admin.has_data_limit = False
    panel_admin.admin_remaining = 0
    panel_admin.save(update_fields=['admin_limit_bytes', 'has_data_limit', 'admin_remaining'])

    return HttpResponse(f'<div class="action-result success">✓ {message} — admin is now unlimited</div>')


@login_required
def update_sync_interval(request):
    if not request.user.is_superuser:
        return HttpResponse('<div class="action-result error">✗ Permission denied</div>', status=403)
    if request.method != 'POST':
        return HttpResponse(status=405)

    try:
        minutes = max(1, int(request.POST.get('interval_minutes', 15)))
    except (ValueError, TypeError):
        return HttpResponse('<div class="action-result error">✗ Invalid value</div>', status=400)

    from django_celery_beat.models import PeriodicTask, IntervalSchedule

    obj, _ = SyncSettings.objects.get_or_create(pk=1)
    obj.interval_minutes = minutes
    obj.save()

    schedule, _ = IntervalSchedule.objects.get_or_create(
        every=minutes,
        period=IntervalSchedule.MINUTES,
    )
    # Use update_or_create + save() so django-celery-beat's PeriodicTaskChanged
    # signal fires and the scheduler picks up the new interval immediately.
    task, _ = PeriodicTask.objects.get_or_create(
        name='Sync Panel Admins',
        defaults={
            'task': 'admins.tasks.sync_panel_admins',
            'interval': schedule,
            'enabled': True,
        },
    )
    task.interval = schedule
    task.task = 'admins.tasks.sync_panel_admins'
    task.enabled = True
    task.save()

    return HttpResponse(
        f'<div class="action-result success">✓ Auto-sync set to every {minutes} minutes</div>'
    )


@login_required
def panel_config(request):
    if not request.user.is_superuser:
        return HttpResponse('<div class="action-result error">✗ Permission denied</div>', status=403)
    if request.method != 'POST':
        return HttpResponse(status=405)

    cfg = PanelConfig.get_config()
    cfg.base_url = request.POST.get('base_url', '').strip()
    cfg.username = request.POST.get('username', '').strip()
    new_password = request.POST.get('password', '').strip()
    if new_password:
        cfg.password = new_password
    cfg.save()

    from admins.panel_api import PanelAPIClient
    client = PanelAPIClient()
    if client.login():
        return HttpResponse('<div class="action-result success">✓ Panel config saved &amp; connection verified</div>')
    return HttpResponse('<div class="action-result error">✗ Saved, but connection test failed — check credentials</div>')


@login_required
def reset_deleted_traffic(request, username):
    if not request.user.is_superuser:
        return HttpResponse('<div class="action-result error">✗ Permission denied</div>', status=403)
    if request.method != 'POST':
        return HttpResponse(status=405)
    panel_admin = get_object_or_404(PanelAdmin, username=username)
    panel_admin.deleted_users_used_bytes = 0
    panel_admin.deleted_traffic_reset_at = timezone.now()
    panel_admin.save(update_fields=['deleted_users_used_bytes', 'deleted_traffic_reset_at'])
    return HttpResponse('<div class="action-result success">✓ Deleted-users counter reset to 0</div>')


@login_required
def telegram_config(request):
    if not request.user.is_superuser:
        return HttpResponse('<div class="action-result error">✗ Permission denied</div>', status=403)
    if request.method != 'POST':
        return HttpResponse(status=405)

    from .models import TelegramConfig
    cfg = TelegramConfig.get_config()
    new_token = request.POST.get('bot_token', '').strip()
    if new_token:
        cfg.bot_token = new_token
    cfg.chat_id = request.POST.get('chat_id', '').strip()
    try:
        cfg.backup_interval_hours = max(1, int(request.POST.get('backup_interval_hours', 24)))
    except (ValueError, TypeError):
        cfg.backup_interval_hours = 24
    cfg.is_enabled = request.POST.get('is_enabled') == '1'
    cfg.save()

    from django_celery_beat.models import PeriodicTask, IntervalSchedule
    if cfg.is_enabled and cfg.bot_token and cfg.chat_id:
        schedule, _ = IntervalSchedule.objects.get_or_create(
            every=cfg.backup_interval_hours * 60,
            period=IntervalSchedule.MINUTES,
        )
        task, _ = PeriodicTask.objects.get_or_create(
            name='Telegram DB Backup',
            defaults={
                'task': 'admins.tasks.send_telegram_backup',
                'interval': schedule,
                'enabled': True,
            },
        )
        task.interval = schedule
        task.enabled = True
        task.save()
    else:
        PeriodicTask.objects.filter(name='Telegram DB Backup').update(enabled=False)

    return HttpResponse('<div class="action-result success">✓ Telegram backup settings saved</div>')


@login_required
def telegram_backup_now(request):
    if not request.user.is_superuser:
        return HttpResponse('<div class="action-result error">✗ Permission denied</div>', status=403)
    if request.method != 'POST':
        return HttpResponse(status=405)

    from .tasks import send_telegram_backup
    result = send_telegram_backup.apply()
    outcome = result.result or ''
    if str(outcome).startswith('ok:'):
        return HttpResponse(f'<div class="action-result success">✓ Backup sent to Telegram</div>')
    return HttpResponse(f'<div class="action-result error">✗ {outcome}</div>')


@login_required
def settings_page(request):
    if not request.user.is_superuser:
        from django.shortcuts import redirect
        return redirect('dashboard')
    from .models import TelegramConfig
    return render(request, _tpl('admins/settings.html', 'v2/settings_v2.html'), {
        'panel_config': PanelConfig.get_config(),
        'sync_interval': SyncSettings.get_interval(),
        'current_theme': UISettings.get_theme(),
        'telegram_config': TelegramConfig.get_config(),
    })


@login_required
def sync_logs_page(request):
    if not request.user.is_superuser:
        from django.shortcuts import redirect
        return redirect('dashboard')
    logs = SyncLog.objects.all()[:100]
    total = SyncLog.objects.count()
    return render(request, _tpl('admins/sync_logs.html', 'v2/sync_logs_v2.html'), {
        'logs': logs,
        'total_syncs': total,
        'success_count': SyncLog.objects.filter(status='success').count(),
        'failed_count': SyncLog.objects.filter(status='failed').count(),
    })


@login_required
def admin_action(request, username):
    """Handle disable/enable admin and their users. Superuser only."""
    if not request.user.is_superuser:
        return HttpResponse('<div class="action-result error">✗ Permission denied</div>')
    if request.method != 'POST':
        return HttpResponse(status=405)

    action = request.POST.get('action')
    from .panel_api import PanelAPIClient

    panel_admin = get_object_or_404(PanelAdmin, username=username)
    client = PanelAPIClient()
    client.authenticate()

    if action == 'disable_admin':
        success, message = client.disable_admin(username)
        if success:
            panel_admin.status = 'disabled'
            panel_admin.is_active = False
            panel_admin.save(update_fields=['status', 'is_active'])
            return HttpResponse(f'<div class="action-result success">🔒 {message}</div>')
        return HttpResponse(f'<div class="action-result error">✗ Failed to disable: {message}</div>')

    elif action == 'enable_admin':
        success, message = client.enable_admin(username)
        if success:
            panel_admin.status = 'active'
            panel_admin.is_active = True
            panel_admin.save(update_fields=['status', 'is_active'])
            return HttpResponse(f'<div class="action-result success">✓ {message}</div>')
        return HttpResponse(f'<div class="action-result error">✗ Failed to enable: {message}</div>')

    elif action == 'disable_users':
        success, message = client.disable_all_users(username)
        if success:
            panel_admin.active_user_count = 0
            panel_admin.disabled_users = panel_admin.user_count
            panel_admin.save(update_fields=['active_user_count', 'disabled_users'])
            return HttpResponse(f'<div class="action-result success">👥🔒 {message}</div>')
        return HttpResponse(f'<div class="action-result error">✗ Failed: {message}</div>')

    elif action == 'enable_users':
        success, message = client.enable_all_users(username)
        if success:
            return HttpResponse(f'<div class="action-result success">👥✓ {message}</div>')
        return HttpResponse(f'<div class="action-result error">✗ Failed: {message}</div>')

    return HttpResponse('<div class="action-result error">✗ Unknown action</div>')


@login_required
def sync_status(request):
    last = SyncLog.objects.first()
    if last:
        return JsonResponse({
            'status': last.status,
            'admins_synced': last.admins_synced,
            'created_at': last.created_at.isoformat(),
            'duration': last.duration_seconds,
        })
    return JsonResponse({'status': 'never'})


@login_required
def backup_database(request):
    """Download a MySQL dump of the database. Superuser only."""
    if not request.user.is_superuser:
        return HttpResponse(status=403)

    db = dj_settings.DATABASES['default']
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    try:
        cmd = [
            'mysqldump',
            f'--host={db["HOST"]}',
            f'--port={str(db["PORT"])}',
            f'--user={db["USER"]}',
            f'--password={db["PASSWORD"]}',
            '--protocol=TCP',
            '--ssl=FALSE',
            '--default-character-set=utf8mb4',
            '--single-transaction',
            '--no-tablespaces',
            '--skip-lock-tables',
            db['NAME'],
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode != 0:
            err = result.stderr.decode()[:300]
            return HttpResponse(f'Backup failed: {err}', status=500)

        response = HttpResponse(result.stdout, content_type='application/sql')
        response['Content-Disposition'] = f'attachment; filename="pamp_backup_{timestamp}.sql"'
        return response
    except FileNotFoundError:
        return HttpResponse('mysqldump not found — check Dockerfile build', status=500)
    except subprocess.TimeoutExpired:
        return HttpResponse('Backup timed out', status=500)
    except Exception as e:
        return HttpResponse(f'Backup error: {e}', status=500)


@login_required
def import_database(request):
    """Restore database from uploaded SQL file. Superuser only."""
    if not request.user.is_superuser:
        return HttpResponse('<div class="action-result error">✗ Permission denied</div>', status=403)
    if request.method != 'POST':
        return HttpResponse(status=405)

    sql_file = request.FILES.get('sql_file')
    if not sql_file:
        return HttpResponse('<div class="action-result error">✗ No file uploaded</div>')
    if not sql_file.name.lower().endswith('.sql'):
        return HttpResponse('<div class="action-result error">✗ Only .sql files are allowed</div>')
    if sql_file.size > 100 * 1024 * 1024:
        return HttpResponse('<div class="action-result error">✗ File too large (max 100 MB)</div>')

    import tempfile, os as _tmpos
    db = dj_settings.DATABASES['default']

    with tempfile.NamedTemporaryFile(suffix='.sql', delete=False, mode='wb') as tmp:
        for chunk in sql_file.chunks():
            tmp.write(chunk)
        tmp_path = tmp.name

    try:
        cmd = [
            'mysql',
            f'--host={db["HOST"]}',
            f'--port={str(db.get("PORT", 3306))}',
            f'--user={db["USER"]}',
            f'--password={db["PASSWORD"]}',
            '--protocol=TCP',
            '--ssl=FALSE',
            '--default-character-set=utf8mb4',
            '--max_allowed_packet=256M',
            db['NAME'],
        ]
        with open(tmp_path, 'rb') as f:
            result = subprocess.run(cmd, stdin=f, stderr=subprocess.PIPE, timeout=300)

        if result.returncode != 0:
            stderr_out = result.stderr.decode('utf-8', errors='replace')
            error_lines = [l for l in stderr_out.split('\n') if 'ERROR' in l or l.lower().startswith('error')]
            error_msg = '\n'.join(error_lines[:3]) if error_lines else stderr_out[:300]
            return HttpResponse(f'<div class="action-result error">✗ Import failed: {error_msg}</div>')

        size_kb = sql_file.size / 1024
        return HttpResponse(
            f'<div class="action-result success">✓ Restored from {sql_file.name} ({size_kb:.1f} KB). Reload the page.</div>'
        )
    except subprocess.TimeoutExpired:
        return HttpResponse('<div class="action-result error">✗ Import timed out (>300s)</div>')
    except Exception as e:
        return HttpResponse(f'<div class="action-result error">✗ Error: {str(e)[:200]}</div>')
    finally:
        _tmpos.unlink(tmp_path)


import os as _os


def _read_host_meminfo():
    """Parse /host/proc/meminfo and return (used_bytes, total_bytes, percent)."""
    path = '/host/proc/meminfo'
    if not _os.path.exists(path):
        return None
    meminfo = {}
    with open(path) as f:
        for line in f:
            parts = line.split(':')
            if len(parts) == 2:
                key = parts[0].strip()
                val = parts[1].strip().split()[0]
                meminfo[key] = int(val) * 1024  # kB → bytes
    total = meminfo.get('MemTotal', 0)
    available = meminfo.get('MemAvailable', 0)
    used = total - available
    percent = round((used / total) * 100, 1) if total else 0
    return used, total, percent


def _read_host_netdev():
    """Parse /host/proc/net/dev and return (recv_bytes, sent_bytes) summed across non-loopback interfaces."""
    path = '/host/proc/net/dev'
    if not _os.path.exists(path):
        return None
    recv = sent = 0
    with open(path) as f:
        for line in f.readlines()[2:]:
            parts = line.split()
            if len(parts) < 10:
                continue
            iface = parts[0].rstrip(':')
            if iface == 'lo':
                continue
            recv += int(parts[1])
            sent += int(parts[9])
    return recv, sent


@login_required
def server_stats(request):
    """Return real-time server resource stats as JSON. Superuser only."""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'forbidden'}, status=403)

    try:
        import psutil
        _host_proc = _os.environ.get('HOST_PROC')
        if _host_proc:
            psutil.PROCFS_PATH = _host_proc

        cpu_percent = psutil.cpu_percent(interval=0.5)
        cpu_count = psutil.cpu_count()

        mem_host = _read_host_meminfo()
        if mem_host:
            mem_used, mem_total, mem_percent = mem_host
        else:
            m = psutil.virtual_memory()
            mem_used, mem_total, mem_percent = m.used, m.total, m.percent

        disk_path = '/host/root' if _os.path.exists('/host/root') else '/'
        disk = psutil.disk_usage(disk_path)

        net_host = _read_host_netdev()
        if net_host:
            net_recv, net_sent = net_host
        else:
            n = psutil.net_io_counters()
            net_recv, net_sent = n.bytes_recv, n.bytes_sent

        return JsonResponse({
            'cpu': {
                'percent': cpu_percent,
                'cores': cpu_count,
            },
            'memory': {
                'percent': mem_percent,
                'used_gb': round(mem_used / 1024 ** 3, 2),
                'total_gb': round(mem_total / 1024 ** 3, 2),
            },
            'disk': {
                'percent': disk.percent,
                'used_gb': round(disk.used / 1024 ** 3, 2),
                'total_gb': round(disk.total / 1024 ** 3, 2),
            },
            'network': {
                'sent_gb': round(net_sent / 1024 ** 3, 2),
                'recv_gb': round(net_recv / 1024 ** 3, 2),
                'sent_bytes': net_sent,
                'recv_bytes': net_recv,
            },
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def _get_public_ipv4():
    try:
        import urllib.request
        return urllib.request.urlopen('https://api4.ipify.org', timeout=3).read().decode()
    except Exception:
        return '—'


def _get_public_ipv6():
    try:
        import urllib.request
        return urllib.request.urlopen('https://api6.ipify.org', timeout=3).read().decode()
    except Exception:
        return '—'


def _get_docker_ips():
    try:
        import socket, psutil
        addrs = psutil.net_if_addrs()
        ips = []
        for iface, addr_list in addrs.items():
            if iface == 'lo':
                continue
            for addr in addr_list:
                if addr.family == socket.AF_INET:
                    ips.append(f'{iface}: {addr.address}')
        return ips
    except Exception:
        return []


def _get_kernel():
    import re
    try:
        host_proc = _os.environ.get('HOST_PROC', '/proc')
        with open(f'{host_proc}/version') as f:
            m = re.search(r'Linux version (\S+)', f.read())
            return m.group(1) if m else '—'
    except Exception:
        import platform
        return platform.release()


def _get_process_count():
    try:
        host_proc = _os.environ.get('HOST_PROC', '/proc')
        return len([d for d in _os.listdir(host_proc) if d.isdigit()])
    except Exception:
        return '—'


def _get_hostname():
    try:
        host_proc = _os.environ.get('HOST_PROC', '/proc')
        with open(f'{host_proc}/sys/kernel/hostname') as f:
            return f.read().strip()
    except Exception:
        import socket
        return socket.gethostname()


@login_required
def overview_v2(request):
    if not request.user.is_superuser:
        return redirect('portal')

    import psutil
    import os as _os2

    _host_proc = _os2.environ.get('HOST_PROC')
    if _host_proc:
        psutil.PROCFS_PATH = _host_proc

    try:
        up = int(time.time() - psutil.boot_time())
        d, h = up // 86400, (up % 86400) // 3600
        uptime_display = f'{d}d {h}h'
    except Exception:
        uptime_display = '—'

    ctx = {
        'uptime_display': uptime_display,
        'public_ipv4': _get_public_ipv4(),
        'public_ipv6': _get_public_ipv6(),
        'docker_ips': _get_docker_ips(),
        'kernel_version': _get_kernel(),
        'process_count': _get_process_count(),
        'hostname': _get_hostname(),
    }
    return render(request, 'v2/overview_v2.html', ctx)


@login_required
def dashboard_v2(request):
    if not request.user.is_superuser:
        return redirect('portal')

    admins = PanelAdmin.objects.all()
    totals = admins.aggregate(
        total_limit=Sum('total_user_limit'),
        total_used=Sum('total_user_used'),
        total_remaining=Sum('admin_remaining'),
        total_users=Sum('user_count'),
        total_active=Sum('active_user_count'),
    )

    total_limit = totals['total_limit'] or 0
    total_used = totals['total_used'] or 0
    total_remaining = totals['total_remaining'] or 0

    over_limit_list = []
    for a in PanelAdmin.objects.all():
        if not a.admin_limit_bytes or a.admin_limit_bytes <= 0:
            continue
        pct = round((a.admin_used_bytes / a.admin_limit_bytes) * 100, 1)
        if pct < 80:
            continue
        over_limit_list.append({
            'username': a.username,
            'limit_fmt': _fmt_bytes(a.admin_limit_bytes),
            'used_fmt': _fmt_bytes(a.admin_used_bytes),
            'pct': pct,
            'state': 'over' if pct >= 100 else 'at_risk',
            'status_label': a.status_label,
            'status_color': a.status_color,
        })
    over_limit_list.sort(key=lambda x: x['pct'], reverse=True)

    context = {
        'admins': admins,
        'admin_count': admins.count(),
        'active_count': PanelAdmin.objects.filter(status='active').count(),
        'disabled_count': PanelAdmin.objects.filter(status='disabled').count(),
        'pamp_limited_count': PanelAdmin.objects.filter(pamp_blocked=True).count(),
        'near_limit_count': len(over_limit_list),
        'total_limit_fmt': _fmt_bytes(total_limit),
        'total_used_fmt': _fmt_bytes(total_used),
        'total_remaining_fmt': _fmt_bytes(total_remaining),
        'total_users': totals['total_users'] or 0,
        'total_active': totals['total_active'] or 0,
        'last_sync': SyncLog.objects.first(),
        'over_limit_admins': over_limit_list,
    }
    return render(request, 'v2/dashboard_v2.html', context)


@login_required
def portal_v2(request):
    try:
        panel_admin = PanelAdmin.objects.get(username=request.user.username)
    except PanelAdmin.DoesNotExist:
        return render(request, 'v2/portal_v2.html', {'not_found': True})

    is_blocked = panel_admin.status == 'disabled' or panel_admin.pamp_blocked
    block_reason = 'disabled' if panel_admin.status == 'disabled' else ('pamp_limited' if panel_admin.pamp_blocked else None)
    support_telegram = panel_admin.support_telegram or '@support'

    show_warning = False
    warning_pct = 0
    if panel_admin.has_data_limit and panel_admin.admin_limit_bytes > 0:
        warning_pct = round((panel_admin.admin_used_bytes / panel_admin.admin_limit_bytes) * 100, 1)
        show_warning = warning_pct >= 80

    ctx = _enrich(panel_admin)
    ctx.update({
        'is_blocked': is_blocked,
        'block_reason': block_reason,
        'support_telegram': support_telegram,
        'show_warning': show_warning,
        'warning_pct': warning_pct,
        'a': panel_admin,
    })
    return render(request, 'v2/portal_v2.html', ctx)


@login_required
def sync_logs_v2(request):
    if not request.user.is_superuser:
        return redirect('portal')
    logs = SyncLog.objects.all()[:100]
    context = {
        'logs': logs,
        'total_syncs': SyncLog.objects.count(),
        'success_count': SyncLog.objects.filter(status='success').count(),
        'failed_count': SyncLog.objects.filter(status='failed').count(),
    }
    return render(request, 'v2/sync_logs_v2.html', context)


@login_required
def settings_v2(request):
    if not request.user.is_superuser:
        return redirect('portal')
    from .models import TelegramConfig
    context = {
        'panel_config': PanelConfig.get_config(),
        'sync_interval': SyncSettings.get_interval(),
        'telegram_config': TelegramConfig.get_config(),
    }
    return render(request, 'v2/settings_v2.html', context)


@login_required
def admin_detail_v2(request, username):
    panel_admin = get_object_or_404(PanelAdmin, username=username)
    if not (request.user.is_superuser or request.user.is_staff or request.user.username == username):
        return redirect('portal')
    context = _enrich(panel_admin)
    return render(request, 'v2/admin_detail_v2.html', context)


@login_required
def set_ui_theme(request):
    if not request.user.is_superuser:
        return HttpResponse('<div class="action-result error">✗ Permission denied</div>')
    if request.method != 'POST':
        return HttpResponse(status=405)
    theme = request.POST.get('theme', 'v2')
    UISettings.set_theme(theme)
    label = 'Modern (v2)' if theme == 'v2' else 'Classic (v1)'
    return HttpResponse(f'<div class="action-result success">✓ Theme set to {label}. Reloading…</div>')
