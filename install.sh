#!/bin/bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

INSTALL_DIR="/opt/pamp"

print_banner() {
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
}

detect_compose() {
    if docker compose version &>/dev/null 2>&1; then
        DC="docker compose"
    elif command -v docker-compose &>/dev/null; then
        DC="docker-compose"
    else
        echo -e "${YELLOW}Installing Docker Compose plugin...${NC}"
        apt-get install -y docker-compose-plugin 2>/dev/null || true
        DC="docker compose"
    fi
}

do_install() {
    if ! command -v docker &>/dev/null; then
        echo -e "${YELLOW}Installing Docker...${NC}"
        curl -fsSL https://get.docker.com | sh
    fi
    detect_compose

    # Global cleanup — remove any leftover pamp volumes regardless of install state.
    # Runs before git clone so it works even on a fresh server with no docker-compose.yml.
    echo -e "${YELLOW}Removing any leftover PAMP volumes...${NC}"
    if [ -f "/opt/pamp/docker-compose.yml" ]; then
        cd /opt/pamp
        docker compose down -v 2>/dev/null || true
        cd - >/dev/null
    fi
    for VOL in pamp_mysql_data pamp_static_volume pamp_certbot_www; do
        if docker volume inspect "$VOL" >/dev/null 2>&1; then
            echo "Removing volume: $VOL"
            docker volume rm "$VOL" 2>/dev/null || true
        fi
    done
    echo -e "${YELLOW}Volume cleanup done.${NC}"

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
        CSRF_ORIGINS="https://$DOMAIN,http://$DOMAIN"
    else
        CSRF_ORIGINS="http://localhost,http://127.0.0.1"
    fi

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
CSRF_TRUSTED_ORIGINS=$CSRF_ORIGINS

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

    if [ -z "$DOMAIN" ]; then
        SERVER_ADDR=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
    else
        SERVER_ADDR="$DOMAIN"
    fi

    # Write HTTP-only nginx.conf first so the app is reachable and certbot can validate.
    # Uses DOMAIN_PLACEHOLDER so nginx $ variables aren't expanded by the shell.
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

    # Add certbot_www volume to nginx service and top-level volumes if not already present
    if ! grep -q "certbot_www" docker-compose.yml; then
        sed -i '/- \/etc\/letsencrypt:\/etc\/letsencrypt:ro/a\      - certbot_www:\/var\/www\/certbot' docker-compose.yml
        sed -i '/^  static_volume:$/a\  certbot_www:' docker-compose.yml
    fi

    # Relative URI avoids scheme/domain mismatch on fresh installs
    sed -i "s|PMA_ABSOLUTE_URI:.*|PMA_ABSOLUTE_URI: /phpmyadmin/|" docker-compose.yml

    # Clean up any leftover containers and volumes from a previous install
    echo -e "${YELLOW}Cleaning up any previous installation data...${NC}"
    $DC down -v 2>/dev/null || true
    docker volume rm pamp_mysql_data pamp_static_volume pamp_certbot_www 2>/dev/null || true
    echo -e "${YELLOW}Cleanup done.${NC}"

    echo -e "${YELLOW}Starting services...${NC}"
    $DC up -d --build

    echo -e "${YELLOW}Waiting for web container to be ready...${NC}"
    MAX_WAIT=120
    WAITED=0
    while [ $WAITED -lt $MAX_WAIT ]; do
        STATUS=$(docker inspect --format='{{.State.Status}}' pamp-web-1 2>/dev/null || \
                 docker inspect --format='{{.State.Status}}' pamp_web_1 2>/dev/null || echo "unknown")
        if [ "$STATUS" = "running" ]; then
            if $DC logs web --tail=5 2>/dev/null | grep -q "Starting application\|Booting worker\|Listening at"; then
                echo -e "${GREEN}Web container is ready.${NC}"
                break
            fi
        fi
        if [ "$STATUS" = "restarting" ]; then
            echo -e "${RED}Web container is restarting — checking logs...${NC}"
            $DC logs web --tail=20
            echo -e "${RED}ERROR: Web container failed to start. Check logs above.${NC}"
            exit 1
        fi
        sleep 3
        WAITED=$((WAITED + 3))
        echo "Still waiting... (${WAITED}s)"
    done
    if [ $WAITED -ge $MAX_WAIT ]; then
        echo -e "${RED}ERROR: Web container did not become ready in ${MAX_WAIT}s.${NC}"
        $DC logs web --tail=30
        exit 1
    fi

    echo -e "${YELLOW}Running migrations...${NC}"
    RETRY=0
    until $DC exec -T web python manage.py migrate --noinput 2>&1; do
        RETRY=$((RETRY + 1))
        if [ $RETRY -ge 3 ]; then
            echo -e "${RED}Migration failed after 3 attempts. Check logs:${NC}"
            $DC logs web --tail=20
            exit 1
        fi
        echo "Migration attempt $RETRY failed, retrying in 5s..."
        sleep 5
    done

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

    # ── Two-phase SSL setup ────────────────────────────────────────────────────
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
}

