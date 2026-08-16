# 🔧 Featly v2.2 — Аудит v2 (пост-фикс mimo-2.5)

> Дата: 2026-08-06
> Коммит: `5b16017` (audit critical fixes)
> Для: GLM5.2 — быстрый пробег по остаткам

---

## ⚠️ Как пользоваться этим файлом

Каждый пункт содержит:
- **Где** — файл + функция
- **Что** — конкретная проблема
- **Почему критично** — последствие
- **Фикс** — готовый код или точные шаги
- **Статус** — `TODO` / `PARTIAL` / `DONE` (от mimo-2.5)

---

## 🔴 БЛОК 1: СРОЧНО — Ломает запуск или работу

### 1.1 Синтаксическая ошибка: дубль `created_at` в `PendingTrade`

**Где:** `backend/app/models/pending_trade.py`

**Что:**
```python
class PendingTrade(Base):
    # ... поля ...
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_pending_trades_bot_status", "bot_id", "status"),
    )
    created_at: Mapped[datetime] = mapped_column(  # ← ДУБЛЬ, убрать
        DateTime(timezone=True), server_default=func.now()
    )
```

**Почему критично:** SQLAlchemy выбросит `InvalidRequestError` при импорте. Backend не запустится.

**Фикс:** Удалить второй блок `created_at` (строки после `__table_args__`).

**Статус:** TODO

---

### 1.2 `wait_for_template_async` создана, но не используется

**Где:** `engine/trade_flow.py` — все вызовы `wait_for_template()`

**Что:** mimo-2.5 добавил `wait_for_template_async()` в `cv_matcher.py`, но `trade_flow.py` всё ещё вызывает старую синхронную `wait_for_template()`, которая делает `time.sleep()` внутри `async def`. Блокирует event loop на 30+ секунд.

**Почему критично:** Engine зависает на каждом ожидании шаблона. WS heartbeat не шлётся, backend помечает Engine offline.

**Фикс:** Заменить все вызовы `wait_for_template(...)` на `wait_for_template_async(...)` в `trade_flow.py`.

```python
# Было:
found, center = wait_for_template(capture_screen, "trade_window.png", timeout=10)

# Стало:
found, center = await wait_for_template_async(capture_screen, "trade_window.png", timeout=10)
```

**Статус:** PARTIAL (функция есть, интеграции нет)

---

### 1.3 `is_roblox_focused()` создан, но не интегрирован

**Где:** `engine/roblox_window.py` (новый файл) + `engine/trade_flow.py`

**Что:** Функция есть, но `trade_flow.py` не вызывает её перед кликами. Клики уходят в Chrome/Discord, если пользователь переключил окно.

**Почему критично:** Бот может случайно купить что-то в браузере или написать в чат.

**Фикс:** В `trade_flow.py`, в начале `execute_trade()`:

```python
from engine.roblox_window import is_roblox_focused, focus_roblox

async def execute_trade(self, trade: dict) -> None:
    if not is_roblox_focused():
        logger.warning("Roblox not focused, attempting to refocus")
        if not focus_roblox():
            logger.error("Cannot focus Roblox — aborting trade")
            await self._on_fail(trade.get("order_id"), "Roblox window not focused")
            return
        await asyncio.sleep(0.5)
    # ... дальше обычный flow
```

**Статус:** PARTIAL

---

### 1.4 Проверка дубликата заказа — не атомарна

**Где:** `backend/app/services/order_service.py` → `create_order()`

**Что:**
```python
existing = await get_order_by_funpay_id(session, funpay_order_id)
if existing:
    return existing
# ... session.add(order); await session.commit()
```

Два одновременных запроса пройдут проверку и создадут 2 заказа.

**Почему критично:** Дубли заказов → дубли pending_trades → бот пытается выдать 2 раза.

**Фикс:** Добавить `try/except IntegrityError` вокруг `commit()`:

```python
from sqlalchemy.exc import IntegrityError

async def create_order(session, funpay_order_id, ...):
    existing = await get_order_by_funpay_id(session, funpay_order_id)
    if existing:
        return existing

    order = Order(...)
    session.add(order)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await get_order_by_funpay_id(session, funpay_order_id)
        if existing:
            return existing
        raise
    return order
```

**Статус:** TODO

---

### 1.5 `cookie_key` добавлен, но шифрование cookie не реализовано

**Где:** `backend/app/models/bot.py`

