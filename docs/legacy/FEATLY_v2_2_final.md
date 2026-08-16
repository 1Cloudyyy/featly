# 🏛️ Featly v2.2 — Концепт автовыдачи (интеграция с funpay-universal)

> Статус: финальная ревизия архитектуры · 2026-08-05
> Основан на: Featly v2.1 + реальный трейд MM2 + funpay-universal
> Ключевые изменения: Featly — плагин для funpay-universal; FunPay-логика убрана из бэкенда; Telegram-управление через роутеры funpay-universal

---

## 1. Что изменилось (v2.1 → v2.2)

| Аспект | Было в v2.1 | Стало в v2.2 | Почему |
|--------|-------------|--------------|--------|
| FunPay-менеджер | Самописный Python polling | **funpay-universal + Featly Plugin** | Готовый, отлаженный polling, чат, TG-управление, система модулей |
| Telegram-бот | Отдельный процесс | **Роутеры в TG-боте funpay-universal** | Не плодим ботов, используем встроенную инфраструктуру |
| Дружба с покупателем | Не было | **Roblox API** (`request-friendship`) | Покупатель видит бота онлайн, проще зайти на сервер |
| Ожидание трейда | 10 минут таймаут | **Постоянное ожидание** (до отмены/возврата) | Покупатель может заходить в любое время |
| VIP-ротация | Была | **Убрана** | Нет смысла, бот сидит на одном сервере |
| Команды чата FunPay | Не было | **!смена, !фото, !помощь, !отмена** | Пользователь контролирует заказ сам |
| Авторизация Roblox | Cookie (.ROBLOSECURITY) | **Двойная**: браузер (игра) + cookie (API-дружба) | Cookie нужен только для API, игра сама подхватывает сессию из браузера |
| Реконнект при кике | Автоперезапуск Roblox | **Клик по кнопке Reconnect** | Быстрее, чем перезапуск |
| Связь с FunPay | Самописный polling | **funpay-universal Runner** | `EventTypes.NEW_DEAL`, `NEW_MESSAGE` из коробки |
| Алерты запаса | Не было | **Настраиваемый порог** + Telegram через funpay-universal | Используем встроенную систему уведомлений |

---

