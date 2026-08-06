# 🔧 Featly v2.2 — Аудит кода + Корректировки для mimo-2.5

> Дата аудита: 2026-08-06
> Ревизия: master (последний коммит)
> Статус: MVP на 70%, **не готов к продакшену**

---

## 📊 Общая оценка

| Компонент | Состояние | Критичность |
|-----------|-----------|-------------|
| **Backend (FastAPI)** | 🟡 Хороший каркас, но есть дыры в безопасности и транзакциях | Средняя |
| **Plugin (funpay-universal)** | 🟡 Работает базовый flow, но много TODO и нет обработки ошибок | Высокая |
| **Windows Engine** | 🟠 CV + клики есть, но логика трейда хрупкая, нет защиты от race condition | Критическая |
| **WebSocket** | 🟡 Работает, но heartbeat не проверяет таймауты на стороне backend | Средняя |
| **Инфраструктура** | 🟢 Docker, Alembic, CI — всё на месте | Низкая |

**Итог:** Проект идёт в правильном направлении, но перед запуском в прод нужно закрыть 12 критических пунктов.

---

## 🔴 КРИТИЧЕСКИЕ — Закрыть в первую очередь

### 1. Roblox cookie хранится в открытом виде

**Где:** `plugin/settings.py` (JSON-файл), `backend/app/models/bot.py` (PostgreSQL), `backend/app/config.py` (env)

**Проблема:** `.ROBLOSECURITY` — это полноценный session token. Если VPS скомпрометирован — угон аккаунта бота.

**Решение:**
```python
# backend/app/models/bot.py — шифровать перед сохранением
from cryptography.fernet import Fernet

class Bot(Base):
    # ...
    roblox_cookie_encrypted: Mapped[str] = mapped_column(String(2048), default="")

    @property
    def roblox_cookie(self) -> str:
        return cipher.decrypt(self.roblox_cookie_encrypted.encode()).decode()

    @roblox_cookie.setter
    def roblox_cookie(self, value: str) -> None:
        self.roblox_cookie_encrypted = cipher.encrypt(value.encode()).decode()
```
- Ключ шифрования — `FEATLY_COOKIE_KEY` (32 байта, base64), **не коммитить в репо**
- В `plugin/settings.py` тоже шифровать или не хранить локально вообще (только в памяти)

---

### 2. WebSocket secret — hardcoded default

**Где:** `backend/app/config.py` → `ws_secret: str = "change-me-in-production"`

**Проблема:** Если админ забудет поменять — любой может подключиться к WS и имитировать Engine.

**Решение:**
```python
# Генерировать случайный secret при первом запуске, если не задан env
import secrets

class Settings(BaseSettings):
    ws_secret: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
```
- При `docker-compose up` выводить в лог: `⚠️ Generated random WS_SECRET: xxx...`
- Добавить health-check endpoint, который проверяет, что secret != default

---

### 3. Отсутствие авторизации на REST API

**Где:** Все роутеры в `backend/app/routes/`

**Проблема:** `POST /orders`, `DELETE /pending_trades/{id}` — открыты миру. Любой может создать фейковый заказ или удалить waitlist.

**Решение:**
```python
# Добавить API-Key middleware
from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")

async def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != settings.api_key:
        raise HTTPException(403, "Invalid API key")

# В роутерах:
router = APIRouter(dependencies=[Depends(verify_api_key)])
```
- `FEATLY_API_KEY` — генерировать при первом запуске, показывать в логах
- Plugin и Engine передавать этот ключ в заголовках

---

### 4. Race condition в trade_flow.py — двойной Accept

**Где:** `engine/trade_flow.py` → `_click_accept()` → `_handle_are_you_sure()`

**Проблема:**
```python
# Step 6
await async_click(cx + cw // 2, cy + ch // 2)  # Accept (серый)
await asyncio.sleep(1.5)
# Step 7
await self._handle_are_you_sure()  # Accept (зелёный / Yes)
```

В MM2 после первого Accept идёт **обратный отсчёт 6-7 секунд** («Please wait (X) before accepting»). Код ждёт фиксированные 7 секунд в `_wait_for_countdown()`, но:
- Если игра лагает — кнопка ещё серая, клик по Yes пройдёт мимо
- Если покупатель уже принял и закрыл трейд — бот кликнет в пустоту
- Нет проверки, что окно трейда всё ещё открыто