**Что:** `roblox_cookie` всё ещё хранится как plaintext `String(2048)`.

**Почему критично:** Утечка БД = угон аккаунта бота.

**Фикс:**

```python
# backend/app/models/bot.py
from cryptography.fernet import Fernet
from app.config import settings

cipher = Fernet(settings.cookie_key.encode()[:32].ljust(32, b'0')[:32])
# Или лучше: cookie_key должен быть 32-байтным base64-строкой

class Bot(Base):
    __tablename__ = "bots"

    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    _roblox_cookie_encrypted: Mapped[str] = mapped_column("roblox_cookie", String(2048), default="")
    status: Mapped[str] = mapped_column(String(32), default="offline")
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    ws_connected: Mapped[bool] = mapped_column(Boolean, default=False)

    @property
    def roblox_cookie(self) -> str:
        if not self._roblox_cookie_encrypted:
            return ""
        return cipher.decrypt(self._roblox_cookie_encrypted.encode()).decode()

    @roblox_cookie.setter
    def roblox_cookie(self, value: str) -> None:
        if not value:
            self._roblox_cookie_encrypted = ""
        else:
            self._roblox_cookie_encrypted = cipher.encrypt(value.encode()).decode()
```

**Важно:** `cookie_key` в `config.py` должен быть стабильным (не генерироваться заново при каждом рестарте), иначе старые cookie станут недешифруемыми. Сохранять в `.env` или файл.

**Статус:** TODO

---

## 🟠 БЛОК 2: ВАЖНО — Работает, но с рисками

### 2.1 Plugin: `!смена` — не обновляет waitlist

**Где:** `plugin/core/order_manager.py` → `_cmd_change_nick()`

**Что:** TODO в коде. Команда валидирует ник, но не шлёт PATCH на бэкенд и не обновляет pending_trade.

**Фикс:**
1. Добавить метод в `backend_client.py`:
```python
async def update_order_nickname(self, order_id: int, nickname: str, user_id: int) -> dict:
    return await self._patch(f"/orders/{order_id}", {"buyer_nickname": nickname, "buyer_user_id": user_id})
```
2. В `_cmd_change_nick`:
```python
async def _cmd_change_nick(chat_id, new_nick, acc):
    state = _dialog_states.get(chat_id)
    if not state:
        await acc.send_message(chat_id, "❌ Нет активного заказа")
        return

    user_id = await validate_username(new_nick)
    if not user_id:
        await acc.send_message(chat_id, f"❌ Ник '{new_nick}' не найден")
        return

    order_id = state.get("order_id")
    cached = orders_cache.get(order_id)
    if not cached:
        await acc.send_message(chat_id, "❌ Заказ не найден")
        return

    # Обновить backend
    await backend_client.update_order_nickname(cached["order_id"], new_nick, user_id)

    # Обновить pending_trade (нужен метод в backend_client)
    # WS → Engine: REMOVE_WAITLIST old + WAIT_FOR_TRADE new
    # (backend должен сам шлёт команды Engine при обновлении pending_trade)

    # Roblox API: новый friend request
    try:
        await request_friendship(user_id)
    except RobloxAuthError:
        await acc.send_message(chat_id, "⚠️ Ошибка авторизации Roblox")
        return

    await acc.send_message(chat_id, f"✅ Ник изменён на {new_nick}")
```

**Статус:** TODO

---

### 2.2 Plugin: `!отмена` — пустая заглушка

**Где:** `plugin/core/order_manager.py` → `_cmd_cancel()`

**Что:** Функция пустая.

**Фикс:**
```python
async def _cmd_cancel(chat_id, acc):
    state = _dialog_states.get(chat_id)
    if not state:
        await acc.send_message(chat_id, "❌ Нет активного заказа")
        return

    await acc.send_message(chat_id, "Подтверди отмену: Да / Нет")
    state["step"] = "confirming_cancel"

# В _handle_dialog_step:
elif step == "confirming_cancel":
    if text.lower() in ("да", "yes"):
        order_id = state["order_id"]
        cached = orders_cache.get(order_id)
        if cached:
            await backend_client.cancel_order(cached["order_id"])
            orders_cache.remove(order_id)
        await acc.send_message(chat_id, "❌ Заказ отменён. Оформляю возврат...")
        # FunPay: ручной возврат (авто-возврат через funpay-universal API если доступен)
    else:
        await acc.send_message(chat_id, "Отмена отменена 😄")
    _dialog_states.pop(chat_id, None)
```

