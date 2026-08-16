# FEATLY v3 — Концепт новой версии

> Статус: черновик / теория (обсуждение со своим ботом как с ревьюером)
> Дата: 2026-08-16
> Цель: описать целевую архитектуру и функциональность v3 до написания кода.

---

## 1. Зачем v3

v2 работает, но несёт инфраструктурный и логический «вес», который не нужен на текущем
объёме продаж (1 продавец, 1–3 движка). Ключевые решения v3:

- **Admin → Telegram** вместо React-панели (объёмы маленькие, интерфейс — панель в боте,
  по образцу плагина для playerok-universal).
- **Инвентарь → FunPay «Наличие»** связывается автоматически: заполнил инвентарь в панели —
  плагин находит лот по названию и обновляет количество на продажу.
- **Лёгкая архитектура под будущий Mini-ПК**: один центр на VDS, несколько движков по WS.

---

## 2. Целевая архитектура

```
VDS (центр управления)                     Mini-PC / Windows (машины выдачи)
┌───────────────────────────────┐          ┌──────────────────────────────┐
│ funpay-universal + FEATLY     │          │ Engine 1 (bot_id="bot1")     │
│   плагин (панель, диалоги)    │◄──WS────►├ Engine 2 (bot_id="bot2")     │
│ backend (hub: REST + WS)      │ network  ├ Engine 3 (bot_id="bot3")     │
│ SQLite (вместо PostgreSQL)    │          └──────────────────────────────┘
│ Telegram-админ (панель)       │
└───────────────────────────────┘
```

- Плагин и backend — на VDS (одна машина), движки — на Mini-ПК/Windows (remote).
- Cross-machine коммуникация только через WebSocket (`/ws/engine`), который уже есть.
- Каждый движок берёт из центра только свой waitlist по `bot_id` (фильтрация уже реализована).
- React-админка: **не разворачивается** (код остаётся в репозитории на случай роста).

### Решения по облегчению (из аудитов)
| Сейчас | В v3 |
|---|---|
| PostgreSQL + контейнер | SQLite (WAL) на VDS |
| Alembic (пустые версии) | `create_all` при старте |
| React + Vite + nginx | Telegram-панель (aiogram 3 Router) |
| Push-очереди команд движку | Poll waitlist движком + ручной sync |
| Двойной учёт заказа (orders + pending_trades) | Статусы в `orders`; `pending_trades` — опционально |

---

## ⚠️ Упущенное: совместимость плагина с последней версией funpay-universal (1.17)

Проверка актуального кода funpay-universal (release **1.17**, 02.08.2026) показала, что
**текущий FEATLY-плагин написан под старый интерфейс и не работает с последней версией бота**:

| Сейчас в FEATLY | Требуется в 1.17 |
|---|---|
| `EVENT_HANDLERS` | `FUNPAY_EVENT_HANDLERS` (ключи — enum `EventTypes`) |
| `TELEGRAM_ROUTERS` | `TELEGRAM_BOT_ROUTERS` |
| `(deal, acc)`, `acc.send_message(...)` | `(bot: FunPayBot, event)`, `bot.send_message(chat_id, ...)` |
| `on_load` / `on_unload` | `BOT_EVENT_HANDLERS`: `ON_MODULE_ENABLED` / `ON_MODULE_DISABLED` |

Проверено по коду и официальному шаблону модуля:
- Доступ к аккаунту: `from fpbot.funpaybot import get_funpay_bot` — глобальный синглтон;
  внутри хендлера — аргумент `bot.account`.
- Отправка сообщений: `FunPayBot.send_message(chat_id, text, ...)` (3 попытки).
- События в коде 1.17: регистрируются `NEW_MESSAGE`, `NEW_ORDER`, `ORDER_STATUS_CHANGED`.
  В README заявлены более новые имена (`NEW_DEAL`, `ITEM_PAID`, `DEAL_CONFIRMED`,
  `DEAL_ROLLED_BACK`), но в бандле `EventTypes` их **нет** — при миграции сверяться
  с реальным `EventTypes` установленного пакета.
