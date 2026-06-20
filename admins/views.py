import logging
import subprocess
from datetime import datetime

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.conf import settings as dj_settings

from .models import PanelAdmin, AdminLimit, SyncLog, SyncSettings, _fmt_bytes
from .tasks import sync_panel_admins

logger = logging.getLogger('admins')


# ── helpers ────────────────────────────────────────────────────────────────

def _enrich(panel_admin):
    """Return context dict with all formatted values for portal/detail views."""
    a = panel_admin
    hidden = a.total_user_limit - a.total_user_used - a.admin_remaining
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

    # Build over-limit list — only admins currently at/above 80% of PAMP limit
    over_limit_list = []
    for lc in AdminLimit.objects.select_related('panel_admin').filter(limit_bytes__gt=0):
        a = lc.panel_admin
        used = a.admin_used_bytes
        if lc.limit_bytes <= 0:
            continue
        pct = round((used / lc.limit_bytes) * 100, 1)
        if pct >= 80:
            if pct >= 100:
                state = 'blocked' if a.pamp_blocked else 'over'
            else:
                state = 'at_risk'
            over_limit_list.append({
                'username': a.username,
                'pamp_limit_fmt': _fmt_bytes(lc.limit_bytes),
                'admin_used_fmt': _fmt_bytes(used),
                'pamp_pct': pct,
                'state': state,
                'pamp_blocked': a.pamp_blocked,
                'pamp_blocked_at': a.pamp_blocked_at,
            })
    over_limit_list.sort(key=lambda x: x['pamp_pct'], reverse=True)

    context = {
        'admins': admins,
        'admin_count': admins.count(),
        'total_count': PanelAdmin.objects.count(),
        'active_count': PanelAdmin.objects.filter(status='active').count(),
        'disabled_count': PanelAdmin.objects.filter(status='disabled').count(),
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

    if panel_admin.pamp_blocked:
        support_telegram = '@support'
        try:
            support_telegram = panel_admin.limit_config.support_telegram or '@support'
        except AdminLimit.DoesNotExist:
            pass
        return render(request, 'admins/portal_blocked.html', {
            'admin': panel_admin,
            'support_telegram': support_telegram,
        })

    show_warning = False
    warning_pct = 0
    try:
        lc = panel_admin.limit_config
        if lc.limit_bytes > 0:
            warning_pct = round((panel_admin.admin_used_bytes / lc.limit_bytes) * 100, 1)
            show_warning = warning_pct >= 80
    except AdminLimit.DoesNotExist:
        pass

    context = _enrich(panel_admin)
    context['show_warning'] = show_warning
    context['warning_pct'] = warning_pct
    return render(request, 'admins/portal.html', context)


@login_required
def admin_detail(request, username):
    panel_admin = get_object_or_404(PanelAdmin, username=username)
    if not (request.user.is_superuser or request.user.is_staff or request.user.username == username):
        return redirect('portal')
    return render(request, 'admins/admin_detail.html', _enrich(panel_admin))


@login_required
def login_redirect(request):
    if request.user.is_superuser or request.user.is_staff:
        return redirect('dashboard')
    return redirect('portal')


# ── actions ────────────────────────────────────────────────────────────────

@login_required
def trigger_sync(request):
    if request.method == 'POST':
        sync_panel_admins.delay()
        return HttpResponse(
            '<span style="background:rgba(16,185,129,0.2);color:#10b981;border:1px solid rgba(16,185,129,0.3);'
            'padding:4px 12px;border-radius:6px;font-size:12px;">↻ Sync queued</span>'
        )
    return redirect('dashboard')


@login_required
def set_limit(request, username):
    if request.method != 'POST':
        return HttpResponse(status=405)
    if not (request.user.is_superuser or request.user.username == username):
        return HttpResponse(status=403)

    action = request.POST.get('action', 'set')
    try:
        value_gb = float(request.POST.get('value_gb', 0))
    except (ValueError, TypeError):
        return HttpResponse('<div class="action-result error">✗ Invalid value</div>', status=400)

    panel_admin = get_object_or_404(PanelAdmin, username=username)

    from .panel_api import PanelAPIClient
    client = PanelAPIClient()
    client.authenticate()

    if action == 'add':
        try:
            current_gb = panel_admin.limit_config.limit_bytes / (1024 ** 3)
        except AdminLimit.DoesNotExist:
            current_gb = panel_admin.admin_limit_bytes / (1024 ** 3) if panel_admin.has_data_limit else 0
        new_limit_gb = current_gb + value_gb
    else:
        new_limit_gb = value_gb

    new_limit_bytes = int(new_limit_gb * 1024 ** 3)

    # Save PAMP limit to AdminLimit
    lc, _ = AdminLimit.objects.get_or_create(panel_admin=panel_admin)
    lc.limit_bytes = new_limit_bytes
    lc.save(update_fields=['limit_bytes'])

    # Unblock if new limit gives headroom
    if panel_admin.pamp_blocked and panel_admin.admin_used_bytes < new_limit_bytes:
        try:
            client.enable_admin(username)
        except Exception as e:
            logger.warning("enable_admin failed for %s: %s", username, e)
        panel_admin.pamp_blocked = False
        panel_admin.pamp_blocked_at = None
        panel_admin.save(update_fields=['pamp_blocked', 'pamp_blocked_at'])

    # Also set the limit on the Sigma panel
    client.set_admin_limit(username, new_limit_gb)

    sync_panel_admins.delay()

    gb_label = f"{new_limit_gb:.0f} GB" if new_limit_gb < 1000 else f"{new_limit_gb / 1000:.1f} TB"
    return HttpResponse(
        f'<div class="action-result success">✓ PAMP limit set to {gb_label}</div>'
    )


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
        success = client.disable_admin(username)
        if success:
            panel_admin.status = 'disabled'
            panel_admin.is_active = False
            panel_admin.save(update_fields=['status', 'is_active'])
            return HttpResponse(
                '<div class="action-result error" style="margin-bottom:12px;">🔒 Admin disabled</div>',
            )
        return HttpResponse('<div class="action-result error">✗ Failed to disable admin</div>')

    elif action == 'enable_admin':
        success = client.enable_admin(username)
        if success:
            panel_admin.status = 'active'
            panel_admin.is_active = True
            panel_admin.save(update_fields=['status', 'is_active'])
            return HttpResponse(
                '<div class="action-result success" style="margin-bottom:12px;">✓ Admin enabled</div>',
            )
        return HttpResponse('<div class="action-result error">✗ Failed to enable admin</div>')

    elif action == 'disable_users':
        success = client.disable_all_users(username)
        if success:
            panel_admin.active_user_count = 0
            panel_admin.disabled_users = panel_admin.user_count
            panel_admin.save(update_fields=['active_user_count', 'disabled_users'])
            return HttpResponse(
                '<div class="action-result error" style="margin-bottom:12px;">👥🔒 All users disabled</div>',
            )
        return HttpResponse('<div class="action-result error">✗ Failed to disable users</div>')

    elif action == 'enable_users':
        success = client.enable_all_users(username)
        if success:
            return HttpResponse(
                '<div class="action-result success" style="margin-bottom:12px;">👥✓ All users enabled</div>',
                headers={'HX-Refresh': 'true'},
            )
        return HttpResponse('<div class="action-result error">✗ Failed to enable users</div>')

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