## 2. Архитектура (финальная)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FunPay (сайт)                                       │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              │ HTTP (polling / chat)
┌─────────────────────────────▼───────────────────────────────────────────────┐
│                    funpay-universal (Python, VPS)                           │
│  • Polling: Runner.listen()                                               │
│  • Chat: acc.send_message()                                               │
│  • Telegram: aiogram 3 (роутеры модулей)                                  │
│  • Settings / Data: JSON-врапперы                                         │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │                    Featly Plugin (модуль)                             │ │
│  │                                                                       │ │
│  │  FunPay Event Handlers:                                               │ │
│  │    NEW_DEAL        → start_dialog()                                   │ │
│  │    NEW_MESSAGE     → parse_commands()                                 │ │
│  │    ITEM_PAID       → create_order()                                   │ │
│  │    DEAL_CONFIRMED  → archive_order()                                  │ │
│  │    DEAL_ROLLED_BACK→ cancel_order()                                  │ │
│  │                                                                       │ │
│  │  Roblox API Client (aiohttp):                                         │ │
│  │    • validate_username() → userId                                     │ │
│  │    • request_friendship(userId)                                       │ │
│  │    • CSRF-token management                                            │ │
│  │                                                                       │ │
│  │  Telegram Routers (aiogram 3):                                        │ │
│  │    /roblox_cookie — обновить .ROBLOSECURITY                         │ │
│  │    /stock           — текущий инвентарь                               │ │
│  │    /orders          — активные заказы                                 │ │
│  │    /force_trade     — ручная выдача                                   │ │
│  │    /alert_channel   — настройка TG-канала для алертов                 │ │
│  │                                                                       │ │
│  │  HTTP Client → Featly Backend (REST)                                │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              │ HTTP REST + WebSocket
┌─────────────────────────────▼───────────────────────────────────────────────┐
│                    Featly Backend (Node.js + PostgreSQL, VPS)              │
│                                                                             │
│  REST API (для плагина):                                                    │
│    POST   /orders              — создать заказ                              │
│    PATCH  /orders/:id/status   — обновить статус                            │
│    GET    /pending_trades      — список ожидания                            │
│    DELETE /pending_trades/:id  — удалить из ожидания                        │
│    GET    /inventory           — инвентарь                                │
│    PATCH  /inventory/:item     — обновить количество                      │
│    POST   /proofs              — загрузить скриншот proof                   │
│                                                                             │
│  WebSocket Server (для Windows Engine):                                     │
│    • auth + heartbeat (30s)                                               │
│    • command: WAIT_FOR_TRADE                                              │
│    • command: REMOVE_WAITLIST                                               │
│    • command: FORCE_TRADE                                                   │
│    • event:   trade_completed                                               │
│    • event:   trade_failed                                                  │
│    • event:   screenshot_taken                                            │
│                                                                             │
│  PostgreSQL:                                                                │
│    • orders (id, funpay_order_id, buyer_nickname, buyer_user_id, items,      │
│             status, created_at, completed_at, proof_url)                      │
│    • pending_trades (id, order_id, bot_id, buyer_nickname, buyer_user_id,  │
│                       items, status, created_at)                            │
│    • inventory (id, item_key, name, count, low_stock_threshold)             │
│    • bots (id, bot_id, roblox_cookie, status, last_seen, ws_connected)     │
│    • trade_logs (id, order_id, buyer, items, success, proof_path, ts)       │
│                                                                             │
│  Alert Service:                                                             │
│    • Telegram-алерты через HTTP → funpay-universal TG-бот                 │
│    • Или прямой aiogram-вызрос (если бэкенд на Python)                     │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              │ WebSocket (heartbeat 30s)
┌─────────────────────────────▼───────────────────────────────────────────────┐
│                    Windows Engine (Python, ноутбук)                         │
│                                                                             │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                  │
│  │ Roblox.exe    │  │ CVMatcher     │  │ WS Client     │                  │
│  │ (оконный)     │  │ (OpenCV)      │  │ (websockets)  │                  │
│  │ • анти-АФК    │  │ • templates   │  │ • heartbeat   │                  │
│  │ • реконнект   │  │ • OCR (tess)  │  │ • commands    │                  │
│  └───────────────┘  └───────────────┘  └───────────────┘                  │
│                                                                             │
│  Flow:                                                                      │
│  1. Получает WAIT_FOR_TRADE по WS                                           │
│  2. Загружает waitlist из БД при старте                                    │
│  3. Каждые 2 сек сканирует экран на входящий трейд                         │
│  4. Если реквест от ника в waitlist → Accept → Put items → Confirm         │
│  5. Скриншот proof → отправка на бэкенд                                   │
│  6. Возврат в режим ожидания                                                │
│                                                                             │
│  Все предметы на одном аккаунте (migufim)                                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Полный flow: от оплаты до выдачи

### Этап 0. Покупатель оплатил на FunPay

```
funpay-universal Runner.listen() → EventTypes.NEW_DEAL
  │
  ▼
Featly Plugin: on_new_deal(deal)
  → Проверяет, есть ли предмет в наличии (GET /inventory/:item)
  → Если count == 0:
       → Авто-возврат (через funpay-universal API)
       → acc.send_message(chat_id, "❌ Предмет закончился. Возврат оформлен.")
  → Если count > 0:
       → Создаёт заказ в БД (POST /orders)
       → Начинает диалог
```

### Этап 1. Диалог в чате FunPay

```
Featly Plugin (через funpay-universal chat):
  acc.send_message(chat_id, "Привет! Напиши свой ник в Roblox:")

Покупатель: xi_qas

Плагин:
  1. Валидирует ник: GET https://users.roblox.com/v1/usernames/users
     → Получает userId (например, 123456789)
  2. Отправляет в чат: "Ник: xi_qas. Верно? Ответь Да"

Покупатель: Да
```

### Этап 2. Добавление в друзья (Roblox API)

