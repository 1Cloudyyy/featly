#!/bin/bash
# Featly Health Check — polls backend and sends alert if down
# Run via cron: */5 * * * * /opt/featly/scripts/health-check.sh

BACKEND_URL="http://localhost:8000/health/detailed"
LOG_FILE="/opt/featly/backend/logs/health-check.log"

check_backend() {
    response=$(curl -s -o /dev/null -w "%{http_code}" "$BACKEND_URL" 2>/dev/null)
    if [ "$response" != "200" ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') BACKEND DOWN (HTTP $response)" >> "$LOG_FILE"
        # Restart backend
        systemctl restart featly-backend
        echo "$(date '+%Y-%m-%d %H:%M:%S') Backend restarted" >> "$LOG_FILE"
    fi
}

check_backend
