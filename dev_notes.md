# Dev Notes — Featly

> Заметки по разработке, архитектурные решения, полезная информация.
> v2.2 работает; направление v3 зафиксировано в `docs/FEATLY_v3_CONCEPT.md`.

---

## Структура проекта — целевая (v3, решения 2026-08-16)

```
featly/
├── README.md
├── pyproject.toml              # ruff/mypy/black для всего Python
├── .env.example                # все секреты (FEATLY_API_KEY, WS_SECRET, TG_ID...)
├── docs/
│   ├── FEATLY_v3_CONCEPT.md    # концепт v3 (архитектура, панель, роадмап)
│   └── legacy/                 # старые v2-документы (аудиты, анализ)
│
├── plugin/                     # модуль funpay-universal 1.17 (имя = featly)
│   ├── __init__.py             # BOT/FUNPAY/TELEGRAM_BOT_ROUTERS-хендлеры
│   ├── meta.py  settings.py  data.py
│   ├── handlers/
│   │   ├── funpay.py           # события сделок/сообщений
│   │   └── telegram_admin.py   # панель (ФCМ-экраны)
│   └── core/
│       ├── backend_client.py   # REST к hub
│       ├── roblox_api.py       # ник → id, заявка в друзья
│       └── lots_sync.py        # авто-поиск лота + «Наличие»
│
├── hub/                        # «центр управления» (бывший backend; SQLite)
│   ├── app/  (models/ routes/ services/ ws/ main.py)
│   └── tests/
│
├── engine/                     # Windows Engine
│   ├── main.py  trade_flow.py  ws_client.py  cv_matcher.py  ...
│   └── profiles/ templates/ tests/
│
├── legacy/web-admin/           # React-админка «на антресоль» (вне compose)
└── scripts/                    # systemd, планировщик, logrotate
```

> Решения: `backend/` → `hub/`; React-админка → `legacy/web-admin/`; один git-репозиторий.
> ✅ **Шаг 0a выполнен 2026-08-16** — структура перестроена (коммит ниже в changelog).

---

## Архитектурные решения

### 2025-08-05
- Бэкенд: **FastAPI** (Python) — единый стек с плагином, авто-документация Swagger
- Клики в Engine: **pydirectinput-rgx** — Scan Codes, DirectX-совместимость
- Скриншоты: **mss** — 30-60 FPS, нативный NumPy
- Управление окном: **PyWinCtl** — watchdog, alwaysOnTop
- Плагин интегрируется в **funpay-universal** через систему модулей

---

## Технические заметки

### Roblox API — request-friendship
- Endpoint: `POST https://friends.roblox.com/v1/users/{userId}/request-friendship`
- Требует CSRF-токен (получается через pre-flight GET)
- Cookie `.ROBLOSECURITY` — только для API, не для игры
- При 401 — cookie протух, нужен /roblox_cookie

### Windows Engine — скриншоты
- `mss.grab()` → NumPy array (BGRA) → `cv2.cvtColor(BGRA2BGR)`
- Для matchTemplate лучше сразу grayscale
- Шаблоны хранятся в `engine/templates/`

### funpay-universal — интеграция (проверено по коду release 1.17)
- ✅ **Шаг 0 — миграция плагина на интерфейс 1.17 выполнена 2026-08-16**:
  - было: `EVENT_HANDLERS`, `TELEGRAM_ROUTERS`, хендлеры `(deal, acc)`, `acc.send_message(...)`
  - стало: `BOT_EVENT_HANDLERS` (`ON_MODULE_ENABLED`/`ON_MODULE_DISABLED`/`ON_TELEGRAM_BOT_INIT`),
    `FUNPAY_EVENT_HANDLERS` (ключи — enum `EventTypes`), `TELEGRAM_BOT_ROUTERS`,
    хендлеры `(bot: FunPayBot, event)`, отправка через `bot.send_message(chat_id, text)` (sync)