**Решение:**
```python
async def _wait_for_countdown(self) -> None:
    self.state = TradeState.WAITING_COUNTDOWN
    # Проверять каждую секунду, стала ли кнопка активной (зелёной)
    for _ in range(10):  # max 10 sec
        await asyncio.sleep(1.0)
        screenshot = capture_screen()
        # Детектим зелёную кнопку по шаблону accept_green.png
        found, center = detect_template(screenshot, "accept_green.png", threshold=0.7)
        if found:
            logger.info("Green accept button detected")
            await async_click(center[0], center[1])
            return
    logger.warning("Green accept not detected, trying fallback...")
    await self._click_accept()  # fallback
```
- Добавить шаблон `accept_green.png` (скриншот активной зелёной кнопки)
- После каждого клика проверять, что окно трейда ещё открыто (`search_box.png` или `your_offer.png`)

---

### 5. OCR nickname — слишком агрессивная очистка

**Где:** `engine/ocr.py` → `read_nickname_from_trade()`

**Проблема:**
```python
cleaned = "".join(c for c in text if c.isalnum() or c == "_")
```

Roblox ники могут содержать **пробелы** (редко, но бывают в display names) и **дефисы** (в старых никах — нет, но в display names — да). `isalnum()` удалит всё.

**Решение:**
```python
def read_nickname_from_trade(self, screenshot, region=None) -> str | None:
    text = self.read_text(screenshot, region, preprocess="thresh")
    text = text.strip()
    if not text or len(text) < 2:
        return None
    # Roblox username rules: 3-20 chars, alphanumeric + underscore
    # Display names: 1-20 chars, alphanumeric + spaces
    # Будем мягче — убираем только мусор OCR
    cleaned = text.replace("|", "").replace("Trade", "").replace("Request", "").strip()
    return cleaned if len(cleaned) >= 3 else None
```
- Добавить fallback: если OCR не сработал — использовать ник из waitlist (проверять по совпадению части строки)
- **Главное:** в `waitlist_manager.find_by_buyer()` делать fuzzy match, а не exact:
```python
def find_by_buyer(self, buyer_nickname: str) -> dict | None:
    buyer_lower = buyer_nickname.lower()
    for trade in self._waitlist:
        nick = trade.get("buyer_nickname", "").lower()
        if buyer_lower in nick or nick in buyer_lower or levenshtein(buyer_lower, nick) <= 2:
            return trade
    return None
```

---

### 6. Плагин не обрабатывает `ITEM_PAID` корректно

**Где:** `plugin/handlers/funpay.py` → `on_item_paid()`

**Проблема:**
```python
async def on_item_paid(deal, acc) -> None:
    cached = orders_cache.get(deal.order_id)
    if cached:
        await backend_client.update_order_status(cached["order_id"], "waiting_trade")
```

- `ITEM_PAID` приходит **до** `NEW_DEAL` или **после** — не гарантировано. Если `NEW_DEAL` ещё не обработался — `cached` будет None, статус не обновится.
- Нет создания заказа, если его ещё нет (хотя в v2.2 заказ создаётся в диалоге, а не по оплате)

**Решение:**
```python
async def on_item_paid(deal, acc) -> None:
    cached = orders_cache.get(deal.order_id)
    if cached:
        await backend_client.update_order_status(cached["order_id"], "waiting_trade")
    else:
        # Заказа нет в кэше — возможно, диалог ещё не завершён
        # Сохраняем в "deferred_payments" и обработаем при завершении диалога
        _deferred_payments[deal.order_id] = deal
        logger.warning(f"ITEM_PAID for {deal.order_id} but no cached order yet")
```
- В `order_manager.py` при завершении диалога проверять `_deferred_payments`

---

### 7. Backend WS — нет защиты от спама и reconnect-флуда

**Где:** `backend/app/ws/engine.py`

**Проблема:**
- Engine может реконнектиться каждые 5 секунд (при ошибке) — бесконечный цикл
- Нет rate limiting на `request_waitlist`
- `keepalive` шлёт `ping` каждые 20 сек, но не проверяет `pong` — бесполезен

