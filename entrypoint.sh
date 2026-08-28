#!/bin/bash
set -e

echo "==> Waiting for MySQL to be ready..."
until python -c "
import sys, MySQLdb, os
try:
    MySQLdb.connect(
        host=os.environ['DB_HOST'],
        user=os.environ['DB_USER'],
        passwd=os.environ['DB_PASSWORD'],
        db=os.environ['DB_NAME']
    )
    sys.exit(0)
except Exception as e:
    sys.exit(1)
" 2>/dev/null; do
    echo "   MySQL not ready, retrying in 2s..."
    sleep 2
done
echo "==> MySQL is ready."

echo "==> Running migrations..."
python manage.py migrate --noinput

echo "==> Seeding PanelConfig from env (if not already set)..."
python manage.py shell -c "
import os
try:
    from admins.models import PanelConfig
except ImportError:
    try:
        from apps.panel_sync.models import PanelConfig
    except ImportError:
        from panel_sync.models import PanelConfig

url = os.environ.get('PANEL_BASE_URL', '').strip()
user = os.environ.get('PANEL_USERNAME', '').strip()
pwd = os.environ.get('PANEL_PASSWORD', '').strip()

if url:
    if not url.startswith('http'):
        url = 'https://' + url
    c = PanelConfig.get_config()
    if not c.base_url:
        c.base_url = url
        c.username = user
        c.password = pwd
        c.save()
        print('PanelConfig seeded from env')
    else:
        print('PanelConfig already set, skipping')
" || true

echo "==> Collecting static files..."
python manage.py collectstatic --noinput

echo "==> Creating/updating superuser..."
python manage.py shell -c "
from django.contrib.auth.models import User
import os
u, created = User.objects.get_or_create(username=os.environ.get('DJANGO_SUPERUSER_USERNAME','admin'))
u.set_password(os.environ.get('DJANGO_SUPERUSER_PASSWORD',''))
u.is_superuser = True
u.is_staff = True
u.is_active = True
u.email = os.environ.get('DJANGO_SUPERUSER_EMAIL','admin@pamp.local')
u.save()
print('Superuser', 'created' if created else 'password updated', ':', u.username)
" || true

echo "==> Setting up periodic sync task..."
python manage.py setup_periodic_tasks

echo "==> Starting application..."
exec "$@"
