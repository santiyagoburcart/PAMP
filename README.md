<div align="center">

# PAMP
### Pasargad Admins Management Panel

![License](https://img.shields.io/badge/license-MIT-blue)
![Django](https://img.shields.io/badge/Django-5.0-green)
![Docker](https://img.shields.io/badge/Docker-ready-blue)

A beautiful glassmorphism web panel for managing Pasargad VPN panel admins.

</div>

---

## Features

- **Admin Dashboard** — Monitor all admins with traffic usage, limits, progress bars
- **Per-Admin Portal** — Each admin logs in and sees only their own data
- **PAMP Limits** — Set custom limits independent of Sigma panel
- **Auto Enforcement** — Automatically disable users when admin reaches limit
- **Hidden Traffic Detection** — `total_user_limit − total_user_used − remaining`
- **Disable/Enable** — Control admin access and their users from the panel
- **Auto Sync** — Celery pulls fresh data every N minutes (configurable)
- **phpMyAdmin** — Web-based database management at `/phpmyadmin/`
- **Glassmorphism UI** — Beautiful dark gradient glass design

## Quick Install

```bash
bash <(curl -Ls https://raw.githubusercontent.com/santiyagoburcart/PAMP/main/install.sh)
```

## Manual Install

```bash
git clone https://github.com/santiyagoburcart/PAMP.git /opt/pamp
cd /opt/pamp
cp .env.example .env
nano .env  # Fill in your values
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

## Access

| Service | URL |
|---------|-----|
| Panel | `http://your-domain/` |
| phpMyAdmin | `http://your-domain/phpmyadmin/` |
| Django Admin | `http://your-domain/admin/` (superuser only) |

## Environment Variables

See `.env.example` for all required variables. **Never commit `.env` to git.**

## Tech Stack

Django 5 · MySQL 8 · Redis · Celery · Nginx · Docker Compose