do_update() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  PAMP Update${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    if [ ! -f "$INSTALL_DIR/.env" ]; then
        echo -e "${RED}  PAMP is not installed. Choose Install instead.${NC}"
        exit 1
    fi

    cd "$INSTALL_DIR"
    detect_compose

    # Show installed version
    INSTALLED_VERSION=$(cat VERSION 2>/dev/null || echo "unknown")
    echo -e "  Installed version : ${YELLOW}v${INSTALLED_VERSION}${NC}"

    # Fetch latest version from GitHub
    echo -e "  Checking GitHub for latest version..."
    LATEST_VERSION=$(curl -sf https://raw.githubusercontent.com/santiyagoburcart/PAMP/main/VERSION 2>/dev/null | tr -d '[:space:]')
    if [ -z "$LATEST_VERSION" ]; then
        echo -e "${RED}  Could not fetch latest version from GitHub. Check internet connection.${NC}"
        exit 1
    fi
    echo -e "  Latest on GitHub  : ${GREEN}v${LATEST_VERSION}${NC}"

    # Already up to date?
    if [ "$INSTALLED_VERSION" = "$LATEST_VERSION" ]; then
        echo ""
        echo -e "${GREEN}  ✓ Already up to date! No update needed.${NC}"
        echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        exit 0
    fi

    echo ""
    echo -e "  New version available: ${YELLOW}v${INSTALLED_VERSION}${NC} → ${GREEN}v${LATEST_VERSION}${NC}"
    echo ""

    # Show changelog for the new version
    echo -e "  ${CYAN}What's new in v${LATEST_VERSION}:${NC}"
    echo -e "  ─────────────────────────────────"
    ESCAPED_VER=$(echo "$LATEST_VERSION" | sed 's/\./\\./g')
    curl -sf https://raw.githubusercontent.com/santiyagoburcart/PAMP/main/CHANGELOG.md 2>/dev/null \
        | awk "/^## \\[?v?${ESCAPED_VER}\\]?/,/^---/" \
        | grep -v "^---" \
        | head -25 \
        | sed 's/^/  /'
    echo ""

    read -p "  Proceed with update? [y/N]: " CONFIRM
    if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}  Update cancelled.${NC}"
        exit 0
    fi

    echo ""
    echo -e "${YELLOW}  Updating PAMP code...${NC}"

    # Back up nginx.conf — git reset --hard will delete it (it's untracked in new versions)
    NGINX_BAK="/tmp/pamp_nginx_$$.conf"
    if [ -f "nginx.conf" ]; then
        cp nginx.conf "$NGINX_BAK"
    fi

    git fetch origin main
    git reset --hard origin/main

    # Restore nginx.conf if git reset removed it
    if [ ! -f "nginx.conf" ]; then
        if [ -f "$NGINX_BAK" ]; then
            cp "$NGINX_BAK" nginx.conf
            echo -e "${GREEN}  ✓ nginx.conf restored (server-specific config preserved)${NC}"
        elif [ -f "nginx.conf.template" ] && [ -f ".env" ]; then
            UPDATE_DOMAIN=$(grep "^ALLOWED_HOSTS" .env | cut -d= -f2 | cut -d, -f1)
            sed "s/PAMP_DOMAIN/${UPDATE_DOMAIN}/g" nginx.conf.template > nginx.conf
            echo -e "${GREEN}  ✓ nginx.conf regenerated from template for ${UPDATE_DOMAIN}${NC}"
        else
            echo -e "${RED}  WARNING: nginx.conf missing — please recreate it manually before restarting nginx${NC}"
        fi
    fi
    rm -f "$NGINX_BAK"

    # Backfill CSRF_TRUSTED_ORIGINS if missing (older installs)
    if ! grep -q "CSRF_TRUSTED_ORIGINS" .env 2>/dev/null; then
        UPDATE_CSRF_DOMAIN=$(grep "^ALLOWED_HOSTS" .env | cut -d= -f2 | cut -d, -f1)
        if [ -n "$UPDATE_CSRF_DOMAIN" ]; then
            echo "CSRF_TRUSTED_ORIGINS=https://${UPDATE_CSRF_DOMAIN},http://${UPDATE_CSRF_DOMAIN}" >> .env
            echo -e "${GREEN}  ✓ Added CSRF_TRUSTED_ORIGINS to .env for ${UPDATE_CSRF_DOMAIN}${NC}"
        fi
    fi

    echo -e "${GREEN}  ✓ Code updated${NC}"

    # Rebuild only the web image
    echo -e "${YELLOW}  Rebuilding web image...${NC}"
    $DC build web
    echo -e "${GREEN}  ✓ Image rebuilt${NC}"

    # Restart web container only (zero-downtime: DB/redis keep running)
    echo -e "${YELLOW}  Restarting web container...${NC}"
    $DC up -d --no-deps web

    # Wait for web to be healthy
    MAX_WAIT=60
    WAITED=0
    WEB_READY=0
    while [ $WAITED -lt $MAX_WAIT ]; do
        STATUS=$(docker inspect --format='{{.State.Status}}' pamp-web-1 2>/dev/null \
                 || docker inspect --format='{{.State.Status}}' pamp_web_1 2>/dev/null \
                 || echo "unknown")
        if [ "$STATUS" = "running" ]; then
            if $DC logs web --tail=10 2>/dev/null | grep -q "Starting application\|Booting worker\|Listening at"; then
                echo -e "${GREEN}  ✓ Web container ready${NC}"
                WEB_READY=1
                break
            fi
        fi
        if [ "$STATUS" = "restarting" ]; then
            echo -e "${RED}  ERROR: Web container failed to start after update.${NC}"
            $DC logs web --tail=20
            echo -e "${YELLOW}  Rolling back to v${INSTALLED_VERSION}...${NC}"
            git reset --hard HEAD@{1}
            $DC build web
            $DC up -d --no-deps web
            echo -e "${RED}  Rolled back to v${INSTALLED_VERSION}. Check logs above for the error.${NC}"
            exit 1
        fi
        sleep 3
        WAITED=$((WAITED + 3))
        echo "  Still waiting... (${WAITED}s)"
    done

    if [ $WEB_READY -eq 0 ]; then
        echo -e "${YELLOW}  Warning: web container readiness check timed out — continuing anyway${NC}"
    fi

    # Run migrations (safe — only applies new ones)
    echo -e "${YELLOW}  Running database migrations...${NC}"
    $DC exec -T web python manage.py migrate --noinput \
        && echo -e "${GREEN}  ✓ Migrations applied${NC}" \
        || echo -e "${YELLOW}  ⚠ Migration step had warnings (check logs)${NC}"

    # Collect static files
    echo -e "${YELLOW}  Collecting static files...${NC}"
    $DC exec -T web python manage.py collectstatic --noinput -v 0 \
        && echo -e "${GREEN}  ✓ Static files updated${NC}"

    # Restart celery workers and nginx with new code
    echo -e "${YELLOW}  Restarting celery and nginx...${NC}"
    $DC up -d --no-deps celery celery-beat

    echo -e "${YELLOW}  Restarting nginx...${NC}"
    if $DC restart nginx 2>/dev/null; then
        sleep 3
        NGINX_STATUS=$(docker inspect --format='{{.State.Status}}' pamp_nginx 2>/dev/null || echo "unknown")
        if [ "$NGINX_STATUS" = "running" ]; then
            echo -e "${GREEN}  ✓ nginx restarted successfully${NC}"
        else
            echo -e "${YELLOW}  ⚠ nginx may have issues — check: docker compose logs nginx${NC}"
        fi
    else
        echo -e "${RED}  ⚠ nginx restart failed — check: docker compose logs nginx${NC}"
        echo -e "${YELLOW}  To recover, run:${NC}"
        echo -e "  sed \"s/PAMP_DOMAIN/\$(grep ALLOWED_HOSTS .env | cut -d= -f2 | cut -d, -f1)/g\" nginx.conf.template > nginx.conf && docker compose restart nginx"
    fi

    NEW_VERSION=$(cat VERSION 2>/dev/null || echo "$LATEST_VERSION")
    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}  ✓ PAMP updated to v${NEW_VERSION}${NC}"
    echo -e "${GREEN}  Your data and configuration are preserved.${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