**Решение:**
```python
# Добавить rate limiter
from asyncio import Queue

class EngineConnection:
    def __init__(self, ws, bot_id):
        self.ws = ws
        self.bot_id = bot_id
        self.last_heartbeat = datetime.now(timezone.utc)
        self.reconnect_count = 0
        self.last_reconnect = None

async def _handle_engine_message(bot_id, data):
    conn = connections.get(bot_id)
    if not conn:
        return

    if msg_type == "request_waitlist":
        # Rate limit: max 1 запрос в 5 секунд
        now = datetime.now(timezone.utc)
        if conn.last_waitlist_request and (now - conn.last_waitlist_request).seconds < 5:
            return
        conn.last_waitlist_request = now
        # ...
```
- Убрать `keepalive` (лишний) — heartbeat от Engine достаточно
- На backend: если heartbeat не приходил > 90 сек — помечать `ws_connected = False`

---

### 8. `pdi.FAILSAFE = False` — опасно

**Где:** `engine/input_controller.py`

**Проблема:**
```python
pdi.FAILSAFE = False
```

Если Engine уйдёт в бесконечный цикл кликов — нет способа остановить его, кроме как убить процесс. В худшем случае — клики по рабочему столу, случайные покупки, открытие программ.

**Решение:**
```python
# Не отключать failsafe, а настроить corner-зону
pdi.FAILSAFE = True
pdi.PAUSE = 0.05  # минимальная пауза между действиями

# Добавить emergency stop — проверку перед каждым кликом
_emergency_stop = False

async def safe_click(x, y, button="left"):
    if _emergency_stop:
        raise RuntimeError("Emergency stop activated")
    # Проверить, что окно Roblox активно
    if not is_roblox_focused():
        logger.warning("Roblox not focused — aborting click")
        raise RuntimeError("Roblox window lost focus")
    await async_click(x, y, button)
```
- Добавить глобальный хоткей `Ctrl+Shift+F12` → emergency stop

---

### 9. Отсутствие rollback при ошибке трейда

**Где:** `engine/trade_flow.py`

**Проблема:** Если трейд зафейлился на шаге 5 (Adding items), Engine переходит в `FAILED`, но:
- Предметы могли уже лежать в окне трейда
- Окно трейда осталось открытым
- Бэкенд не получит уведомление о необходимости вернуть предмет в инвентарь

**Решение:**
```python
async def _on_fail(self, order_id, error):
    logger.error(f"Trade failed: {order_id}, {error}")

    # 1. Закрыть окно трейда, если открыто
    await self._close_trade_window()

    # 2. Уведомить backend
    if self._on_trade_failed and order_id:
        await self._on_trade_failed(order_id, error)

    # 3. Вернуть предметы в инвентарь (backend откатит count)
    # 4. Оставить в waitlist для повторной попытки
    # (не удалять из waitlist при фейле — только при success или cancel)

    self.state = TradeState.IDLE

async def _close_trade_window(self):
    # Нажать ESC или кликнуть Decline
    await async_press("esc")
    await asyncio.sleep(0.5)
```

---

## 🟠 ВАЖНЫЕ — Закрыть до первого теста

### 10. Плагин: `!смена` не обновляет waitlist

**Где:** `plugin/core/order_manager.py` → `_cmd_change_nick()`

**Проблема:** TODO в коде. Команда валидирует ник, но не шлёт PATCH на бэкенд и не обновляет pending_trade.

**Реализация:**
```python
async def _cmd_change_nick(chat_id, new_nick, acc):
    # 1. Найти активный заказ для этого chat_id
    state = _dialog_states.get(chat_id)
    if not state:
        # Ищем в кэше по chat_id (нужно добавить chat_id в orders_cache)
        await acc.send_message(chat_id, "❌ Нет активного заказа для смены ника")
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

    # 2. Обновить order в backend
    await backend_client.update_order_nickname(cached["order_id"], new_nick, user_id)
    # (нужно добавить метод в backend_client)

    # 3. Отправить новый friend request
    try:
        await request_friendship(user_id)
    except RobloxAuthError:
        await acc.send_message(chat_id, "⚠️ Ошибка авторизации Roblox")
        return

    # 4. WS → Engine: REMOVE_WAITLIST old + WAIT_FOR_TRADE new
    # (нужен endpoint в backend для этого)

    await acc.send_message(chat_id, f"✅ Ник изменён на {new_nick}")
```