**Статус:** TODO

---

### 2.3 Plugin: `!фото` — нет интеграции с Engine

**Где:** `plugin/core/order_manager.py` → `_cmd_screenshot()`

**Что:** Нужно получить скриншот с Engine и отправить в чат FunPay.

**Фикс (простой вариант):**
1. Engine при получении команды `SCREENSHOT` делает скриншот → POST `/proofs` с `type: "admin_screenshot"`
2. Plugin раз в 3 сек опрашивает `GET /proofs/latest?bot_id=...`
3. При получении URL → `acc.send_message(chat_id, "Скрин: {url}")`

**Или через WS relay:**
- Plugin HTTP → Backend → Engine WS (`{"action": "SCREENSHOT"}`)
- Engine POST `/proofs` → Plugin polling `GET /proofs/latest`

**Статус:** TODO

---

### 2.4 Plugin: `orders_cache` — не thread-safe

**Где:** `plugin/data.py` → `OrdersCache`

**Что:** Обычный `dict` без блокировок. funpay-universal может вызывать хендлеры конкурентно.

**Фикс:**
```python
import asyncio

class OrdersCache:
    def __init__(self, path: str = "orders_cache.json"):
        self._path = path
        self._cache: dict[str, dict] = {}
        self._lock = asyncio.Lock()
        self._load()

    async def set(self, funpay_order_id: str, data: dict) -> None:
        async with self._lock:
            self._cache[funpay_order_id] = data
            self._save()

    async def get(self, funpay_order_id: str) -> dict | None:
        async with self._lock:
            return self._cache.get(funpay_order_id)

    async def remove(self, funpay_order_id: str) -> None:
        async with self._lock:
            self._cache.pop(funpay_order_id, None)
            self._save()
```

**Важно:** Все вызовы `orders_cache.set()` / `get()` / `remove()` в плагине уже `await` — нужно только добавить `async` в сигнатуры `OrdersCache`.

**Статус:** TODO

---

### 2.5 Plugin: `ITEM_PAID` без cached order

**Где:** `plugin/handlers/funpay.py` → `on_item_paid()`

**Что:** Если `ITEM_PAID` приходит до завершения диалога — `cached` будет None, статус не обновится.

**Фикс:**
```python
_deferred_payments: dict[str, Any] = {}

async def on_item_paid(deal, acc) -> None:
    cached = orders_cache.get(deal.order_id)
    if cached:
        await backend_client.update_order_status(cached["order_id"], "waiting_trade")
    else:
        _deferred_payments[deal.order_id] = deal
        logger.warning(f"ITEM_PAID deferred for {deal.order_id}")

# В order_manager.py, при завершении диалога (после "Да"):
async def _finish_dialog(chat_id, state, acc):
    # ... создание заказа ...
    # Проверить deferred payments
    deferred = _deferred_payments.pop(state["funpay_order_id"], None)
    if deferred:
        await backend_client.update_order_status(order_id, "waiting_trade")
```

**Статус:** TODO

---

### 2.6 Backend: WS — нет очереди сообщений для offline Engine

**Где:** `backend/app/ws/engine.py` → `send_to_engine()`

**Что:** Если Engine offline в момент отправки команды — команда теряется навсегда.

**Фикс:**
```python
message_queue: dict[str, asyncio.Queue] = {}

async def send_to_engine(bot_id: str, message: dict) -> bool:
    ws = connections.get(bot_id)
    if ws is None:
        if bot_id not in message_queue:
            message_queue[bot_id] = asyncio.Queue(maxsize=100)
        try:
            message_queue[bot_id].put_nowait(message)
        except asyncio.QueueFull:
            logger.warning(f"Queue full for {bot_id}")
        return False
    try:
        await ws.send_json(message)
        return True
    except Exception:
        connections.pop(bot_id, None)
        return False

# При подключении Engine:
async def engine_websocket(websocket: WebSocket, bot_id: str, ...):
    # ... auth ...
    connections[bot_id] = websocket

    # Доставить накопленные
    queue = message_queue.pop(bot_id, None)
    if queue:
        while not queue.empty():
            msg = queue.get_nowait()
            await websocket.send_json(msg)
```

**Статус:** TODO

---

