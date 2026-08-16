#!/bin/bash
# Featly Hub — Production Deployment Script
# Run on VPS as root or with sudo

set -e

APP_DIR="/opt/featly"
REPO_URL="https://github.com/1Cloudyyy/featly.git"
DB_USER="featly"
DB_PASS="featly"
DB_NAME="featly"
WS_SECRET="${WS_SECRET:-$(openssl rand -hex 32)}"

echo "=== Featly Hub Deployment ==="

# 1. Create app user
echo "[1/7] Creating app user..."
id -u featly &>/dev/null || useradd -r -m -s /bin/bash featly

# 2. Clone/update repo
echo "[2/7] Cloning repository..."
if [ -d "$APP_DIR/.git" ]; then
    cd "$APP_DIR"
    git pull origin master
else
    git clone "$REPO_URL" "$APP_DIR"
fi
chown -R featly:featly "$APP_DIR"

# 3. Setup Python venv
echo "[3/7] Setting up Python environment..."
cd "$APP_DIR/hub"
sudo -u featly python3.12 -m venv venv 2>/dev/null || sudo -u featly python3 -m venv venv
sudo -u featly ./venv/bin/pip install -r requirements.txt

# 4. Setup PostgreSQL
echo "[4/7] Configuring PostgreSQL..."
sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';" 2>/dev/null || true
sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" 2>/dev/null || true
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;" 2>/dev/null || true

# 5. Database
echo "[5/7] Database — таблицы создаются автоматически (create_all в lifespan)"
# Если нужна миграция позже: alembic upgrade head

# 6. Create uploads directory
echo "[6/7] Setting up directories..."
sudo -u featly mkdir -p "$APP_DIR/hub/uploads"
sudo -u featly mkdir -p "$APP_DIR/hub/logs"

# 7. Install systemd service
echo "[7/7] Installing systemd service..."
cp "$APP_DIR/scripts/featly-hub.service" /etc/systemd/system/
sed -i "s|change-me-in-production|$WS_SECRET|g" /etc/systemd/system/featly-hub.service
systemctl daemon-reload
systemctl enable featly-hub
systemctl restart featly-hub

echo ""
echo "=== Deployment Complete ==="
echo ""
echo "Hub URL: http://$(hostname -I | awk '{print $1}'):8000"
echo "Health check: curl http://localhost:8000/health/detailed"
echo "WS Secret: $WS_SECRET"
echo ""
echo "Commands:"
echo "  systemctl status featly-hub"
echo "  journalctl -u featly-hub -f"
echo "  systemctl restart featly-hub"