---

### 11. Плагин: `!отмена` не реализована

**Где:** `_cmd_cancel()` — пустая заглушка.

**Реализация:**
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
            # Удалить pending_trade
            # TODO: нужен метод backend_client.delete_pending_trade_by_order_id()
            await backend_client.cancel_order(cached["order_id"])
            orders_cache.remove(order_id)
        await acc.send_message(chat_id, "❌ Заказ отменён. Оформляю возврат...")
        # FunPay: возврат через funpay-universal API (если доступен)
    else:
        await acc.send_message(chat_id, "Отмена отменена 😄")
    _dialog_states.pop(chat_id, None)
```

---

### 12. Плагин: `!фото` — нет интеграции с Engine

**Где:** `_cmd_screenshot()`

**Проблема:** Нужно отправить WS-команду `SCREENSHOT`, дождаться `screenshot_taken`, получить URL, отправить в чат.

**Реализация:**
- Backend должен поддерживать relay: Plugin HTTP → Backend → Engine WS → Backend → Plugin HTTP (polling или webhook)
- Или проще: Engine делает скриншот → POST `/proofs` → Plugin раз в 5 сек опрашивает `/proofs/latest`

---

### 13. Backend: `items` хранится как JSON-строка

**Где:** `backend/app/models/order.py`, `pending_trade.py`

**Проблема:**
```python
items: Mapped[str] = mapped_column(String(512))  # JSON array as string
```

- Нельзя искать по предметам в SQL
- Нельзя делать `JOIN` с инвентарём
- Риск corrupted data

**Решение:**
```python
# 1. Нормализация — отдельная таблица order_items
class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    item_key: Mapped[str] = mapped_column(String(128))
    quantity: Mapped[int] = mapped_column(Integer, default=1)

# 2. Или использовать PostgreSQL JSONB
from sqlalchemy.dialects.postgresql import JSONB
items: Mapped[list[str]] = mapped_column(JSONB, default=list)
```
- **Рекомендация:** JSONB — проще для MVP, нормализация — для масштаба

---

### 14. Backend: Нет индекса на `pending_trades.status`

**Где:** `backend/app/models/pending_trade.py`

**Проблема:**
```python
status: Mapped[PendingTradeStatus] = mapped_column(
    Enum(PendingTradeStatus), default=PendingTradeStatus.WAITING, index=True
)
```

Индекс есть, но в `_get_waitlist()` фильтр по `bot_id` + `status` — нужен **композитный индекс**:
```python
from sqlalchemy import Index

class PendingTrade(Base):
    __tablename__ = "pending_trades"
    # ...
    __table_args__ = (
        Index("ix_pending_trades_bot_status", "bot_id", "status"),
    )
```

---

### 15. Engine: `wait_for_template` — блокирующий sleep

**Где:** `engine/cv_matcher.py`

**Проблема:**
```python
def wait_for_template(screenshot_fn, ...):
    import time
    while time.monotonic() - start < timeout:
        screenshot = screenshot_fn()
        # ...
        time.sleep(interval)  # БЛОКИРУЮЩИЙ sleep в async-контексте!
```

Эта функция вызывается из `async def`, но сама синхронная. Блокирует event loop на `timeout` секунд.

**Решение:**
```python
async def wait_for_template_async(
    screenshot_fn,
    template_name: str,
    threshold: float = 0.8,
    timeout: float = 30.0,
    interval: float = 0.5,
) -> tuple[bool, tuple[int, int] | None]:
    start = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start < timeout:
        screenshot = await asyncio.to_thread(screenshot_fn)
        found, center = detect_template(screenshot, template_name, threshold)
        if found:
            return True, center
        await asyncio.sleep(interval)
    return False, None
