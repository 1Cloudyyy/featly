#!/bin/bash
# Featly Health Check — polls hub and sends alert if down
# Run via cron: */5 * * * * /opt/featly/scripts/health-check.sh

BACKEND_URL="http://localhost:8000/health/detailed"
LOG_FILE="/opt/featly/hub/logs/health-check.log"

check_backend() {
    response=$(curl -s -o /dev/null -w "%{http_code}" "$BACKEND_URL" 2>/dev/null)
    if [ "$response" != "200" ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') HUB DOWN (HTTP $response)" >> "$LOG_FILE"
        # Restart hub
        systemctl restart featly-hub
        echo "$(date '+%Y-%m-%d %H:%M:%S') Hub restarted" >> "$LOG_FILE"
    fi
}

check_backend