do_uninstall() {
    # Check if PAMP is actually installed before proceeding
    if [ ! -f "/opt/pamp/.env" ] && ! docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "pamp"; then
        echo "PAMP is not installed on this server."
        exit 0
    fi

    read -p "This will DELETE all data including the database. Type 'yes' to confirm: " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        echo "Cancelled."
        exit 0
    fi

    echo "Uninstalling PAMP..."
    detect_compose
    cd /opt/pamp 2>/dev/null || true

    # Read domain before deleting files
    UNINSTALL_DOMAIN=""
    if [ -f ".env" ]; then
        UNINSTALL_DOMAIN=$(grep ALLOWED_HOSTS .env 2>/dev/null | cut -d= -f2 | cut -d, -f1 || true)
    fi

    # Stop and remove containers + volumes
    echo -e "${YELLOW}Stopping and removing containers and volumes...${NC}"
    $DC down -v 2>/dev/null || docker compose down -v 2>/dev/null || true

    # Remove any leftover named volumes
    docker volume rm pamp_mysql_data pamp_static_volume pamp_certbot_www 2>/dev/null || true

    # Remove SSL cert if domain found
    if [ -n "$UNINSTALL_DOMAIN" ]; then
        echo -e "${YELLOW}Removing SSL certificate for ${UNINSTALL_DOMAIN}...${NC}"
        certbot delete --cert-name "$UNINSTALL_DOMAIN" --non-interactive 2>/dev/null || true
    fi

    # Remove the directory
    cd /
    echo -e "${YELLOW}Removing /opt/pamp ...${NC}"
    rm -rf /opt/pamp

    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}  PAMP uninstalled successfully.${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# ── Main ──────────────────────────────────────────────────────────────────────

if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root: sudo bash install.sh${NC}"
    exit 1
fi

print_banner

echo ""
echo -e "${BLUE}  What would you like to do?${NC}"
echo ""
echo -e "  ${CYAN}1)${NC} Install PAMP"
echo -e "  ${CYAN}2)${NC} Update PAMP  ${YELLOW}(pull latest + rebuild + migrate)${NC}"
echo -e "  ${CYAN}3)${NC} Uninstall PAMP  ${RED}(removes everything)${NC}"
echo ""
read -p "  Enter choice [1-3]: " MENU_CHOICE
echo ""

case "$MENU_CHOICE" in
    1) do_install ;;
    2) do_update ;;
    3) do_uninstall ;;
    *) echo -e "${RED}Invalid choice. Run the script again and enter 1, 2, or 3.${NC}"; exit 1 ;;
esac