```
- Переименовать старую в `wait_for_template_sync` для синхронных вызовов

---

### 16. Engine: `TradeFlow` не проверяет фокус окна Roblox

**Где:** `engine/trade_flow.py`

**Проблема:** Если пользователь свернёт Roblox или переключится в Chrome — клики уйдут не туда.

**Решение:**
```python
# Добавить в main.py или trade_flow.py
import pywinctl as pwc

def is_roblox_focused() -> bool:
    try:
        win = pwc.getActiveWindow()
        return win and "roblox" in win.title.lower()
    except Exception:
        return False

# В начале каждого трейда:
if not is_roblox_focused():
    logger.warning("Roblox not focused — aborting trade")
    # Попытаться вернуть фокус
    try:
        wins = pwc.getWindowsWithTitle("Roblox")
        if wins:
            wins[0].activate()
            await asyncio.sleep(0.5)
    except Exception:
        pass
```

---

### 17. Engine: Нет проверки, что бот не в AFK-лобби

**Проблема:** Если Roblox кикнул в лобби (не в игре MM2) — шаблоны не найдутся, но Engine будет бесконечно сканировать.

**Решение:**
```python
# В начале scan loop:
screenshot = capture_screen()
if not detect_template(screenshot, "mm2_hud.png", threshold=0.6)[0]:
    logger.warning("MM2 HUD not detected — bot may be in lobby or disconnected")
    await self.ws_client.report_status("no_hud")
    await asyncio.sleep(10)
    return
```

---

### 18. Plugin: `orders_cache` — не thread-safe

**Где:** `plugin/data.py`

**Проблема:** `OrdersCache` использует обычный `dict` без блокировок. funpay-universal может вызывать хендлеры из разных тредов/корутин.

**Решение:**
```python
import asyncio

class OrdersCache:
    def __init__(self):
        self._cache: dict[str, dict] = {}
        self._lock = asyncio.Lock()

    async def set(self, funpay_order_id: str, data: dict) -> None:
        async with self._lock:
            self._cache[funpay_order_id] = data
            self._save()

    async def get(self, funpay_order_id: str) -> dict | None:
        async with self._lock:
            return self._cache.get(funpay_order_id)
```
- Или использовать `functools.lru_cache` + `threading.Lock`, если funpay-universal синхронный

---

### 19. Backend: `send_to_engine` — нет очереди сообщений

**Где:** `backend/app/ws/engine.py`

**Проблема:**
```python
async def send_to_engine(bot_id: str, message: dict) -> bool:
    ws = connections.get(bot_id)
    if ws is None:
        return False
    try:
        await ws.send_json(message)
        return True
    except Exception:
        return False
```

Если Engine отключился между проверкой `ws is not None` и `send_json` — исключение.

**Решение:**
```python
import weakref

connections: dict[str, WebSocket] = {}
message_queue: dict[str, asyncio.Queue] = {}  # Очередь для offline-ботов

async def send_to_engine(bot_id: str, message: dict) -> bool:
    ws = connections.get(bot_id)
    if ws is None:
        # Сохранить в очередь для доставки при reconnect
        if bot_id not in message_queue:
            message_queue[bot_id] = asyncio.Queue(maxsize=100)
        try:
            message_queue[bot_id].put_nowait(message)
        except asyncio.QueueFull:
            logger.warning(f"Message queue full for {bot_id}")
        return False
    try:
        await ws.send_json(message)
        return True
    except Exception:
        connections.pop(bot_id, None)
        return False

# При подключении Engine:
async def engine_websocket(websocket: WebSocket):
    # ...
    # Доставить накопленные сообщения
    queue = message_queue.pop(bot_id, None)
    if queue:
        while not queue.empty():
            msg = queue.get_nowait()
            await websocket.send_json(msg)
```

---

### 20. Backend: Нет обработки дублирования заказов

**Где:** `backend/app/services/order_service.py` → `create_order()`

**Проблема:** Если FunPay пришлёт `NEW_DEAL` дважды (реконнект polling) — создастся 2 заказа.

**Решение:**
```python
async def create_order(session, funpay_order_id, ...):
    # Проверить существование
    existing = await get_order_by_funpay_id(session, funpay_order_id)
    if existing:
        logger.info(f"Order {funpay_order_id} already exists, skipping")
        return existing

    order = Order(...)
    session.add(order)
    await session.commit()
    return order
