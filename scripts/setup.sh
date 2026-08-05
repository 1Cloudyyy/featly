#!/bin/bash
# Featly v2.2 — Quick Setup Script
# Run this on a fresh Ubuntu 24 VPS

set -e

echo "=== Featly v2.2 Setup ==="

# Update system
echo "[1/6] Updating system..."
sudo apt update && sudo apt upgrade -y

# Install Python 3.12
echo "[2/6] Installing Python 3.12..."
sudo apt install -y python3.12 python3.12-venv python3.12-dev python3-pip

# Install PostgreSQL
echo "[3/6] Installing PostgreSQL..."
sudo apt install -y postgresql postgresql-contrib

# Setup database
echo "[4/6] Setting up database..."
sudo -u postgres psql -c "CREATE USER featly WITH PASSWORD 'featly';" 2>/dev/null || true
sudo -u postgres psql -c "CREATE DATABASE featly OWNER featly;" 2>/dev/null || true
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE featly TO featly;" 2>/dev/null || true

# Install Tesseract (for OCR)
echo "[5/6] Installing Tesseract..."
sudo apt install -y tesseract-ocr tesseract-ocr-eng

# Setup backend
echo "[6/6] Setting up backend..."
cd backend
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run migrations
alembic upgrade head 2>/dev/null || echo "Run 'alembic revision --autogenerate -m init' first"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Start backend:  cd backend && source venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000"
echo "Start engine:   cd engine && python -m engine.main"
echo ""
echo "Docker alternative: docker-compose up -d"