```
Плагин выполняет:

  POST https://friends.roblox.com/v1/users/123456789/request-friendship
  Headers:
    Cookie: .ROBLOSECURITY={cookie из data.py}
    X-CSRF-TOKEN: {получен через pre-flight GET}
    Content-Type: application/json
  Body: {}

  При 200 OK:
    → acc.send_message(chat_id, "✅ Добавил тебя в друзья. Заходи в игру!")
    → acc.send_message(chat_id, "Сервер: {static_server_link}")
    → acc.send_message(chat_id, "Кинь мне трейд через TAB → Trade.")

  При 401:
    → Telegram-алерт: "🔴 Roblox cookie протух. /roblox_cookie"
    → acc.send_message(chat_id, "Техническая пауза, скоро продолжим...")
```

### Этап 3. Создание заказа и постоянное ожидание

```
Плагин → POST /orders
  {
    "funpay_order_id": "fp_456",
    "buyer_nickname": "xi_qas",
    "buyer_user_id": 123456789,
    "items": ["Batwing"],
    "status": "waiting_trade"
  }

Бэкенд:
  INSERT INTO pending_trades (...)
  WS → Windows Engine: {"action": "WAIT_FOR_TRADE", "buyer": "xi_qas", "items": ["Batwing"], "order_id": "ord_123"}
```

### Этап 4. Покупатель заходит в игру и кидает трейд

```
Windows Engine (каждые 2 сек):
  → Сканирует экран на "trade_request_notification.png"
  → Если детект:
       → Проверяет: ник отправителя в waitlist? ДА
       → Кликает Accept
```

### Этап 5. Бот выдаёт предмет

```
Windows Engine:
  1. Accept trade request
  2. Search box → type "bat" → click Batwing → YOUR OFFER
  3. Accept (gray) → wait 6 sec → Accept (green)
  4. OCR: "YOU HAVE ACCEPTED" detected
  5. Screenshot proof → POST /proofs
  6. WS → Backend: {"type": "trade_completed", "order_id": "ord_123", "success": true}
```

### Этап 6. Закрытие заказа

```
Бэкенд получает trade_completed:
  → PATCH /orders/ord_123/status → "completed"
  → DELETE FROM pending_trades WHERE order_id = "ord_123"
  → PATCH /inventory/batwing_single → count--
  → Проверка порога: count <= threshold? → Telegram-алерт

Плагин (по вебхуку/периодическому GET):
  → Видит статус "completed"
  → acc.send_message(chat_id, "✅ Предмет выдан! Спасибо за покупку")
  → FunPayAPI: подтверждает выдачу (если нужно)
  → Telegram: "✅ Заказ #fp_456 выдан. +{amount}₽"

Windows Engine:
  → Возвращается в WAITING
  → Запрашивает актуальный waitlist (GET /pending_trades)
```

---

## 4. Система постоянного ожидания (Persistent Waitlist)

### Проблема

Покупатель может оплатить утром, а зайти вечером. Если ждать только 10 минут — заказ сгорит.

### Решение

Бэкенд хранит `pending_trades`. Windows Engine при старте и после каждого трейда синхронизирует список.

```
Windows Engine стартует / реконнект
        │
        ▼
WS → Backend: {"type": "request_waitlist", "bot_id": "bot_main"}
        │
        ▼
Backend: SELECT * FROM pending_trades WHERE bot_id = "bot_main"
        │
        ▼
WS → Engine: {"type": "waitlist_sync", "waitlist": ["xi_qas", "pro_player_99"]}
        │
        ▼
Engine загружает в локальный список
```

### Удаление из ожидания

```
Админка / Telegram / Покупатель пишет !отмена
        │
        ▼
Плагин → DELETE /pending_trades/:id
        │
        ▼
Backend: WS → Engine: {"action": "REMOVE_WAITLIST", "buyer": "xi_qas"}
        │
        ▼
Engine убирает из локального списка
```

### Приоритет

Если реквест от ника, которого НЕТ в waitlist — **Decline**.

---

## 5. Команды в чате FunPay