- **Бонус для авто-поиска:** в `FunPayBot` уже есть `get_lot_by_title(title)` — поиск своего
  лота по названию. Изменение количества: `bot.account.get_lot_fields(lot_id)` →
  `fields.amount = n` → `account.save_lot(fields)` (методы подтверждены в бандле FunPayAPI).
- Telegram-роутеры модуля сливаются с роутером бота (aiogram 3): префиксы callback'ов
  делать уникальными, чтобы не конфликтовать с основным ботом.

**Следствие:** миграция плагина на актуальный интерфейс — обязательный **шаг 0** v3.
Без него ни панель, ни диалоги не заработают на версии 1.17.

---

## 📁 Файловая структура v3

Принятые решения (2026-08-16): `backend/` → `hub/`, React-админка → `legacy/web-admin/`,
**один git-репозиторий** на весь проект.

```
featly/
├── README.md
├── pyproject.toml              # линт/тайпчеки для всего Python
├── .env.example                # ВСЕ секреты разом (FEATLY_API_KEY, WS_SECRET, TG_ID...)
├── docker-compose.yml          # опционально (SQLite — можно и без него)
├── docs/
│   ├── FEATLY_v3_CONCEPT.md    # этот концепт
│   ├── roadmap.md              # шаги 0–6 (todo)
│   └── legacy/                 # старые v2-документы (аудиты, анализ)
│
├── plugin/                     # модуль funpay-universal 1.17 (имя модуля = featly)
│   ├── __init__.py             # BOT_EVENT_HANDLERS / FUNPAY_EVENT_HANDLERS / TELEGRAM_BOT_ROUTERS
│   ├── meta.py
│   ├── settings.py             # SettingsFile (config.json через бота)
│   ├── data.py                 # DataFile (orders_cache и т.п.)
│   ├── handlers/
│   │   ├── funpay.py           # события сделок/сообщений
│   │   └── telegram_admin.py   # панель (экраны, FSM)
│   └── core/
│       ├── backend_client.py   # REST к hub
│       ├── roblox_api.py       # ник → id, заявка в друзья
│       └── lots_sync.py        # авто-поиск лота + «Наличие» (автозаполнение)
│
├── hub/                        # «центр управления» (бывший backend; SQLite)
│   ├── app/
│   │   ├── models/  routers/  services/  ws/
│   │   └── main.py             # create_all при старте
│   └── tests/
│
├── engine/                     # бе Windows (без концептуальных изменений)
│   ├── main.py  trade_flow.py  ws_client.py  cv_matcher.py  ...
│   └── profiles/ templates/ tests/
│
├── legacy/
│   └── web-admin/              # React-админка «на антресоль», не в compose
│
└── scripts/                    # системная обвязка (systemd, планировщик, logrotate)
```

Пояснения:
- `backend/` → **`hub/`** — переименование отражает роль: центр управления (waitlist,
  инвентарь, WS-связь с движками), а не просто «HTTP-бэкенд».
- **`plugin/`** — структура подчинена требованиям funpay-universal 1.17 (официальные точки
  входа: `BOT_EVENT_HANDLERS`, `FUNPAY_EVENT_HANDLERS`, `TELEGRAM_BOT_ROUTERS`).
- **`legacy/web-admin/`** — React-панель остаётся в репо, но не участвует в сборке.
- Корневые `*.md` (аудиты, changelog, dev_notes) переносятся в `docs/legacy/`.
- `logs/` — runtime-мусор, не коммитится (добавляется в `.gitignore`).
- Перестройка структуры выполняется в начале реализации v3 (шаг 0).

---

## 3. Telegram-панель админки (`/admin`)

Каркас переносится из плагина playerok (`minecraft_dropship/admin_handlers.py`):
aiogram Router + `StatesGroup` (FSM) + inline-кнопки с текущими значениями +
редактирование одного и того же сообщения.

### Главное меню (визуал-пример)

