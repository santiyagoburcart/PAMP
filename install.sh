#!/bin/bash
set -e

if [[ "$1" == "--uninstall" ]]; then
  echo "Uninstalling PAMP..."
  cd /opt/pamp 2>/dev/null || true
  docker compose down -v 2>/dev/null || docker-compose down -v 2>/dev/null || true
  if [ -f .env ]; then
    DOMAIN=$(grep ALLOWED_HOSTS .env | cut -d= -f2 | cut -d, -f1)
    certbot delete --cert-name "$DOMAIN" --non-interactive 2>/dev/null || true
  fi
  cd /
  rm -rf /opt/pamp
  echo "PAMP uninstalled successfully."
  exit 0
fi

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

if docker compose version &>/dev/null 2>&1; then
    DC="docker compose"
elif command -v docker-compose &>/dev/null; then
    DC="docker-compose"
else
    echo -e "${YELLOW}Installing Docker Compose plugin...${NC}"
    apt-get install -y docker-compose-plugin 2>/dev/null || true
    DC="docker compose"
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

# Resolve the address to display/use (domain or public IP)
if [ -z "$DOMAIN" ]; then
    SERVER_ADDR=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
else
    SERVER_ADDR="$DOMAIN"
fi

# Write HTTP-only nginx.conf first so certbot can validate over HTTP.
# Nginx variables use DOMAIN_PLACEHOLDER; shell substitutes it via sed after the heredoc.
cat > nginx.conf << 'NGINXHTTP'
server {
    listen 80;
    server_name DOMAIN_PLACEHOLDER;
    client_max_body_size 20M;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location /static/ { alias /app/staticfiles/; expires 30d; }
    location /phpmyadmin/ {
        proxy_pass http://phpmyadmin/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_redirect off;
    }
    location / {
        resolver 127.0.0.11 valid=30s;
        set $upstream http://web:8000;
        proxy_pass $upstream;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_connect_timeout 60s;
        proxy_read_timeout 60s;
        proxy_redirect off;
    }
}
NGINXHTTP
sed -i "s/DOMAIN_PLACEHOLDER/$SERVER_ADDR/" nginx.conf

# Add certbot_www volume to nginx service and top-level volumes if missing
if ! grep -q "certbot_www" docker-compose.yml; then
    sed -i '/- \/etc\/letsencrypt:\/etc\/letsencrypt:ro/a\      - certbot_www:\/var\/www\/certbot' docker-compose.yml
    sed -i '/^  static_volume:$/a\  certbot_www:' docker-compose.yml
fi

# Use a relative URI for phpMyAdmin — avoids scheme/domain mismatch on fresh installs
sed -i "s|PMA_ABSOLUTE_URI:.*|PMA_ABSOLUTE_URI: /phpmyadmin/|" docker-compose.yml

echo -e "${YELLOW}Starting services...${NC}"
$DC up -d --build

echo -e "${YELLOW}Waiting for database...${NC}"
sleep 20

echo -e "${YELLOW}Running migrations...${NC}"
$DC exec -T web python manage.py migrate

echo -e "${YELLOW}Creating/updating superuser...${NC}"
$DC exec -T web python manage.py shell -c "
from django.contrib.auth.models import User
u, created = User.objects.get_or_create(username='admin')
u.set_password('$ADMIN_PASS')
u.is_superuser = True
u.is_staff = True
u.is_active = True
u.email = 'admin@pamp.local'
u.save()
print('Superuser', 'created' if created else 'password updated', ':', u.username)
"

echo -e "${YELLOW}Collecting static files...${NC}"
$DC exec -T web python manage.py collectstatic --noinput

# ── SSL Setup ──────────────────────────────────────────────────────────────────
SCHEME="http"
if [ -n "$DOMAIN" ]; then
    read -p "Set up HTTPS with Let's Encrypt now? (domain must already point to this server) [y/N]: " SSL_YN
    if [[ "$SSL_YN" =~ ^[Yy]$ ]]; then
        docker run --rm \
            -v /etc/letsencrypt:/etc/letsencrypt \
            -v pamp_certbot_www:/var/www/certbot \
            certbot/certbot certonly --webroot -w /var/www/certbot \
            -d "${DOMAIN}" --email "admin@${DOMAIN}" --agree-tos --no-eff-email --non-interactive

        if [ -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]; then
            cat > nginx.conf << NGINXSSL
server {
    listen 80;
    server_name ${DOMAIN};
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 301 https://\$host\$request_uri; }
}
server {
    listen 443 ssl;
    server_name ${DOMAIN};
    client_max_body_size 20M;
    ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_session_cache shared:SSL:10m;
    resolver 127.0.0.11 valid=10s;
    location /static/ { alias /app/staticfiles/; expires 30d; }
    location /phpmyadmin/ {
        proxy_pass http://phpmyadmin/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_redirect off;
    }
    location / {
        set \$upstream http://web:8000;
        proxy_pass \$upstream;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_connect_timeout 60s;
        proxy_read_timeout 60s;
        proxy_redirect off;
    }
}
NGINXSSL
            $DC restart nginx
            SCHEME="https"
            echo -e "${GREEN}HTTPS enabled for ${DOMAIN}${NC}"
        else
            echo -e "${YELLOW}WARNING: certbot failed (check DNS points to this server). Site running on HTTP only.${NC}"
        fi
    fi
fi

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  PAMP installed successfully!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  Panel:      ${CYAN}${SCHEME}://${SERVER_ADDR}${NC}"
echo -e "  phpMyAdmin: ${CYAN}${SCHEME}://${SERVER_ADDR}/phpmyadmin/${NC}"
echo -e "  Admin:      ${CYAN}${SCHEME}://${SERVER_ADDR}/admin/${NC}"
echo ""
echo -e "  Admin user: ${YELLOW}admin${NC}"
echo -e "  Admin pass: ${YELLOW}$ADMIN_PASS${NC}"
echo ""
echo -e "${RED}  Save these credentials — they won't be shown again.${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
