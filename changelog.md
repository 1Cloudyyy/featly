# Changelog — Featly

> Все значимые изменения проекта фиксируются здесь.

---

## [9.1.0] — 2026-08-16 (v3 «полировка»)

### Эшо B — полная настройка hub из Telegram (коммит `…`)
- **Hub**: таблица `app_settings` (key→value) + `GET /settings` / `PATCH /settings`
  (auth — api-key; неизвестные ключи отклоняются), `GET /settings/secrets`
- **Применение без рестарта**: фоновый `engine_offline_watcher` (раз в 60 с) — если движок
  offline дольше `engine_offline_threshold`, шлёт TG-алерт (`telegram_bot_token` +
  `telegram_alert_chat_id`; throttle 10 мин на движок) — мини-реализация H3 из аудита
- **Панель**: новый экран «🏠 Hub» (редактирование 3 ключей через FSM `hub_value`);
  «🔑 Подключения» — одноразовый показ `WS_SECRET`/`API_KEY` + готовый env-блок для движка
  (Mini-ПК); главное меню дополнено
- **«⚙️ Настройки» расширены**: `backend_ws_url`, `alert_on_zero` (вкл/выкл)
- `backend_client`: `get_hub_settings`, `update_hub_settings`, `get_secrets`
- hub requirements: добавлен `aiohttp` (TG-алерты)

---

### Эшо A–C первой серии: X-API-Key + умная автовыдача (коммит `…`)
- **A1–A2 — плагин авторизуется в hub**: `X-API-Key` из настроек (`settings.json → api_key`);
  при пустом ключе — лог-предупреждение (без ключа hub отвечает 403)
- **C1 — настройки выдачи**: `add_friends` (запрос в друзья вкл/выкл), `nickname_source`
  (`auto` | `auto_trusted` | `ask`) в `settings.json` + панель
- **C2–C4 — ник из «Имя персонажа» `Order.player`** (поле обязательно на FunPay):
  - `auto` — берём из заказа, требуем подтверждение «Да»;
  - `auto_trusted` — если ник найден в Roblox 1-в-1, финализируем без вопросов;
  - `ask` — всегда запрашиваем;
  - плюс мягкая проверка ника при подтверждении (не блокирует, лог-предупреждение)
- **`add_friends=false`**: заявка в друзья пропускается (логируется), подтверждение ника —
  остаётся (нужно для матчинга выдачи)
- **C5 — панель**: новый экран «🚀 Автовыдача» (toggle друзей, цикл режимов ника);
  поле `api_key` добавлено в «⚙️ Настройки» (скрыт показ: 🟢/🔴)
- Рефакторинг диалога: `_finish_dialog()` — единая финализация (заявка/заказ/waitlist/сообщения)

---

### Роадмап v3.1 создан
- `docs/ROADMAP_v3.1.md` — план релизного цикла: полная настройка из Telegram (эшо A–B),
  умная автовыдача с «Имя персонажа» (эшо C), закрытие аудита Kimi (эшо A/B), двое решений
  продавца: поле «Имя персонажа» обязательно (ник из `Order.player`) + режим `auto_trusted`
- Ключевой блокер: плагин пока НЕ шлёт `X-API-Key` — первая задача (A1)

### Роадмап v3 завершён + полировка
- **Все базовые шаги v3 (0–6) выполнены** — roadmap концепта обновлён
- **`!смена` теперь рабочий**: валидация ника → подтверждение («Да») → `PATCH /orders/{id}/nickname`
  обновляет заказ и waitlist в hub; движок подхватывает новый ник при пулле (~15 с).
  В кэш заказа добавлен `chat_id` (поиск `find_by_chat`)
- **Уникальность `pending_trade`**: `UniqueConstraint(order_id, bot_id)` — защита от дублей в waitlist
- **`orders_cache` стал thread-safe** (`threading.Lock` вокруг всех операций)
- Hub: новая схема `OrderNicknameUpdate`; эндпоинт отклоняет смену ника для терминальных заказов

---

## [9.0.0] — 2026-08-16 (v3 в разработке)

### Шаг 6 — poll waitlist + готовность к Mini-ПК (коммит `…`)
- **Engine сам перезапрашивает waitlist** (poll) каждые `waitlist_sync_interval` (по умолчанию 15 с,
  первый запрос через 2 с после коннекта) — схема самовосстанавливающаяся, без очередей
- Hub: удалены `message_queue`/`_flush_queued_messages`/`queue_pending_trade` и команда `WAIT_FOR_TRADE`;
  `send_to_engine` — только прямая отправка
- Оставлен быстрый сигнал **`REMOVE_WAITLIST`** при отмене/удалении заказа (чтобы не выдать
  товар за отменённый заказ в окне до следующего пулла)
- `FORCE_TRADE` при офлайн-движке теперь честно возвращает `ok=false` (панель сообщает
  «движок офлайн» вместо «в очереди»)