Обрабатываются в `on_new_message` плагина. Парсинг: если сообщение начинается с `!` — это команда.

| Команда | Что делает | Flow |
|---------|-----------|------|
| `!смена НовыйНик` | Меняет ник в заказе | Валидация → Roblox API validate → PATCH /orders/:id → Обновить waitlist → WS → Engine |
| `!фото` | Скриншот экрана бота | WS → Engine: SCREENSHOT → Engine делает скрин → POST /proofs → Плагин получает URL → acc.send_message(chat_id, "Скрин: {url}") |
| `!помощь` | Вызов продавца | Telegram-алерт с ссылкой на чат и инфо заказа |
| `!отмена` | Запрос отмены | Плагин: "Подтверди: Да/Нет" → При подтверждении: DELETE /pending_trades → WS → Engine: REMOVE_WAITLIST → FunPay: возврат |
| `!статус` | Статус заказа | Плагин делает GET /orders/:id → отвечает в чат |

### Пример

```
Покупатель: !смена pro_player_99
Плагин: "Ник изменён на pro_player_99. Верно?"
Покупатель: Да
Плагин:
  1. validate_username("pro_player_99") → userId
  2. PATCH /orders/ord_123 (новый ник + userId)
  3. WS → Engine: REMOVE_WAITLIST "xi_qas" + WAIT_FOR_TRADE "pro_player_99"
  4. Roblox API: request_friendship(новый userId)
  5. acc.send_message(chat_id, "Готово! Добавил pro_player_99 в друзья.")
```

---

## 6. Авторизация Roblox (двойная)

### Для десктоп-клиента (игра)

1. Ты один раз заходишь в Roblox через браузер (Chrome/Firefox)
2. Нажимаешь «Play» на странице игры → браузер спрашивает «Открыть Roblox Player?»
3. Roblox.exe запускается и **сам подхватывает сессию** из браузера
4. Дальше Roblox.exe живёт своей жизни — для игры cookie не нужен

### Для API-дружбы (плагин funpay-universal)

Нужен `.ROBLOSECURITY` cookie аккаунта бота (migufim):

```
1. Зайди в Roblox через браузер на аккаунт бота
2. F12 → Application → Cookies → https://www.roblox.com
3. Скопируй значение .ROBLOSECURITY
4. Telegram: /roblox_cookie <значение>
5. Плагин сохраняет в data.py (JSON) и отправляет на бэкенд (PATCH /bots/bot_main)
```

**Обновление cookie:**
- Cookie живёт месяцами, если не разлогиниваться
- Если протухнет — Roblox API вернёт 401 → Telegram-алерт → /roblox_cookie

### Проверка авторизации

```python
# Плагин: детект протухшего cookie
async def request_friendship(user_id: int):
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"https://friends.roblox.com/v1/users/{user_id}/request-friendship",
            headers={"Cookie": f".ROBLOSECURITY={cookie}"}
        ) as resp:
            if resp.status == 401:
                await send_telegram_alert("🔴 Roblox cookie протух. /roblox_cookie")
                raise RobloxAuthError()
```

---

## 7. Анти-АФК + Авто-реконнект

### Анти-АФК

```python
import pydirectinput as pdi
import random
import asyncio

async def anti_afk():
    action = random.choice(['camera', 'jump', 'walk'])
    if action == 'camera':
        pdi.moveRel(random.randint(-200, 200), random.randint(-100, 100), duration=0.5)
    elif action == 'jump':
        pdi.press('space')
    elif action == 'walk':
        key = random.choice(['w', 'a', 's', 'd'])
        pdi.keyDown(key)
        await asyncio.sleep(0.3)
        pdi.keyUp(key)
```

> **Важно:** используем `pydirectinput-rgx` вместо `pyautogui`. PyAutoGUI использует устаревшие `mouse_event()` / `keybd_event()` + Virtual Key Codes — **Roblox (DirectX-игра) может игнорировать эти события**. `pydirectinput` использует `SendInput()` + Scan Codes, что гарантирует работу в DirectX.

