import os
from django.conf import settings

_VERSION_FILE = os.path.join(settings.BASE_DIR, 'VERSION')


def pamp_globals(request):
    try:
        with open(_VERSION_FILE) as f:
            version = f.read().strip()
    except Exception:
        version = 'dev'

    last_sync_fmt = None
    avatar_url = ''
    if request.user.is_authenticated:
        try:
            from admins.models import SyncLog
            log = SyncLog.objects.order_by('-id').first()
            if log:
                last_sync_fmt = log.started_at.strftime('%H:%M')
        except Exception:
            pass
        avatar_url = request.session.get('avatar_url', '')

    return {
        'pamp_version': version,
        'github_url': 'https://github.com/santiyagoburcart/PAMP',
        'last_sync_fmt': last_sync_fmt,
        'avatar_url': avatar_url,
    }