- Mini-ПК готовность: движок полностью конфигурируется env (`FEATLY_WS_URL`, `FEATLY_BOT_ID`,
  `FEATLY_WS_SECRET`) — несколько инстансов на машине выдачи с уникальными `bot_id`

---

### Шаг 5 — SQLite по умолчанию, лёгкий бэкенд (коммит `…`)
- **SQLite** — БД по умолчанию (`sqlite+aiosqlite:///./featly.db`), PostgreSQL — опционально
  (через `FEATLY_DATABASE_URL` / `USE_POSTGRES=1`)
- Новый тип **`TZDateTime`** (SQLite хранит naive UTC, отдаёт aware UTC; PostgreSQL без изменений) —
  применён во всех моделях; проверено смоук-тестом (create_all, server_default, запрос статистики)
- `db.py`: `check_same_thread=False` для SQLite
- **Alembic удалён** (пустые версии, таблицы создаёт `create_all` в lifespan)
- `hub/requirements.txt`: добавлен `aiosqlite`
- Деплой: `featly-hub.service` без зависимости от PostgreSQL, SQLite в `ReadWritePaths`;
  `deploy-hub.sh` — шаг БД опционален (SQLite по умолчанию)
- `.env.example`/README актуализированы (SQLite — дефолт)

---

### Шаг 4 — принудительная выдача и отмена заказов (коммит `…`)
- **Hub**: `POST /orders/{id}/force` (FORCE_TRADE движку, с очередь при офлайне)
  и `POST /orders/{id}/cancel` (CANCELLED + удаление pending_trades + REMOVE_WAITLIST;
  409 для завершённых заказов)
- **Engine**: обработка команды `FORCE_TRADE` (поиск заказа в локальном waitlist →
  при отсутствии синхронизация с hub → kick); `trade_flow.kick_scan()` — немедленное
  пересканирование вместо ожидания интервала; `waitlist_manager.find_by_order_id`
- **Панель**: у каждого заказа кнопки «⚡ Выдать» / «❌ Отменить» / «🗑 Убрать из waitlist»;
  отмена с FSM-подтверждением («да»/«нет»)
- `/force_trade <id>` в Telegram теперь реальный (раньше — заглушка)
- Исправлено: `DELETE /pending_trades/{id}` теперь уведомляет движок (REMOVE_WAITLIST)
- Все операции логируются (кто, id заказа, результат/ошибка)

---

### Шаг 3 — авто-заполнение «Наличия» лотов FunPay (коммит `…`)
- Новый `plugin/core/lots_sync.py`: авто-поиск лота по названию (`FunPayBot.get_lot_by_title`
  + fallback fuzzy по своим лотам), обновление `amount`/`active` через
  `account.get_lot_fields`/`save_lot`, кэш привязок `item_key → lot_id` в `lot_map`
- Панель: кнопки «🛍 Синхронизировать лот» (авто-поиск + применение наличия)
  и «📎 Привязать лот вручную» (ввод lot_id, FSM)
- Автосинк при добавлении предмета и изменении количества (настройка `autosync_lots`,
  по умолчанию вкл; отключается в панели)
- `settings.json` теперь создаётся при включении модуля (`ensure_settings`) с дефолтами
  и лог-подсказкой про `admin_tg_id` — файл больше не «появляется сам по себе»
- Все шаги синка логируются (поиск → найден/не найден → наличие → результат)

---

### Шаг 1 — Telegram-панель `/admin` (коммит `…`)
- Новый `plugin/handlers/telegram_admin.py`: панель с экранами
  **движок / инвентарь / заказы / статистика / настройки / диагностика**
  (каркас — aiogram Router + FSM + кнопки с текущими значениями, паттерн playerok)
- Инвентарь: ✅ добавление предмета (FSM: key → name → count → порог),
  изменение количества/порога, удаление; предупреждение ⚠️ при `count <= threshold`
- Заказы: список waitlist + «убрать из waitlist» (удаление pending_trade)
- Статистика: новый hub-эндпоинт **`GET /stats`** (всего/выполнено/сегодня/отмены/waitlist/движки)
- Настройки: редактирование полей из settings.json через FSM (включая `admin_tg_id` —
  включается вручную в файле модуля)
- Диагностика: проверка hub, cookie, статуса движка
- Ограничение доступа: только `admin_tg_id` (лог-запись при чужих вызовах)
- **Hub**: новый `routes/stats.py`; `POST /inventory` (upsert) и `DELETE /inventory/{item_key}`;
  `InventoryCreate`/`StatsResponse` схемы; версия API → 3.0.0
- `backend_client`: методы `get_stats`, `upsert_item`, `delete_item`, `update_item_count`,
  `update_item_threshold`
- Все действия панели логируются (кто, что, результат)

---

