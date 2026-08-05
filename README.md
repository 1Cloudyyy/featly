# Featly v2.2

Auto-delivery system for Roblox MM2 items via FunPay.

## Architecture

```
FunPay → Plugin (funpay-universal) → Backend (FastAPI) → Engine (Windows)
```

- **Plugin** — module for funpay-universal, handles FunPay events and Telegram commands
- **Backend** — FastAPI server with REST API and WebSocket for Engine communication
- **Engine** — Windows automation (OpenCV, pydirectinput, mss) for MM2 trades

## Quick Start

### Docker (recommended)

```bash
docker-compose up -d
```

### Manual Setup

```bash
# Backend (Linux VPS)
cd backend
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Engine (Windows)
cd engine
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m engine.main
```

### VPS Setup Script

```bash
bash scripts/setup.sh
```

## Project Structure

```
featly/
├── plugin/          # Featly Plugin (funpay-universal module)
│   ├── core/        # Roblox API, Backend client, Order manager
│   ├── handlers/    # FunPay and Telegram event handlers
│   └── utils/       # Alerts utilities
├── backend/         # Featly Backend (FastAPI)
│   ├── app/
│   │   ├── models/  # SQLAlchemy models
│   │   ├── routes/  # REST API endpoints
│   │   ├── ws/      # WebSocket server
│   │   └── services/# Business logic
│   └── alembic/     # Database migrations
├── engine/          # Windows Engine
│   ├── profiles/    # Game-specific configs (YAML)
│   ├── templates/   # OpenCV template images
│   └── proofs/      # Trade proof screenshots
├── docs/            # Architecture documentation
└── scripts/         # Setup scripts
```

## API Endpoints

### REST API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /health | Health check |
| GET | /health/detailed | Detailed health (DB status) |
| POST | /orders | Create order |
| GET | /orders | List active orders |
| GET | /orders/:id | Get order |
| PATCH | /orders/:id/status | Update order status |
| GET | /pending_trades | List pending trades |
| POST | /pending_trades | Create pending trade |
| DELETE | /pending_trades/:id | Delete pending trade |
| GET | /inventory | List inventory |
| PATCH | /inventory/:item | Update item |
| GET | /bots | List bots |
| PATCH | /bots/:id/heartbeat | Bot heartbeat |

### WebSocket (Engine)

```json
// Auth
{"secret": "...", "bot_id": "bot_main"}

// Heartbeat
{"type": "heartbeat", "bot_id": "bot_main"}

// Trade completed
{"type": "trade_completed", "order_id": 1, "success": true}
```

## Configuration

### Backend

Environment variables (prefix `FEATLY_`):

- `FEATLY_DATABASE_URL` — PostgreSQL connection string
- `FEATLY_WS_SECRET` — WebSocket authentication secret
- `FEATLY_CORS_ORIGINS` — Allowed CORS origins

### Engine

Edit `engine/profiles/mm2.yaml` for screen regions and trade flow settings.

## Tech Stack

- Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, asyncpg
- OpenCV, pydirectinput-rgx, mss, pytesseract, PyWinCtl
- PostgreSQL 15, Docker
- GitHub Actions CI (ruff + mypy)