### Авто-реконнект при кике

```python
async def check_reconnect():
    screenshot = capture_screen()
    if detect_template('reconnect_button.png', screenshot):
        click(cfg.regions.reconnect_button)
        await wait_for_template('mm2_hud.png', timeout=30)
        # После реконнекта синхронизируем waitlist
        await ws_send({"type": "request_waitlist", "bot_id": "bot_main"})
        return True
    return False
```

**Почему Reconnect лучше перезапуска:**
- Перезапуск = 45 секунд
- Reconnect = 5-10 секунд
- Бот остаётся на том же сервере

---

## 8. Алерты и пороги запаса

### Настраиваемый порог

Хранится в `settings.py` плагина:

```json
{
  "low_stock_threshold": 3,
  "telegram_alert_chat_id": "123456789",
  "alert_on_zero": true
}
```

### Когда срабатывает

```
После каждого успешного трейда:
  inventory.batwing_single.count = 2
  2 <= threshold (3) → ТРИГГЕР
        │
        ▼
Telegram (через funpay-universal TG-бот):
  «🟡 Batwing осталось 2 шт. Пополни запас.»
```

### Типы алертов

| Событие | Сообщение Telegram |
|---------|-------------------|
| Запас <= порога | 🟡 {item} осталось {count}. Пополни. |
| Запас = 0 | 🔴 {item} закончился! Срочно пополни. |
| Успешная выдача | ✅ Заказ #{fp_id} выдан. +{amount}₽ |
| Ошибка трейда | 🔴 Ошибка #{id}: {error} |
| Roblox разлогин | 🔴 Roblox разлогинился. Зайди через браузер. |
| Roblox cookie протух | 🔴 Roblox API cookie протух. /roblox_cookie |
| !помощь от покупателя | 🆘 Покупатель просит помощь: {link} |
| FunPay сессия протухла | 🔴 FunPay не отвечает. Перезайди в funpay-universal. |

---

## 9. Telegram-управление (роутеры плагина)

Все команды доступны через TG-бота funpay-universal (добавляются как роутеры модуля).

| Команда | Доступ | Описание |
|---------|--------|----------|
| `/roblox_cookie <cookie>` | Админ | Обновить .ROBLOSECURITY для API-дружбы |
| `/stock` | Админ | Текущий инвентарь (из БД) |
| `/orders` | Админ | Активные заказы + pending_trades |
| `/force_trade <order_id>` | Админ | Принудительно выдать (если бот "застрял") |
| `/set_threshold <item> <n>` | Админ | Изменить порог алерта |
| `/alert_channel <chat_id>` | Админ | Куда слать алерты (отдельно от TG-бота) |
| `/engine_status` | Админ | Статус Windows Engine (online/offline, waitlist) |
| `/engine_restart` | Админ | Перезапустить Engine (WS-команда) |

---

## 10. Технический стек

| Компонент | Технология | Где |
|-----------|-----------|-----|
| FunPay-ядро | funpay-universal (Python) | Linux VPS |
| Featly Plugin | Python + aiohttp + aiogram 3 | Внутри funpay-universal |
| Бэкенд | **FastAPI** (Python) + asyncpg + SQLAlchemy 2.0 | Linux VPS |
| База данных | PostgreSQL 15 | Linux VPS |
| Windows Engine | Python + OpenCV + **pydirectinput-rgx** + **mss** + **PyWinCtl** | Ноутбук |
| Связь Plugin ↔ Backend | HTTP REST | localhost / VPS |
| Связь Backend ↔ Engine | WebSocket (heartbeat 30s) | VPS ↔ Ноутбук |
| Telegram | aiogram 3 (через funpay-universal) | Linux VPS |
| Скриншоты proof | mss + OpenCV + отправка в чат FunPay | Ноутбук → FunPay |

### 10.1. Обоснование выбора библиотек (Windows Engine)

#### pydirectinput-rgx ⭐ CRITICAL