- **События в коде 1.17:** регистрируются `NEW_MESSAGE`, `NEW_ORDER`, `ORDER_STATUS_CHANGED`.
  README заявляет `NEW_DEAL`/`ITEM_PAID`/`DEAL_CONFIRMED`/`DEAL_ROLLED_BACK` — этих членов
  НЕТ в бандле `EventTypes`; вместо них: `NEW_ORDER` = оплата товара, подтверждение/возврат
  ловим через системные сообщения чата (`MessageTypes.ORDER_CONFIRMED`/`REFUND`) и `ORDER_STATUS_CHANGED`
- Доступ к аккаунту: `from fpbot.funpaybot import get_funpay_bot` → `get_funpay_bot().account`;
  чат покупателя ищется через `account.get_chat_by_name(buyer_username, True)`
- Авто-поиск лота: в `FunPayBot` уже есть `get_lot_by_title(title, subcategory_id=None)`.
  Изменение «Наличия»: `account.get_lot_fields(lot_id)` → `fields.amount = n` → `account.save_lot(fields)`;
  при `count == 0` → `fields.active = False`.
- Telegram-роутеры модуля сливаются с роутером бота → префиксы callback'ов уникальные (`featly_*`)
- Плагин = папка-модуль (в v3 — `plugin/` в корне репо, устанавливается ботом как модуль `featly`)

### Telegram-панель (шаг 1, выполнена 2026-08-16)
- `plugin/handlers/telegram_admin.py`, команда `/admin`, доступ только по `admin_tg_id`
- Экраны: движок / инвентарь (CRUD FSM) / заказы (waitlist) / статистика / настройки / диагностика
- Hub-эндпоинты панели: `GET /stats`, `POST /inventory`, `DELETE /inventory/{key}`
- Callback-префикс: `cb:*`; FSM-стейты `PanelStates`

---

## Журнал обязательного сопровождения

Чтобы проект не расходился с реальностью, при каждой заметной работе обновляются:
1. **git-коммит** — каждое изменение;
2. **`changelog.md`** — запись о значимых изменениях (дата + версия/подсистема);
3. **`dev_notes.md`** — архитектурные факты, решения, открытые вопросы;
4. **`README.md`** — структура, быстрый старт, конфигурация;
5. идеально — push на GitHub после коммита.

---

## Роадмап разработки

### Фаза 0. Инфраструктура (1-2 дня)
- Инициализировать git-репозиторий, `.gitignore`, структуру папок
- Создать `pyproject.toml` или `requirements.txt` по компонентам
- Поднять PostgreSQL (локально или VPS) + Alembic-миграции (базовые таблицы)
- Настроить GitHub Actions (CI: lint + typecheck на каждый PR)
- Настроить `ruff` + `mypy` + `black` (конфиг в `pyproject.toml`)

### Фаза 1. Backend — ядро (3-5 дней)
**Зачем:** Бэкенд — центральная точка связи. Без него плагин и Engine не могут обмениваться данными.

- [ ] `backend/app/config.py` — Pydantic Settings (DATABASE_URL, WS_SECRET, CORS)
- [ ] `backend/app/models/` — SQLAlchemy 2.0 модели:
  - `order.py` (orders, pending_trades)
  - `inventory.py` (inventory)
  - `bot.py` (bots)
  - `trade_log.py` (trade_logs)
- [ ] `backend/app/routes/` — REST эндпоинты:
  - `POST /orders` — создать заказ
  - `PATCH /orders/{id}/status` — обновить статус
  - `GET /pending_trades` — список ожидания
  - `DELETE /pending_trades/{id}` — удалить из ожидания
  - `GET /inventory` — инвентарь
  - `PATCH /inventory/{item}` — обновить кол-во
  - `POST /proofs` — загрузить скриншот
- [ ] `backend/app/ws/` — WebSocket сервер:
  - Auth + heartbeat (30s)
  - Команды: `WAIT_FOR_TRADE`, `REMOVE_WAITLIST`, `FORCE_TRADE`, `SCREENSHOT`
  - События: `trade_completed`, `trade_failed`, `screenshot_taken`