### 2.7 Backend: State machine для OrderStatus — нет валидации переходов

**Где:** `backend/app/services/order_service.py` → `update_order_status()`

**Что:** Любой статус можно установить из любого. `COMPLETED` → `NEW` — возможно.

**Фикс:**
```python
from app.models.order import OrderStatus

VALID_TRANSITIONS = {
    OrderStatus.NEW: [OrderStatus.DIALOG, OrderStatus.CANCELLED],
    OrderStatus.DIALOG: [OrderStatus.WAITING_TRADE, OrderStatus.CANCELLED],
    OrderStatus.WAITING_TRADE: [OrderStatus.DELIVERING, OrderStatus.CANCELLED],
    OrderStatus.DELIVERING: [OrderStatus.COMPLETED, OrderStatus.FAILED],
    OrderStatus.FAILED: [OrderStatus.DELIVERING],  # retry
    OrderStatus.COMPLETED: [],
    OrderStatus.CANCELLED: [],
}

async def update_order_status(session, order_id, new_status, proof_url=None):
    order = await get_order_by_id(session, order_id)
    if not order:
        return None

    current = order.status
    if new_status not in VALID_TRANSITIONS.get(current, []):
        logger.warning(f"Invalid transition: {current} → {new_status}")
        raise ValueError(f"Cannot transition from {current} to {new_status}")

    order.status = new_status
    if new_status == OrderStatus.COMPLETED:
        order.completed_at = datetime.now(timezone.utc)
    if proof_url:
        order.proof_url = proof_url
    await session.commit()
    return order
```

**Статус:** TODO

---

### 2.8 Backend: `items` как JSON-строка в VARCHAR(512)

**Где:** `backend/app/models/order.py`, `pending_trade.py`

**Что:** `items: Mapped[str] = mapped_column(String(512))` — строка, не JSONB.

**Фикс:**
```python
from sqlalchemy.dialects.postgresql import JSONB

# order.py + pending_trade.py
items: Mapped[list[str]] = mapped_column(JSONB, default=list)
```

**Важно:** Нужна Alembic-миграция для конвертации существующих данных.

**Статус:** TODO

---

### 2.9 Engine: `_wait_for_countdown` — фиксированный sleep

**Где:** `engine/trade_flow.py` → `_wait_for_countdown()`

**Что:** `await asyncio.sleep(7.0)` — ждёт фиксированно. Если игра лагает — кнопка ещё серая.

**Фикс:** Детект зелёной кнопки по шаблону:

```python
async def _wait_for_countdown(self) -> None:
    self.state = TradeState.WAITING_COUNTDOWN
    for _ in range(10):  # max 10 sec
        await asyncio.sleep(1.0)
        screenshot = capture_screen()
        found, center = detect_template(screenshot, "accept_green.png", threshold=0.7)
        if found:
            logger.info("Green accept detected")
            await async_click(center[0], center[1])
            return
    logger.warning("Green accept not found, fallback to fixed delay")
    await asyncio.sleep(2.0)
    await self._click_accept()  # fallback
```

**Требуется:** Добавить шаблон `engine/templates/accept_green.png` (скриншот активной зелёной кнопки Accept в MM2).

**Статус:** TODO

---

### 2.10 Engine: Нет проверки MM2 HUD перед сканированием

**Где:** `engine/main.py` → scan loop

**Что:** Если бот в лобби (не в игре) — шаблоны не найдутся, но сканирование продолжается бесконечно.

**Фикс:**
```python
# В начале каждой итерации scan loop:
screenshot = capture_screen()
if not detect_template(screenshot, "mm2_hud.png", threshold=0.6)[0]:
    logger.warning("MM2 HUD not detected — bot in lobby or disconnected")
    await ws_client.report_status("no_hud")
    await asyncio.sleep(10)
    continue
```

**Требуется:** Шаблон `engine/templates/mm2_hud.png`.

**Статус:** TODO

---

### 2.11 Backend: Inline-импорты в `orders.py`

**Где:** `backend/app/routes/orders.py` — `from sqlalchemy import select` и `from app.models.order import Order` внутри функций.

**Что:** Признак циклического импорта, пофикшенного костылём.

**Фикс:** Вынести импорты наверх файла. Если циклический импорт — пересмотреть структуру (вынести общие типы в `schemas.py`).

**Статус:** TODO

---

### 2.12 Backend: `send_to_engine` — race condition

