# Featly

Auto-delivery system for Roblox MM2 items via FunPay.

> Текущая версия: **v2.2** (работает). Следующая версия **v3** — в разработке:
> Telegram-панель вместо React-админки, авто-заполнение «Наличия» в лотах FunPay,
> SQLite вместо PostgreSQL. Концепт: [`docs/FEATLY_v3_CONCEPT.md`](docs/FEATLY_v3_CONCEPT.md).

## Architecture

```
FunPay → Plugin (funpay-universal) → Backend (FastAPI) → Engine (Windows)
```

- **Plugin** — module for funpay-universal, handles FunPay events and Telegram commands
- **Backend** — FastAPI server (REST + WebSocket for Engine), центр управления (waitlist, инвентарь)
- **Engine** — Windows automation (OpenCV, pydirectinput, mss) for MM2 trades

## Quick Start

### Docker (recommended)

```bash
docker-compose up -d
```

### Manual Setup

```bash
# Hub (Linux VPS)
cd hub
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
# Таблицы в БД создаются автоматически при старте (Base.metadata.create_all в lifespan)

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
│   ├── core/        # Roblox API, Hub client, Order manager
│   ├── handlers/    # FunPay and Telegram event handlers
│   └── utils/       # Alerts utilities
├── hub/             # Featly Hub (FastAPI) — центр управления
│   ├── app/
│   │   ├── models/  # SQLAlchemy models
│   │   ├── routes/  # REST API endpoints
│   │   ├── ws/      # WebSocket server
│   │   └── services/# Business logic
│   └── tests/
├── engine/          # Windows Engine
│   ├── profiles/    # Game-specific configs (YAML)
│   ├── templates/   # OpenCV template images
│   └── proofs/      # Trade proof screenshots
├── legacy/web-admin # React-админка (не в compose, «на антресоль»)
├── docs/            # Документация (концепт v3, legacy-доки)
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
| POST | /inventory | Create/update item (upsert) |
| PATCH | /inventory/:item | Update item |
| DELETE | /inventory/:item | Delete item |
| GET | /bots | List bots |
| PATCH | /bots/:id/heartbeat | Bot heartbeat |
| GET | /stats | Статистика (заказы, выданные сегодня, waitlist, движки) |
| GET/PATCH | /settings | Настройки hub (TG-алерты, порог офлайна) — из Telegram-панели |
| GET | /settings/secrets | Секреты (ws_secret, api_key) для настройки движка |

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

### Hub

Environment variables (prefix `FEATLY_`):

- `FEATLY_DATABASE_URL` — SQLite (по умолчанию `sqlite+aiosqlite:///./featly.db`) или PostgreSQL
  (`postgresql+asyncpg://...`)
- `FEATLY_WS_SECRET` — WebSocket authentication secret
- `FEATLY_API_KEY` — REST API key (X-API-Key, обязателен для плагина и админки)
- `FEATLY_CORS_ORIGINS` — Allowed CORS origins

### Engine

Edit `engine/profiles/mm2.yaml` for screen regions and trade flow settings.

## Tech Stack

- Python 3.12, FastAPI, SQLAlchemy 2.0
- SQLite (по умолчанию) / PostgreSQL (опционально), асинхронный драйвер aiosqlite/asyncpg
- OpenCV, pydirectinput-rgx, mss, pytesseract, PyWinCtl
- GitHub Actions CI (ruff + mypy)

## Deployment

### VPS (Hub — SQLite по умолчанию)

```bash
# One-click deploy
bash scripts/deploy-hub.sh

# Or manual
cd /opt/featly/hub
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Windows (Engine)

```bash
# Install auto-start task
scripts\install-engine-task.bat

# Or run manually
cd engine
python -m engine.main
```

### Health Check

```bash
# Check hub
curl http://localhost:8000/health/detailed

# Setup cron (every 5 min)
echo "*/5 * * * * /opt/featly/scripts/health-check.sh" | crontab -
```

### Logs

```bash
# Hub logs
journalctl -u featly-hub -f

# Engine logs
tail -f engine/logs/engine_*.log
```

## Dev & Docs

- [`docs/FEATLY_v3_CONCEPT.md`](docs/FEATLY_v3_CONCEPT.md) — концепт v3 (архитектура, панель, роадмап)
- [`changelog.md`](changelog.md) — журнал изменений
- [`dev_notes.md`](dev_notes.md) — архитектурные решения и технические заметки

Значимые изменения фиксируются коммитом + записями в качестве сопроводительной документации.