| | PyAutoGUI | pydirectinput-rgx |
|---|---|---|
| Windows API | `mouse_event()` / `keybd_event()` (устаревшие) | `SendInput()` (современный) |
| Key Codes | Virtual Key Codes | **Scan Codes** (DirectInput-совместимые) |
| DirectX | ❌ Может игнорироваться Roblox | ✅ Гарантированно работает |
| API | `click()`, `typewrite()`, `press()` | Полностью совместим с PyAutoGUI |
| Дополнительно | — | `unicode_typewrite()`, `scancode_press()`, `hold()` context manager, multi-monitor |

**Установка:** `pip install pydirectinput-rgx`

#### MSS (Multi-ScreenShot) ⭐ HIGHLY RECOMMENDED

| | pyautogui.screenshot() | mss |
|---|---|---|
| Скорость | 10-15 FPS | **30-60 FPS** (в 3-5 раз быстрее) |
| Реализация | PIL → WinAPI | ctypes напрямую |
| OpenCV | Нужна конвертация | Нативный NumPy array (BGRA) |
| Multi-monitor | ❌ | ✅ Из коробки |

**Установка:** `pip install mss`

#### PyWinCtl ⭐ RECOMMENDED

| | pygetwindow (устарел) | PyWinCtl |
|---|---|---|
| Платформа | Только Windows | Кроссплатформенный |
| Фокус окна | `win.activate()` | `win.activate()` + `alwaysOnTop(True)` |
| Мониторинг | ❌ | `win.watchdog` — детект закрытия / сворачивания |
| Позиция | `moveTo()` | `moveTo()` + `resizeTo()` |

**Установка:** `pip install pywinctl`

### 10.2. Бэкенд: FastAPI vs Node.js

| Критерий | FastAPI (Python) | Node.js + Express |
|---|---|---|
| Единый стек с плагином | ✅ Да | ❌ Нет |
| Асинхронность из коробки | ✅ `async`/`await` | ✅ `async`/`await` |
| Авто-документация API | ✅ Swagger UI / ReDoc | ❌ Требует отдельной настройки |
| ORM | SQLAlchemy 2.0 + Alembic | Prisma / TypeORM |
| WebSocket | `websockets` (нативно) | `ws` |
| Сложность освоения | Низкая (1 человек) | Зависит от опыта |

**Рекомендация:** Использовать **FastAPI** для единого Python-стека на VPS. Упрощает поддержку одним человеком.

---

## 11. Структура модуля Featly

```
modules/
└── featly/
    ├── __init__.py              # Точка входа, хендлеры, метаданные
    ├── meta.py                  # PREFIX, VERSION, NAME, AUTHORS
    ├── settings.py              # Конфиги (пороги, URL бэкенда, cookie)
    ├── data.py                  # Данные (кэш заказов, cookie)
    ├── requirements.txt         # aiohttp, и т.д.
    │
    ├── core/
    │   ├── roblox_api.py        # validate_username, request_friendship
    │   ├── backend_client.py    # HTTP REST к бэкенду
    │   └── order_manager.py       # Логика заказов, диалогов
    │
    ├── handlers/
    │   ├── funpay.py            # on_new_deal, on_new_message
    │   └── telegram.py          # Роутеры aiogram 3
    │
    └── utils/
        └── alerts.py            # Отправка алертов в Telegram
```

### 11.1. Зависимости Windows Engine

```
# CV + OCR
opencv-python==4.10.0.84
numpy==1.26.4
pytesseract==0.3.10
Pillow==10.4.0

# Скриншоты (быстрые)
mss==9.0.1

# Клики / клавиатура (DirectX-совместимые)
pydirectinput-rgx==1.1.0

# Управление окнами
pywinctl==0.5

# WebSocket
websockets==12.0

# Конфиги
pyyaml==6.0.1

# Опционально: логирование
loguru==0.7.2
```

---

## 12. Чек-лист окружения

### VPS (Ubuntu 24)

```bash
# Python 3.12
sudo apt install python3.12 python3.12-venv python3.12-dev

# PostgreSQL
sudo apt install postgresql postgresql-contrib

# Tesseract (если OCR на VPS — обычно нет)
sudo apt install tesseract-ocr tesseract-ocr-eng

# FastAPI + зависимости (если бэкенд на Python)
pip install fastapi uvicorn asyncpg sqlalchemy alembic pydantic websockets
```

