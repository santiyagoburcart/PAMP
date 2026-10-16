"""
Settings override used ONLY for `manage.py test`.

Points Django at an in-memory SQLite database instead of the live MySQL
instance, so the test suite can never read or write production data —
no CREATE DATABASE privilege on the MySQL user is needed either.

Usage:
    python manage.py test admins --settings=pamp.test_settings
"""
from .settings import *  # noqa: F401,F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# Tasks call .apply() directly in tests; keep Celery fully synchronous/local
# so no broker/worker is needed and nothing reaches Redis.
CELERY_ALWAYS_EAGER = True
CELERY_TASK_ALWAYS_EAGER = True
CELERY_BROKER_URL = 'memory://'
CELERY_RESULT_BACKEND = 'cache+memory://'

PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
