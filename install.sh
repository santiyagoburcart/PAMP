#!/bin/bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}"
echo "  ██████╗  █████╗ ███╗   ███╗██████╗ "
echo "  ██╔══██╗██╔══██╗████╗ ████║██╔══██╗"
echo "  ██████╔╝███████║██╔████╔██║██████╔╝"
echo "  ██╔═══╝ ██╔══██║██║╚██╔╝██║██╔═══╝ "
echo "  ██║     ██║  ██║██║ ╚═╝ ██║██║     "
echo "  ╚═╝     ╚═╝  ╚═╝╚═╝     ╚═╝╚═╝     "
echo -e "${NC}"
echo -e "${GREEN}Pasargad Admins Management Panel${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root: sudo bash install.sh${NC}"
    exit 1
fi

if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}Installing Docker...${NC}"
    curl -fsSL https://get.docker.com | sh
fi

if ! docker compose version &> /dev/null; then
    echo -e "${YELLOW}Installing Docker Compose plugin...${NC}"
    apt-get install -y docker-compose-plugin 2>/dev/null || true
fi

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━ Configuration ━━━━━━━━━━━━━${NC}"

read -p "Panel URL (e.g. https://panel.example.com): " PANEL_URL
read -p "Panel Username: " PANEL_USER
read -s -p "Panel Password: " PANEL_PASS
echo ""
read -p "Your Domain (e.g. pamp.example.com) or press Enter to skip: " DOMAIN
read -p "DB Password [press Enter to auto-generate]: " DB_PASS
if [ -z "$DB_PASS" ]; then
    DB_PASS=$(openssl rand -hex 16)
fi

DB_ROOT_PASS=$(openssl rand -hex 16)
SECRET_KEY=$(openssl rand -hex 32)
ADMIN_PASS=$(openssl rand -hex 8)

ALLOWED_HOSTS="localhost,127.0.0.1"
if [ -n "$DOMAIN" ]; then
    ALLOWED_HOSTS="$DOMAIN,$ALLOWED_HOSTS"
fi

INSTALL_DIR="/opt/pamp"
echo ""
echo -e "${YELLOW}Cloning PAMP to $INSTALL_DIR ...${NC}"
if [ -d "$INSTALL_DIR/.git" ]; then
    echo -e "${YELLOW}Directory exists — updating...${NC}"
    git -C "$INSTALL_DIR" pull
else
    git clone https://github.com/santiyagoburcart/PAMP.git "$INSTALL_DIR"
fi
cd "$INSTALL_DIR"

cat > .env << ENV
SECRET_KEY=$SECRET_KEY
DEBUG=False
ALLOWED_HOSTS=$ALLOWED_HOSTS

DB_NAME=pamp_db
DB_USER=pamp_user
DB_PASSWORD=$DB_PASS
DB_ROOT_PASSWORD=$DB_ROOT_PASS
DB_HOST=db
DB_PORT=3306

CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1

PANEL_BASE_URL=$PANEL_URL
PANEL_USERNAME=$PANEL_USER
PANEL_PASSWORD=$PANEL_PASS
PANEL_SYNC_INTERVAL_MINUTES=15

DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_PASSWORD=$ADMIN_PASS
DJANGO_SUPERUSER_EMAIL=admin@pamp.local
ENV

echo -e "${YELLOW}Starting services...${NC}"
docker compose up -d --build

echo -e "${YELLOW}Waiting for database...${NC}"
sleep 20

echo -e "${YELLOW}Running migrations...${NC}"
docker compose exec -T web python manage.py migrate

echo -e "${YELLOW}Creating superuser...${NC}"
docker compose exec -T web python manage.py shell -c "
from django.contrib.auth.models import User
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@pamp.local', '$ADMIN_PASS')
    print('Superuser created')
else:
    print('Superuser already exists')
"

echo -e "${YELLOW}Collecting static files...${NC}"
docker compose exec -T web python manage.py collectstatic --noinput

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  PAMP installed successfully!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
if [ -n "$DOMAIN" ]; then
    echo -e "  Panel:      ${CYAN}http://$DOMAIN${NC}"
    echo -e "  phpMyAdmin: ${CYAN}http://$DOMAIN/phpmyadmin/${NC}"
    echo -e "  Admin:      ${CYAN}http://$DOMAIN/admin/${NC}"
else
    SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
    echo -e "  Panel:      ${CYAN}http://$SERVER_IP${NC}"
    echo -e "  phpMyAdmin: ${CYAN}http://$SERVER_IP/phpmyadmin/${NC}"
    echo -e "  Admin:      ${CYAN}http://$SERVER_IP/admin/${NC}"
fi
echo ""
echo -e "  Admin user: ${YELLOW}admin${NC}"
echo -e "  Admin pass: ${YELLOW}$ADMIN_PASS${NC}"
echo ""
echo -e "${RED}  Save these credentials — they won't be shown again.${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