```
⚙️ FEATLY — АДМИН

🤖 Движок: 🟢 online · seen 12:01
📦 Инвентарь: 14 предметов · 3 ⚠️
📋 В waitlist: 2 заказа
✅ Выдано сегодня: 3

📌 Настройки
Бот: bot_main | Порог: 3 | Cookie: 🟢
```

```
[🤖 Движок] [📦 Инвентарь]
[📋 Заказы] [📊 Статистика]
[⚙️ Настройки] [🧪 Диагностика]
```

### Разделы
- **🤖 Движок**: статус (`GET /bots/{bot_id}`), «Обновить waitlist», «Скрин с движка» (v3.1).
- **📦 Инвентарь**: список предметов с предупреждением ⚠️ при `count <= threshold`;
  добавление/изменение количества/порога/удаление; **автозаполнение «Наличия»** (раздел 4).
- **📋 Заказы**: таблица из `GET /pending_trades`, действия «Выдать принудительно» и «Отменить» (с FSM-подтверждением).
- **📊 Статистика**: счётчики из `orders` (выполнено/отменено/возвраты, среднее время выдачи).
- **⚙️ Настройки**: кнопки с текущим значением (`backend_url`, `bot_id`, `roblox_cookie`,
  `threshold`, `static_server_link`, `ADMIN_TG_ID`, `alert_on_zero` toggle).
- **🧪 Диагностика**: проверка cookie (валидация username через Roblox API),
  ping WS движка, прислать последний лог файлом.

### Требуемые доработки кода
- `plugin/handlers/admin.py` — Router + FSM + экраны (по образцу playerok-плагина).
- Регистрация роутера в `TELEGRAM_ROUTERS` + команда `/admin`.
- Хук `ON_FUNPAY_BOT_INIT` → глобальный референс `FunPayBot` для доступа к FunPay API.
- Backend: добавить `DELETE /inventory/{item_key}` и `POST /bots/{bot_id}/sync_waitlist`.
- Оживить кнопки-заглушки: force-trade и отмена заказа (**P1 из аудита v2.2**).

---

## 4. Инвентарь и авто-заполнение «Наличия» в лотах FunPay

### 4.1 Сценарий пользователя
Продавец в панели пишет: `icepiercer 2`. Плагин:
1. обновляет `count` предмета в бэкенде;
2. находит лот FunPay с названием, похожим на `icepiercer` (без учёта регистра);
3. меняет «Наличие» лота на `2`;
4. включает лот на продажу.

### 4.2 Возможности FunPayAPI (проверено по коду библиотеки)
- **Свои лоты:** `account.get_user(account.id).get_lots()` → `list[LotShortcut]`
  (атрибуты: `.id`, `.title`, `.amount`, `.price`). Альтернатива по подкатегориям —
  `account.get_my_subcategory_lots(subcategory_id)`.
- **Правка наличия:**
  ```python
  fields = account.get_lot_fields(lot.id)      # load → csrf обновляется сам
  fields.amount = new_count                    # property «Наличие»
  if new_count == 0:
      fields.active = False                    # скрыть лот при нуле
  account.save_lot(fields)                     # POST lots/offerSave
  ```
- **Нюансы, подтверждённые кодом:**
  - при `amount = 0` на FunPay уходит пустое значение (трактуется как 0);
  - для лотов **с автовыдачей** `amount` считается как `len(secrets)` — менять надо
    `secrets`, а не `amount` (проверять при внедрении);
  - готового поиска по названию в API нет — реализуем свой fuzzy-матчинг.

### 4.3 Авто-поиск лота по названию
В 1.17 использовать готовый `FunPayBot.get_lot_by_title(title)` (есть в библиотеке):
```python
bot = get_funpay_bot()
lot = bot.get_lot_by_title("icepiercer")       # или subcategory/subcategory_id для точности
if lot:
    fields = bot.account.get_lot_fields(lot.id)
    fields.amount = new_count
    if new_count == 0:
        fields.active = False
    bot.account.save_lot(fields)
```
Запасной вариант (если get_lot_by_title не найдёт из-за регистра/формата):
```python
def find_lot_by_title(lots, query: str):
    q = query.strip().lower()
    # точное → вхождение подстроки → fuzzy (SequenceMatcher >= 0.6)
```
- При успехе `lot_id` **кэшируется** в конфиге плагина
  (`items: {item_key: {lot_id, name}}`) — дальнейшие обновления идут по id без поиска.