### Шаг 0 — миграция плагина на интерфейс funpay-universal 1.17 (коммит `…`)
- Плагин переписан со старого интерфейса (`EVENT_HANDLERS`, `TELEGRAM_ROUTERS`, `(deal, acc)`)
  на новый: **`BOT_EVENT_HANDLERS`** / **`FUNPAY_EVENT_HANDLERS`** (ключи — enum `EventTypes`) /
  **`TELEGRAM_BOT_ROUTERS`**; хендлеры теперь принимают `(bot, event)`, отправка через `bot.send_message()`
- События: `NEW_MESSAGE` (диалоги+команды+системные сообщения), `NEW_ORDER` (оплаченный заказ → старт диалога),
  `ORDER_STATUS_CHANGED` (CLOSED→completed, REFUNDED→cancelled); системные сообщения чата
  (`ORDER_CONFIRMED`, `REFUND`, `PARTIAL_REFUND`) обрабатываются в `order_manager`
- `meta.py`: `VERSION = 3.0.0`, имя модуля `featly` (PREFIX используется как тег)
- **Полное логирование на каждом этапе** (`logging` + loguru-совместимость):
  жизненный цикл модуля, каждое событие FunPay, шаги диалога покупателя,
  HTTP-вызовы hub (метод/URL/статус/длительность/текст ошибки), Roblox API
  (CSRF, резолв ника, заявка), все TG-команды, кэш заказов
- `backend_client`: единый метод `_request` с трейсингом; новые методы `health`, `get_pending_trades`,
  `set_item_threshold`, `get_bot`
- `!отмена` получила реальный флоу (FSM-подтверждение → отмена заказа в hub); `!смена`/`!статус`/`!фото` — логируются с явным TODO

---

## [8.0.0] — 2026-08-16

### Рефакторинг структуры (шаг 0a v3, коммит `…`)
- `backend/` → **`hub/`** (центр управления); обновлены все ссылки: CI, pyproject, docker-compose, Dockerfile, scripts
- `admin/` → **`legacy/web-admin/`**; admin-сервис убран из docker-compose (панель → Telegram в v3)
- Старые документы перенесены в **`docs/legacy/`**: аудиты v2.2, repo-анализ, AI-промпт
- Скрипты деплоя: `deploy-backend.sh` → `deploy-hub.sh`, systemd-юнит `featly-hub.service`,
  health-check/logrotate переведены на `/opt/featly/hub/` и `featly-hub`
- Добавлен **`.env.example`** (единая точка правды по секретам)
- `setup.sh`: убран вызов alembic (таблицы создаются через `create_all` в lifespan)

### Исправлено (аудит v2.2, коммит `3040cdd`)
- Engine: зарегистрированы callbacks `on_trade_completed`/`on_trade_failed` → `ws_client.report_*` (замыкание цикла «выдача → уведомление бэкенда»)
- Backend WS: починен keepalive (`ws` → `websocket`, был NameError), добавлена очередь сообщений для офлайн-движка, доставка накопленного при реконнекте
- Backend: оповещение движка о новых/удалённых `pending_trade` (`WAIT_FOR_TRADE`/`REMOVE_WAITLIST`)
- Backend: `trade_completed` — валидация переходов статуса, списание инвентаря, удаление из waitlist только при успехе (политика retry при фейле)
- Backend: `create_all` при старте в `lifespan` (таблицы создаются без Alembic), `engine.dispose()` на shutdown
- Admin: передача `X-API-Key` (из `VITE_API_KEY`), прокинут в docker-compose
- Engine: `waitlist_manager` обновляется по `WAIT_FOR_TRADE`/`REMOVE_WAITLIST` (фактически предыдущий путь был мёртвым)
- CI/mypy: `callable` → `Callable` аннотации

### Документация и направление v3
- Создан `docs/FEATLY_v3_CONCEPT.md` — концепт новой версии:
  - Архитектура: VDS-центр (плагин + hub) + движки на Mini-ПК через WS
  - Панель админки → Telegram (вместо React)
  - Автозаполнение «Наличия» в лотах FunPay (авто-поиск лота по названию)
  - SQLite вместо PostgreSQL, poll вместо push
  - **Выявлена несовместимость плагина с последней версией funpay-universal (1.17)**:
    старая модель `EVENT_HANDLERS`/`(deal, acc)` → новая `FUNPAY_EVENT_HANDLERS`/`(bot, event)` — шаг 0 миграции
  - Целевая структура файлов: `backend/` → `hub/`, React-админка → `legacy/web-admin/`, один репозиторий
- Решения продавца (2026-08-16): плагин на VDS; Telegram-админка — достаточно; Mini-ПК под будущую инфраструктуру

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

## [7.0.0] — 2026-08-05

### Фаза 7: Админка
- React + Vite + TailwindCSS
- Страница заказов (таблица + фильтры по статусу)
- Страница инвентаря (CRUD)
- Страница ботов (статус, pending trades)
- Страница статистики (активные/выполненные/отменённые)
- API клиент для бэкенда
- Dockerfile + nginx.conf
- Добавлен в docker-compose (порт 3000)
