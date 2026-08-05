# Changelog — Featly v2.2

> Все значимые изменения проекта фиксируются здесь.

---

## [0.0.0] — 2025-08-05

### Начало проекта
- Проанализированы документы: FEATLY_v2_2_final(1).md, FEATLY_v2_2_repo_analysis.md
- Загружен system prompt (FEATLY_AI_PROMPT.md)
- Определена структура проекта (plugin / backend / engine)
- Выбран стек: FastAPI, pydirectinput-rgx, mss, PyWinCtl
- Созданы dev_notes.md и changelog.md

## [0.1.0] — 2026-08-05

### Добавлено
- Подробный роадмап разработки в dev_notes.md (7 фаз, ~25-35 дней до MVP)
- Определены критические зависимости между фазами

## [1.0.0] — 2026-08-05

### Фаза 0: Инфраструктура
- Инициализирован git-репозиторий (приватный: github.com/1Cloudyyy/featly)
- Создана структура проекта: plugin/, backend/, engine/, docs/, .github/
- Настроен pyproject.toml (ruff + mypy + black)
- Настроен GitHub Actions CI (lint + typecheck)
- Настроен Alembic для async PostgreSQL
- Созданы requirements.txt для каждого компонента
- Перенесена документация в docs/

## [2.0.0] — 2026-08-05

### Фаза 1: Backend
- SQLAlchemy модели: Order, PendingTrade, InventoryItem, Bot, TradeLog
- Pydantic схемы для API
- REST routes: /orders, /pending_trades, /inventory, /bots
- WebSocket сервер: auth, heartbeat, waitlist sync
- Service layer: order_service, inventory_service

### Фаза 2: Plugin
- meta.py, settings.py, data.py
- core/roblox_api.py — validate username, request friendship, CSRF
- core/backend_client.py — REST клиент к бэкенду
- core/order_manager.py — lifecycle заказов, диалог в чате
- handlers/funpay.py — обработчики ивентов
- handlers/telegram.py — роутеры aiogram 3
- utils/alerts.py — Telegram алерты

## [3.0.0] — 2026-08-05

### Фаза 3: Windows Engine
- config.py — загрузка конфигурации из YAML
- ws_client.py — WebSocket клиент (auth, heartbeat, реконнект)
- screen_capture.py — скриншоты через mss
- cv_matcher.py — OpenCV template matching
- input_controller.py — клики/клавиатура через pydirectinput-rgx
- waitlist_manager.py — локальный кэш waitlist
- trade_flow.py — автоматика выдачи (скан → accept → items → confirm)
- anti_afk.py — анти-АФК
- reconnect.py — авто-реконнект при кике
- profiles/mm2.yaml — координаты окон MM2
- main.py — точка входа

## [4.0.0] — 2026-08-05

### Фаза 4: OCR + Tests + Docker
- ocr.py — pytesseract для чтения ников и текста
- trade_flow.py — улучшен (OCR ников, proof-скриншоты, error handling)
- backend/tests/ — pytest конфигурация и тесты
- engine/tests/ — тесты config, waitlist
- backend/Dockerfile — контейнер для бэкенда
- docker-compose.yml — PostgreSQL + Backend

## [5.0.0] — 2026-08-05

### Фаза 5: Integration + E2E Tests
- backend/tests/test_integration.py — full order lifecycle test
- backend/tests/test_ws.py — WebSocket auth and heartbeat tests
- backend/tests/test_e2e.py — end-to-end trade flow simulation
- health/detailed — DB health check endpoint
- scripts/setup.sh — VPS quick setup script
- README.md — project documentation

## [6.0.0] — 2026-08-05

### Фаза 6: Полировка + деплой
- scripts/featly-backend.service — systemd unit для автозапуска
- scripts/deploy-backend.sh — one-click деплой на VPS
- scripts/featly-engine-task.xml — Windows Task Scheduler для Engine
- scripts/install-engine-task.bat — установка автозапуска Engine
- scripts/health-check.sh — health check polling + auto-restart
- scripts/featly-logrotate.conf — лог-ротация
- README.md — инструкции по деплою