- [ ] `backend/alembic/` — миграции для всех таблиц
- [ ] Тесты: CRUD-тесты для каждого эндпоинта

### Фаза 2. Plugin — каркас (3-4 дня)
**Зачем:** Плагин — мозг системы. Обрабатывает ивенты FunPay, управляет диалогами, шлёт команды на бэкенд.

- [ ] Структура модуля `modules/featly/`:
  - `__init__.py` — точка входа, event handlers
  - `meta.py` — PREFIX, VERSION, NAME
  - `settings.py` — пороги, URL бэкенда
  - `data.py` — кэш заказов, cookie
- [ ] `core/roblox_api.py` — aiohttp-клиент:
  - `validate_username(nick)` → userId
  - `request_friendship(userId)` с CSRF-handling
  - Обработка 401 (протухший cookie)
- [ ] `core/backend_client.py` — REST-клиент к бэкенду:
  - Все эндпоинты из Фазы 1
- [ ] `core/order_manager.py` — логика заказов:
  - Состояния: `new → dialog → waiting_trade → delivering → completed`
  - Диалог в чате FunPay
- [ ] `handlers/funpay.py` — обработчики ивентов:
  - `NEW_DEAL` → `start_dialog()`
  - `NEW_MESSAGE` → `parse_commands()`
  - `ITEM_PAID` → `create_order()`
  - `DEAL_CONFIRMED` → `archive_order()`
  - `DEAL_ROLLED_BACK` → `cancel_order()`
- [ ] `handlers/telegram.py` — роутеры aiogram 3:
  - `/roblox_cookie`, `/stock`, `/orders`, `/force_trade`
  - `/engine_status`, `/engine_restart`
- [ ] Команды чата FunPay: `!смена`, `!фото`, `!помощь`, `!отмена`, `!статус`

### Фаза 3. Engine — каркас (3-4 дня)
**Зачем:** Windows Engine — руки бота. Кликает, скриншотит, общается с бэкендом.

- [ ] `engine/config.py` — Pydantic Settings (WS_URL, WS_SECRET, regions)
- [ ] `engine/ws_client.py` — WebSocket-клиент:
  - Auth + heartbeat (30s)
  - Обработка команд от бэкенда
  - Авто-реконнект
- [ ] `engine/screen_capture.py` — скриншоты через `mss`:
  - `capture_screen()` → NumPy array (BGRA)
  - Конвертация BGRA→BGR для OpenCV
- [ ] `engine/cv_matcher.py` — компьютерное зрение:
  - `detect_template(screenshot, template_path)` → bool + координаты
  - `wait_for_template(template, timeout)` → координаты
- [ ] `engine/input_controller.py` — клики/клавиатура:
  - `click(x, y)`, `type_text(text)`, `press_key(key)`
  - Все через `pydirectinput-rgx`
- [ ] `engine/templates/` — шаблоны для MM2:
  - `reconnect_button.png`, `trade_request_notification.png`
  - `mm2_hud.png`, `accept_button.png`
  - `search_box.png`, `you_have_accepted.png`
- [ ] `engine/profiles/mm2.yaml` — координаты окон MM2

### Фаза 4. Engine — trade flow (4-5 дней)
**Зачем:** Ключевая автоматика — от детекта реквеста до скриншота proof.

- [ ] `engine/trade_flow.py` — основной flow:
  1. Сканирование экрана каждые 2 сек на `trade_request_notification.png`
  2. Детект реквеста → проверка ника в waitlist
  3. Accept trade request (клик по Accept)
  4. Поиск предмета через Search Box → клик → YOUR OFFER
  5. Accept (серый) → ожидание 6 сек → Accept (зелёный)
  6. OCR: "YOU HAVE ACCEPTED" → подтверждение
  7. Скриншот proof → отправка на бэкенд
  8. WS → `trade_completed`