- Если лот не найден: предмет сохраняется в инвентаре, в панель приходит
  «⚠️ Лот не найден — задай вручную» и предлагается `lot_id`.

### 4.4 Когда синхронизируется наличие
1. **Основной триггер** — ручное изменение `count` в панели (сразу после сохранения).
2. **Reconcile** (опциональный, раз в N минут): плагин сравнивает инвентарь бэкенда
   с фактическим `amount` лотов и «подтягивает» расхождения. Самовосстанавливается.
3. **Списание при продаже** — FunPay сам уменьшает «Наличие» при покупке; отдельный
   вызов не нужен. Backend-инвентарь при выдаче уменьшает движок — reconcile сводит.

### 4.5 Ограничения и риски
- `save_lot` — POST на FunPay: **троттлинг**, риск капчи. Не вызывать по таймеру часто;
  синхронизация — по действиям продавца.
- При наименовании предметов придерживаться единого формата в инвентаре и в заголовках лотов.
- Лоты-дубликаты с одинаковым названием: решает точный матч → первый по списку / уточнение.

---

## 5. Что остаётся открытым (вопросы на следующее обсуждение)

1. У продавца funpay-universal **1.17**: интерфейс модуля — `FUNPAY_EVENT_HANDLERS`/`BOT_EVENT_HANDLERS`/
   `TELEGRAM_BOT_ROUTERS`. Расхождение README (деals-имена) и кода (order-события) решено
   проверкой установленного пакета при миграции (шаг 0).
2. Переезд backend на SQLite — сразу в v3 или позже?
3. Судьба `pending_trades`: оставить как есть (опционально) или перейти на статусы в `orders`.
4. Нужен ли reconcile-таск или достаточно синка по действию.

## 6. Дорожная карта (порядок шагов)

| # | Шаг | Эффект |
|---|---|---|
| 0a | **Перестройка структуры**: `backend/` → `hub/`, `admin/` → `legacy/web-admin/`, docs → `docs/legacy`, `.env.example` | ✅ **выполнено 2026-08-16** |
| 0 | **Миграция плагина на интерфейс 1.17**: `FUNPAY_EVENT_HANDLERS`/`BOT_EVENT_HANDLERS`/`TELEGRAM_BOT_ROUTERS`, хендлеры `(bot, event)`, `bot.send_message` | ✅ **выполнено 2026-08-16** (см. changelog [9.0.0]) |
| 1 | Telegram-панель: `/admin`, экраны инвентаря и настроек (каркас из playerok) | ✅ **выполнено 2026-08-16** |
| 2 | Инвентарь: CRUD через панель + `DELETE /inventory` на бэкенде | ✅ **выполнено 2026-08-16** |
| 3 | Автозаполнение «Наличия»: авто-поиск лота + `get_lot_fields`/`save_lot` | ✅ **выполнено 2026-08-16** |
| 4 | Заказы: force-trade / отмена через панель (закрыть TODO аудита v2.2) | ✅ **выполнено 2026-08-16** |
| 5 | (Опц.) SQLite + убрать React-админку из compose | ✅ **выполнено 2026-08-16** |
| 6 | (Опц.) Подготовка к Mini-ПК: poll waitlist, конфиг движка через env | ✅ **выполнено 2026-08-16** |

> **Статус: все базовые шаги v3 (0–6) выполнены 16.08.2026.**
> Дальше — v3.1 «полировка»: `!смена` (обновление ника в waitlist), шифрование
> `roblox_cookie`, уникальность `pending_trade`, deferred-платежи, скриншоты движка.