```
- Добавить `UNIQUE` constraint на `funpay_order_id` (уже есть в модели! — проверить, что Alembic-миграция создаёт индекс)

---

## 🟡 УЛУЧШЕНИЯ — Сделать после MVP

### 21. Добавить health-check для Engine

**Где:** `engine/main.py`

```python
# Добавить HTTP health endpoint (опционально, на отдельном порту)
from aiohttp import web

async def health_handler(request):
    return web.Response(text="ok", status=200)

app = web.Application()
app.router.add_get("/health", health_handler)
# Запускать параллельно с основным циклом
```

---

### 22. Логирование в structured JSON

**Где:** Все компоненты

```python
# Вместо текстовых логов — JSON для парсинга в Grafana/Loki
logger.add(
    "logs/featly.json",
    serialize=True,
    format="{message}",
    rotation="1 day",
)
```

---

### 23. Метрики (Prometheus)

**Где:** Backend

```python
from prometheus_client import Counter, Histogram

trades_completed = Counter("featly_trades_completed", "Completed trades", ["item"])
trades_failed = Counter("featly_trades_failed", "Failed trades", ["reason"])
trade_duration = Histogram("featly_trade_duration_seconds", "Trade duration")
```

---

### 24. Профили игр — валидация YAML

**Где:** `engine/config.py`

```python
from pydantic import validator

class EngineConfig(BaseModel):
    # ...
    @validator("scan_interval")
    def scan_interval_positive(cls, v):
        if v < 0.5:
            raise ValueError("scan_interval must be >= 0.5 (CPU safety)")
        return v
```

---

### 25. Админка — минимальный React

**Где:** `admin/` (папка уже есть, но пустая)

**Минимум:**
- Таблица заказов (статус, ник, предмет, время)
- Таблица инвентаря (количество, порог)
- Кнопка «Перезапустить Engine» (WS-команда)
- Логи в реальном времени (SSE или WS)

---

## 📝 Чек-лист для mimo-2.5

### Неделя 1: Безопасность + Стабильность
- [ ] **P1** Шифрование `roblox_cookie` в БД и в `settings.json`
- [ ] **P1** API-Key middleware на всех роутерах backend
- [ ] **P1** Генерация случайного `ws_secret` при первом запуске
- [ ] **P1** Убрать `pdi.FAILSAFE = False`, добавить `is_roblox_focused()`
- [ ] **P2** Добавить `UNIQUE` constraint на `orders.funpay_order_id` + проверка в `create_order`
- [ ] **P2** Композитный индекс `pending_trades(bot_id, status)`

### Неделя 2: Trade Flow (Engine)
- [ ] **P1** Реализовать `_wait_for_countdown()` через детект зелёной кнопки
- [ ] **P1** Добавить `_close_trade_window()` при фейле
- [ ] **P1** Fuzzy match для ника в `waitlist_manager.find_by_buyer()`
- [ ] **P2** Проверка `mm2_hud.png` перед каждым сканированием
- [ ] **P2** `wait_for_template` → `async` версия
- [ ] **P2** Emergency stop (Ctrl+Shift+F12)

### Неделя 3: Plugin + Интеграция
- [ ] **P1** Реализовать `!смена` — PATCH order + WS-команды
- [ ] **P1** Реализовать `!отмена` — подтверждение + удаление pending_trade + возврат
- [ ] **P1** Реализовать `!фото` — relay через backend или polling
- [ ] **P2** Обработка `ITEM_PAID` без cached order (deferred payments)
- [ ] **P2** Thread-safe `OrdersCache` (async lock)
- [ ] **P2** Telegram-алерты при ошибках (Roblox 401, Engine offline, stock = 0)

### Неделя 4: Backend + WS
- [ ] **P1** Очередь сообщений для offline Engine
- [ ] **P1** Rate limiting на `request_waitlist` (1 раз в 5 сек)
- [ ] **P2** Heartbeat timeout detection (90 сек → offline)
- [ ] **P2** `items` → PostgreSQL JSONB
- [ ] **P2** Алерты на low stock (после каждого успешного трейда)
- [ ] **P3** Dockerfile для Engine (если будет VPS Windows)

### Неделя 5: Тестирование
- [ ] **P1** End-to-end: FunPay deal → диалог → дружба → трейд → proof
- [ ] **P1** Тест реконнекта Engine (убить WS → проверить recovery)
- [ ] **P1** Тест `!отмена` — заказ удаляется из waitlist
- [ ] **P2** Тест двойного `NEW_DEAL` — дубль не создаётся
- [ ] **P2** Тест безопасности: запрос без API-Key → 403
- [ ] **P2** Нагрузочный тест: 10 заказов одновременно

---

## 🎯 Архитектурные рекомендации

### 1. State Machine для заказа

Сейчас статусы — строки в Enum. Лучше сделать явную машину состояний:

```
NEW → DIALOG → WAITING_TRADE → DELIVERING → COMPLETED
                ↓                    ↓
            CANCELLED             FAILED → RETRY (max 3)