### Ноутбук (Windows)

```bash
# Python 3.12 с python.org (Add to PATH!)

# Создать venv
python -m venv featly_env
featly_env\Scriptsctivate

# Установить зависимости
pip install pydirectinput-rgx mss pywinctl opencv-python numpy pytesseract Pillow websockets pyyaml loguru

# Установить Tesseract
# 1. Скачать: https://github.com/UB-Mannheim/tesseract/wiki
# 2. Запомнить путь установки (обычно C:\Program Files\Tesseract-OCR)
# 3. Добавить в PATH
```

### funpay-universal (VPS)

```bash
# Установка
bash <(curl -s https://raw.githubusercontent.com/alleexxeeyy/funpay-universal/main/install.sh)

# Запуск
fpuniversal setup
fpuniversal start
```

---

## 13. План реализации

### Этап 1. MVP — «Плагин + диалог + API-дружба» (неделя 1)

- [ ] Установить funpay-universal на VPS
- [ ] Создать структуру модуля Featly (`__init__.py`, `meta.py`, `settings.py`)
- [ ] Реализовать `roblox_api.py`: validate_username, request_friendship, CSRF-handling
- [ ] Реализовать `backend_client.py`: POST /orders, GET /pending_trades
- [ ] FunPay-ивент `NEW_DEAL` → диалог → валидация ника → API-дружба
- [ ] Бэкенд: таблицы orders, pending_trades, inventory, bots (FastAPI + PostgreSQL)
- [ ] Windows Engine: запуск Roblox, ожидание трейда (ручное подтверждение через Telegram)
- [ ] **Цель:** проверить связку FunPay → Плагин → Roblox API → Дружба → Бэкенд

### Этап 2. Автоматизация — «Бот сам выдаёт» (неделя 2)

- [ ] Windows Engine: детект входящего реквеста по шаблону (OpenCV + mss)
- [ ] Поиск предмета через Search + двойной Accept (pydirectinput-rgx)
- [ ] OCR «YOU HAVE ACCEPTED" (pytesseract)
- [ ] Система постоянного ожидания (waitlist sync)
- [ ] Скриншот proof + отправка в чат FunPay
- [ ] Обновление инвентаря и статуса заказа
- [ ] **Цель:** полный авто от оплаты до выдачи

### Этап 3. Надёжность — «Команды + алерты + реконнект» (неделя 3)

- [ ] Команды чата FunPay: !смена, !фото, !помощь, !отмена
- [ ] Telegram роутеры: /roblox_cookie, /stock, /orders, /force_trade
- [ ] Авто-реконнект при кике (кнопка Reconnect)
- [ ] Алерты запаса (настраиваемый порог)
- [ ] Анти-АФК (pydirectinput-rgx)
- [ ] **Цель:** бот работает неделями без вмешательства

### Этап 4. Платформа — «Новая игра = YAML» (неделя 4)

- [ ] Вынести координаты кликов в YAML-профиль игры
- [ ] Вынести шаблоны предметов в каталог
- [ ] Написать trade_flow для второй игры
- [ ] Админка: заказы, инвентарь, статистика (React + Vite)
- [ ] **Цель:** масштабирование

---

## 14. Ответы на вопросы

### 1. Почему funpay-universal, а не самописный polling?

- Готовый polling с `Runner.listen()` — отлажен, обрабатывает реконнекты
- Встроенный чат `acc.send_message()` — не нужен HTTP-скрапинг
- Система модулей — Featly это просто папка в `modules/`
- Telegram-управление — уже есть, добавляем роутеры
- Сообщество — шаблоны, обновления, багфиксы
- Авто-выдача цифровых товаров — можно использовать параллельно с MM2

### 2. Как именно добавлять в друзья?

**Через официальный API Roblox** (не GUI, не cookie-эмуляция):