- [ ] `engine/anti_afk.py` — анти-АФК:
  - Случайные действия каждые 5-10 мин
  - `pydirectinput.moveRel()`, `press('space')`, WASD
- [ ] `engine/reconnect.py` — авто-реконнект:
  - Детект `reconnect_button.png` → клик
  - Ожидание `mm2_hud.png` → синхронизация waitlist
- [ ] `engine/waitlist_manager.py` — локальный кэш waitlist:
  - Загрузка из БД при старте
  - Синхронизация по WS

### Фаза 5. Интеграция + тестирование (3-4 дня)
**Зачем:** Связать всё воедино и проверить end-to-end.

- [ ] Plugin → Backend: проверить REST-вызовы
- [ ] Backend → Engine: проверить WS-команды
- [ ] End-to-end тест:模拟 оплаты → заказ → трейд → proof
- [ ] Тест реконнекта Engine
- [ ] Тест анти-АФК
- [ ] Логирование через `loguru` во всех компонентах
- [ ] Обработка ошибок: retry-логика, graceful degradation

### Фаза 6. Полировка + деплой (2-3 дня)
**Зачем:** Привести в продакшн-состояние.

- [ ] Dockerfile для Backend + PostgreSQL (docker-compose)
- [ ] Systemd-юнит для Backend на VPS
- [ ] funpay-universal + Featly Plugin на VPS
- [ ] Windows Engine: автозапуск при старте Windows (Task Scheduler)
- [ ] Мониторинг: uptime, логи, алерты
- [ ] Документация: README.md, setup guide

### Фаза 7. Админка (5-7 дней, опционально)
**Зачем:** Удобный интерфейс для управления заказами и инвентарём.

- [ ] React + Vite + TailwindCSS
- [ ] Страница заказов (таблица + фильтры)
- [ ] Страница инвентаря (CRUD)
- [ ] Страница статистики (продажи, выручка)
- [ ] Страница ботов (статус, waitlist)

---

## Приоритеты по фазам

| Фаза | Время | Критичность | Зависимости |
|------|-------|-------------|-------------|
| 0. Инфраструктура | 1-2 дня | 🔴 Высокая | — |
| 1. Backend — ядро | 3-5 дней | 🔴 Высокая | Фаза 0 |
| 2. Plugin — каркас | 3-4 дня | 🔴 Высокая | Фаза 1 |
| 3. Engine — каркас | 3-4 дня | 🟡 Средняя | Фаза 1 |
| 4. Engine — trade flow | 4-5 дней | 🔴 Высокая | Фаза 3 |
| 5. Интеграция | 3-4 дня | 🔴 Высокая | Фазы 1-4 |
| 6. Полировка | 2-3 дня | 🟡 Средняя | Фаза 5 |
| 7. Админка | 5-7 дней | 🟢 Низкая | Фаза 5 |

**Итого:** ~25-35 дней до MVP (Фазы 0-5), ~30-40 дней до полного релиза.

---

## Рекомендации по порядку

1. **Начни с Фазы 0 + 1** — инфраструктура + бэкенд. Без бэкенда плагин и Engine не смогут общаться.
2. **Параллельно Фаза 2 + 3** — Plugin и Engine каркас можно писать одновременно (разные люди/AI-сессии).
3. **Фаза 4 — самая сложная** — trade flow требует точных координат и тестирования с реальным Roblox.
4. **Фаза 5 — интеграция** — собрать всё воедино, проверить end-to-end.
5. **Админку — потом** — можно без неё жить через Telegram-команды.

---

## Полезные ссылки

- [funpay-universal](https://github.com/alleexxeeyy/funpay-universal)
- [pydirectinput-rgx](https://github.com/ReggX/pydirectinput_rgx)
- [mss](https://python-mss.readthedocs.io/)
- [PyWinCtl](https://github.com/Kalmat/PyWinCtl)
- [FastAPI](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/)
