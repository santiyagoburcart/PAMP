import os
from django.conf import settings

_VERSION_FILE = os.path.join(settings.BASE_DIR, 'VERSION')


def pamp_globals(request):
    try:
        with open(_VERSION_FILE) as f:
            version = f.read().strip()
    except Exception:
        version = 'dev'
    return {
        'pamp_version': version,
        'github_url': 'https://github.com/santiyagoburcart/PAMP',
    }