```http
POST https://friends.roblox.com/v1/users/{targetUserId}/request-friendship
Cookie: .ROBLOSECURITY={bot_cookie}
X-CSRF-TOKEN: {csrf}
```

**Почему не GUI:**
- В десктоп-клиенте Roblox внутри игры нет кнопки «Add Friend»
- Можно только «Invite to Play Together» — это не добавляет в друзья
- На главном экране Roblox есть друзья, но выходить из игры ради этого — лишнее действие, которое прерывает ожидание трейда

**Почему API — безопасно:**
- Публичный эндпоинт, используемый самим сайтом Roblox
- Не нарушает ToS
- Требуется только `.ROBLOSECURITY`, полученный легально через браузер

### 3. Как работает постоянное ожидание при перезаходе?

Бэкенд хранит `pending_trades` в PostgreSQL. Windows Engine при старте:

```python
pending = await backend.get_pending_trades(bot_id='bot_main')
self.waitlist = [p.buyer_nickname for p in pending]
```

Если ноутбук перезагрузился — при старте бот сам восстановит список через WS.

### 4. Нужен ли виртуальный монитор?

**Короткий ответ:** если ноутбук будет лежать включённым и никто не будет трогать мышь/клавиатуру — **не нужен**.

**Подробно:** PyAutoGUI / pydirectinput работают с реальным экраном. Если свернёшь Roblox или накроешь окном Chrome — клики промахнутся.

| Вариант | Нужен вирт. монитор? | Описание |
|---------|---------------------|----------|
| Ноутбук просто лежит включённым | ❌ Нет | Roblox на экране, никто не трогает |
| Хочу пользоваться ноутбуком параллельно | ✅ Да | IddSampleDriver / Parsec VDD — Roblox на виртуальном экране |
| Сервер без монитора (VPS Windows) | ✅ Да | Обязательно нужен виртуальный монитор |

**Рекомендация:** начни без виртуального монитора. Если потом захочешь пользоваться ноутбуком — добавим за 10 минут.

### 5. Что если .ROBLOSECURITY cookie протухнет?

1. Roblox API вернёт 401 Unauthorized
2. Telegram-алерт: «🔴 Roblox API cookie протух. Отправь /roblox_cookie»
3. Ты заходишь в браузер на аккаунт бота → F12 → Cookies → копируешь `.ROBLOSECURITY`
4. Telegram: `/roblox_cookie новое_значение`
5. Плагин сохраняет в `data.py` и отправляет на бэкенд

> **Примечание:** десктоп-клиент Roblox при этом **продолжает работать**. Cookie нужен только для API.

### 6. Как плагин узнаёт, что предмета нет в наличии?

Бэкенд хранит `inventory`. Плагин делает `GET /inventory/:item_key` перед созданием заказа. Если `count == 0`:
- Авто-возврат через FunPay API (если доступен)
- Или ручной возврат через Telegram-команду `/refund <order_id>`
- Сообщение в чат: «❌ Предмет закончился. Оформляю возврат...»

### 7. Что если Windows Engine отключился?

- Бэкенд детектит по WS heartbeat (30 сек). Если 2 пропущенных — статус `offline`
- Telegram-алерт: «🔴 Windows Engine offline. Проверь ноутбук.»
- Заказы в `pending_trades` остаются. При переподключении Engine синхронизирует waitlist.
- Покупатель может ждать сколько угодно — заказ не сгорит.

### 8. Можно ли продавать несколько предметов в одном заказе?

Да. `items` — массив. Engine кладёт каждый предмет в окно трейда по очереди.

```json
{
  "items": ["Batwing", "Ghostblade"],
  "order_id": "ord_123"
}
```

### 9. Как обновлять инвентарь?

Ручной ввод через Telegram `/stock` или админка. Авто-сканирование инвентаря в игре — фича Этапа 4.

```
/stock
→ Показывает: Batwing: 5, Ghostblade: 2, ...

/set_stock batwing_single 10
→ Обновляет count в БД
```

---

> **Featly v2.2** — финальный концепт в архитектуре funpay-universal.
> Готов к реализации. Стартуем с плагина?
