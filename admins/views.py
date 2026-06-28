import logging
import subprocess
import time
from datetime import datetime


from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.conf import settings as dj_settings

from .models import PanelAdmin, SyncLog, SyncSettings, _fmt_bytes
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
    }


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
    }
    return render(request, 'admins/dashboard.html', context)


@login_required
def portal(request):
    try:
        panel_admin = PanelAdmin.objects.get(username=request.user.username)
    except PanelAdmin.DoesNotExist:
        return render(request, 'admins/portal_not_found.html')

    if panel_admin.status == 'disabled':
        return render(request, 'admins/portal_blocked.html', {
            'admin': panel_admin,
            'support_telegram': '@support',
            'reason': 'disabled',
        })

    show_warning = False
    warning_pct = 0
    if panel_admin.has_data_limit and panel_admin.admin_limit_bytes > 0:
        warning_pct = round((panel_admin.admin_used_bytes / panel_admin.admin_limit_bytes) * 100, 1)
        show_warning = warning_pct >= 80

    context = _enrich(panel_admin)
    context['show_warning'] = show_warning
    context['warning_pct'] = warning_pct
    return render(request, 'admins/portal.html', context)


@login_required
def admin_detail(request, username):
    panel_admin = get_object_or_404(PanelAdmin, username=username)
    if not (request.user.is_superuser or request.user.is_staff or request.user.username == username):
        return redirect('portal')
    context = _enrich(panel_admin)
    return render(request, 'admins/admin_detail.html', context)


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
        return HttpResponse(status=403)
    if request.method != 'POST':
        return HttpResponse(status=405)

    try:
        minutes = max(1, int(request.POST.get('interval_minutes', 15)))
    except (ValueError, TypeError):
        return HttpResponse('<span class="action-result error">✗ Invalid value</span>', status=400)

    from django_celery_beat.models import PeriodicTask, IntervalSchedule

    obj, _ = SyncSettings.objects.get_or_create(pk=1)
    obj.interval_minutes = minutes
    obj.save()

    schedule, _ = IntervalSchedule.objects.get_or_create(
        every=minutes,
        period=IntervalSchedule.MINUTES,
    )
    PeriodicTask.objects.filter(name='Sync Panel Admins').update(interval=schedule)

    return HttpResponse(
        f'<span class="action-result success">✓ Sync set to every {minutes} minutes</span>'
    )


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
