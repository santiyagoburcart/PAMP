import os
from django.conf import settings


def _read_version():
    try:
        with open(os.path.join(settings.BASE_DIR, 'VERSION')) as f:
            return f.read().strip()
    except Exception:
        return 'dev'


_VERSION = _read_version()


def pamp_globals(request):
    return {
        'pamp_version': _VERSION,
        'github_url': 'https://github.com/santiyagoburcart/PAMP',
    }