```

- Переходы только через явные методы
- Нельзя перейти из COMPLETED в WAITING_TRADE
- При FAILED — автоматический retry (Engine пробует ещё 2 раза)

### 2. Event Sourcing (опционально)

Для аудита и отладки — логировать все события:
```python
class OrderEvent(Base):
    __tablename__ = "order_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    event_type: Mapped[str]  # "deal_created", "friend_request_sent", "trade_accepted", ...
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime]
```

### 3. Circuit Breaker для Roblox API

Если Roblox API вернул 5xx 3 раза подряд — перестать слать запросы на 60 секунд:
```python
from circuitbreaker import circuit

@circuit(failure_threshold=3, recovery_timeout=60)
async def request_friendship(user_id: int) -> bool:
    ...
```

### 4. Graceful Shutdown

```python
# backend/app/main.py
@app.on_event("shutdown")
async def shutdown():
    # Закрыть все WS-соединения
    for bot_id, ws in connections.items():
        await ws.close(code=1001, reason="Server shutdown")
    # Завершить все pending trades как "cancelled" (или оставить — они восстановятся)
```

---

## ❓ Открытые вопросы

1. **FunPay API для возврата** — доступен ли автоматический refund через funpay-universal? Если нет — `!отмена` требует ручного возврата.
2. **Множественные предметы** — `items: list[str]` поддерживается, но в `trade_flow.py` `_search_single_item()` кликает по одной координате. Если предметов >1 и они не влезают в список — нужен скролл.
3. **Перевод инвентаря** — `item_key` (например, `batwing_single`) мапится на `name` ("Batwing"). Где хранится это соответствие? Сейчас — вручную через `/stock`?
4. **Обновление инвентаря** — после трейда backend уменьшает count. Но если Engine упал до отправки `trade_completed` — count не обновится. Нужен idempotent update ( Engine шлёт `items_delivered: [{item_key, qty}]`).
5. **Параллельные трейды** — Engine может обрабатывать только 1 трейд за раз. Если 2 покупателя кинут одновременно — второй проигнорируется. Нужна очередь?

---

## 📎 Полезные сниппеты

### Проверка API-Key в Plugin
```python
# plugin/core/backend_client.py
async def _get_session(self) -> aiohttp.ClientSession:
    if self._session is None or self._session.closed:
        headers = {"X-API-Key": settings.api_key}
        self._session = aiohttp.ClientSession(headers=headers)
    return self._session
```

### Retry с exponential backoff
```python
import asyncio
from functools import wraps

def retry(max_retries=3, delay=1.0):
    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return await fn(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    wait = delay * (2 ** attempt)
                    logger.warning(f"Retry {attempt+1}/{max_retries} after {wait}s: {e}")
                    await asyncio.sleep(wait)
        return wrapper
    return decorator

@retry(max_retries=3, delay=1.0)
async def create_order(...):
    ...
```

### Fuzzy match для ников
```python
import difflib

def fuzzy_match(a: str, b: str, threshold: float = 0.8) -> bool:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() >= threshold
```

---

> **Заключение:** Featly v2.2 — хороший MVP с правильной архитектурой. Основные риски: безопасность (cookie, API), race conditions в trade flow, и незавершённые команды чата. Закрыть 5 критических пунктов — и можно запускать на тестовых сделках. Закрыть 12 — и можно в прод.