**Где:** `backend/app/ws/engine.py`

**Что:**
```python
ws = connections.get(bot_id)
if ws is None:
    return False
await ws.send_json(message)  # ws может закрыться между get и send_json
```

**Фикс:** Оборачивать `send_json` в `try/except` и удалять из `connections` при ошибке (уже частично есть, но не полностью).

**Статус:** PARTIAL

---

## 🟡 БЛОК 3: УЛУЧШЕНИЯ — После стабилизации

### 3.1 Graceful shutdown
**Где:** `backend/app/main.py`
**Фикс:** Закрыть все WS-соединения при `lifespan` shutdown.

### 3.2 Circuit breaker для Roblox API
**Где:** `plugin/core/roblox_api.py`
**Фикс:** `@circuit(failure_threshold=3, recovery_timeout=60)` на `request_friendship()`.

### 3.3 Prometheus метрики
**Где:** `backend/app/main.py`
**Фикс:** `prometheus_client` — счётчики trades_completed, trades_failed.

### 3.4 Health endpoint для Engine
**Где:** `engine/main.py`
**Фикс:** HTTP `/health` на отдельном порту (aiohttp или fastapi).

### 3.5 Event sourcing (опционально)
**Где:** Новая таблица `order_events`
**Фикс:** Логировать все переходы статусов для аудита.

### 3.6 Alembic-миграция для composite index
**Где:** `backend/alembic/versions/`
**Фикс:** Автогенерация миграции после добавления `__table_args__` в `PendingTrade`.

---

## 📋 Чек-лист для GLM5.2

### Приоритет P0 (баги, ломающие запуск)
- [ ] 1.1 Убрать дубль `created_at` в `pending_trade.py`
- [ ] 1.2 Заменить `wait_for_template` → `wait_for_template_async` в `trade_flow.py`
- [ ] 1.3 Интегрировать `is_roblox_focused()` в `trade_flow.py`
- [ ] 1.4 Добавить `try/except IntegrityError` в `create_order()`

### Приоритет P1 (критическая функциональность)
- [ ] 1.5 Реализовать шифрование `roblox_cookie` в `models/bot.py`
- [ ] 2.1 Реализовать `!смена` — PATCH + WS-команды
- [ ] 2.2 Реализовать `!отмена` — подтверждение + удаление
- [ ] 2.3 Реализовать `!фото` — polling или relay
- [ ] 2.4 Сделать `OrdersCache` thread-safe (async lock)
- [ ] 2.5 Добавить deferred payments для `ITEM_PAID`
- [ ] 2.6 Добавить WS message queue для offline Engine
- [ ] 2.7 Добавить state machine валидацию для OrderStatus
- [ ] 2.8 Перевести `items` на PostgreSQL JSONB
- [ ] 2.9 Детект зелёной кнопки в `_wait_for_countdown()`
- [ ] 2.10 Проверка MM2 HUD перед сканированием

### Приоритет P2 (стабильность)
- [ ] 2.11 Вынести inline-импорты из `orders.py`
- [ ] 2.12 Полный `try/except` в `send_to_engine()`
- [ ] 3.1 Graceful shutdown
- [ ] 3.6 Alembic миграция

### Приоритет P3 (фичи)
- [ ] 3.2 Circuit breaker
- [ ] 3.3 Prometheus
- [ ] 3.4 Engine health endpoint

---

## 🗺️ Архитектурные заметки (для контекста)

### Поток данных (как должно работать)
```
FunPay deal → Plugin диалог → Roblox API дружба → POST /orders → 
  → pending_trade в БД → WS WAIT_FOR_TRADE → Engine сканирование → 
  → Accept → Items → Confirm → POST /proofs → WS trade_completed → 
  → PATCH status=completed → DELETE pending_trade → PATCH inventory--
```

### Что уже работает (mimo-2.5)
- API-Key auth на всех роутерах
- Auto-generated secrets
- Duplicate order check (но не атомарно)
- Composite index
- FAILSAFE + emergency stop flag
- Fuzzy match для ников
- `_close_trade_window()` при фейле
- `wait_for_template_async()` (но не используется)
- `is_roblox_focused()` (но не интегрирован)

### Главный риск сейчас
**Engine может зависнуть** из-за синхронного `wait_for_template()` + отсутствие проверки фокуса окна. Это приоритет #1 после синтаксической ошибки.
