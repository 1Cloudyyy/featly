# FEATLY v3.1 — Полное руководство по запуску

> Актуально на 2026-08-16 (master, changelog 9.1.0).
> Покрывает: VDS (hub + funpay-universal + плагин), Windows-машину выдачи (движок),
> и «уборку» остатков прежней v2 на сервере.

---

## 0. Схема развёртывания

```
VDS (Linux)                                Windows / Mini-ПК
┌─────────────────────────────┐            ┌──────────────────────┐
│ funpay-universal 1.17       │            │ Engine (python)      │
│  └─ модуль featly (плагин)  │◄──REST────►│  Roblox + MM2        │
│ hub (FastAPI + SQLite)      │◄──WS──────►│  OpenCV, OCR, клики  │
│  └─ port 8000               │            └──────────────────────┘
│ Telegram-бот (панель /admin)│
└─────────────────────────────┘
```

- Всё на VDS: **hub + плагин + Telegram-бот** (один процесс funpay-universal + один процесс hub).
- Движок — на отдельной машине (Windows), подключается к hub по WebSocket.

---

## 1. Остатки v2 на VDS — сначала ЗАЧИСТКА ⚠️

Сейчас на VDS крутятся процессы старой версии (тесты v2). Их нужно остановить и
удалить, иначе новый hub не поднимется (порт 8000 занят) и старый плагин будет
конфликтовать в funpay-universal.

### 1.1 Найти, что крутится
```bash
# systemd-юниты старого backend'а
systemctl list-units | grep -i featly
systemctl status featly-backend --no-pager

# Docker (старые контейнеры backend/admin/postgres)
docker ps -a

# Что слушает порт 8000
ss -ltnp | grep 8000

# Старые папки
ls -la /opt/featly/
```

### 1.2 Остановить и удалить (команды примерные — подставь свои имена)
```bash
systemctl stop featly-backend && systemctl disable featly-backend   # если юнит v2
rm -f /etc/systemd/system/featly-backend.service && systemctl daemon-reload

# Docker-вариант (если был):
cd /opt/featly && docker compose down
docker rm -f featly-backend featly-admin 2>/dev/null

# Старая папка v2 (после проверки — можно удалить, БД v2 не переносим)
mv /opt/featly/backend /opt/featly/backend_v2_backup
mv /opt/featly/admin  /opt/featly/admin_v2_backup
```
> Решение принято: **данные v2 (старые заказы, инвентарь) не переносим** — система
> стартует с чистой базой (SQLite) и «нулевой» историей.

### 1.3 Очистить funpay-universal от старого плагина
В папке модулей funpay-universal:
```bash
find /opt/funpay-universal -maxdepth 3 -type d -name "featly*"  # найти старый
rm -rf <папка_старого_модуля>            # удалить старый плагин v2
rm -rf <папка_модуля>/data               # и его data/settings.json (старые настройки)
```

### 1.4 Итог проверки перед установкой
```bash
ss -ltnp | grep 8000   # пусто — порт свободен
```

---

## 2. VDS — Hub

### 2.1 Код и окружение
```bash
git clone https://github.com/1Cloudyyy/featly.git /opt/featly   # или git pull в существующем
cd /opt/featly/hub
python3.12 -m venv venv            # (или python3)
./venv/bin/pip install -r requirements.txt
```
Зависимости hub (ставит requirements): fastapi, uvicorn, sqlalchemy[asyncio],
**aiosqlite**, **aiohttp**, **cryptography**, websockets, pydantic-settings, loguru.

### 2.2 Первый запуск — создания секретов и БД
```bash
./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```
При первом старте hub сам:
- создаст **`featly.db`** (SQLite) и все таблицы;
- создаст корневой **`.env`** с секретами:
  `FEATLY_WS_SECRET=…`, `FEATLY_API_KEY=…`, `FEATLY_COOKIE_KEY=…`.

⚠️ **Скопируй значения из `/opt/featly/.env`** — они понадобятся для плагина и движка.
Файл `.env` в `git status` не появляется (gitignored).

### 2.3 Автозапуск (systemd)
```bash
cp /opt/featly/scripts/featly-hub.service /etc/systemd/system/
# Отредактировать: при желании задать свои WS_SECRET/API_KEY,
# пути по умолчанию уже правильные.
systemctl daemon-reload && systemctl enable --now featly-hub
systemctl status featly-hub --no-pager
journalctl -u featly-hub -f          # логи старта/ошибок
```

### 2.4 Проверка hub
```bash
curl http://localhost:8000/health                 # {"status":"ok"}
curl -H "X-API-Key: <FEATLY_API_KEY>" http://localhost:8000/stats
# Документация API: http://<vds-ip>:8000/docs
```
Если firewall — открыть порты:
```bash
ufw allow 8000/tcp
```

---

## 3. VDS — funpay-universal 1.17 + плагин featly

### 3.1 Установка бота
- Скачай и установи **последний релиз funpay-universal (1.17)** на VDS.
- В панели бота укажи **Telegram-токен** (свой бот для продаж).

### 3.2 Установка модуля featly
Подключи папку плагина из репозитория как модуль `featly` (через модули/структуру
funpay-universal). В папке модуля находятся `__init__.py`, `meta.py`, `core/`, `handlers/` и т.д.

После первого включения модуля появится файл **`plugin/data/settings.json`** (создаётся
автоматически с дефолтами; путь — внутри папки модуля).

### 3.3 Заполнить settings.json (ОБЯЗАТЕЛЬНО минимум 4 поля)
```jsonc
{
  "backend_url": "http://localhost:8000",
  "bot_id": "bot_main",
  "admin_tg_id": "<ТВОЙ Telegram ID>",
  "api_key": "<FEATLY_API_KEY из hub .env>",
  "roblox_cookie": "<.ROBLOSECURITY>",
  "static_server_link": "ссылка на VIP-сервер (если есть)",
  // остальное: по умолчанию; адативные опции — через панель /admin
}
```
- `api_key` без него панель и все запросы к hub вернут 403 → запись в лог «api_key не задан».
- `admin_tg_id` без него панель `/admin` отвечает «Нет доступа».
- `roblox_cookie` также можно задать командой `/roblox_cookie <значение>` или в панели.

### 3.4 Перезапуск и первичный вход
1. Перезапусти funpay-universal (модуль включится).
2. В логах должно быть: «Модуль Featly v3.1.0 включён», «Hub доступен».
3. Открой своего Telegram-бота → `/admin` → панель (движок 🔴, инвентарь пуст — это нормально).
4. Заполни инвентарь через «📦 Инвентарь ➕» (авто-синк лотов подключится сам при `autosync_lots`).

---

## 4. Windows / Mini-ПК — движок

### 4.1 Окружение (один раз)
```powershell
# Установить Python 3.12 (важно: добавить в PATH)
# Установить Tesseract OCR: https://github.com/UB-Mannheim/tesseract/wiki
#   (язык не требуется — используется англ. по умолчанию)

cd C:\path\to\featly\engine
python -m venv venv
venv\Scripts\pip install -r requirements.txt
```
Зависимости движка (в requirements): opencv-python, numpy, pytesseract, Pillow,
mss, pydirectinput-rgx, pywinctl, websockets, pyyaml, pydantic, loguru.
Плюс системно: Tesseract (см. выше).

### 4.2 Настройки через переменные окружения (Mini-ПК)
```powershell
setx FEATLY_WS_URL     "ws://<VDS-IP>:8000/ws/engine"
setx FEATLY_BOT_ID     "bot_main"
setx FEATLY_WS_SECRET  "<FEATLY_WS_SECRET из hub .env>"
```
> Все три — обязательно. `bot_id` ОБЯЗАН совпадать с `bot_id` в settings.json плагина.

### 4.3 Запуск
```powershell
cd C:\path\to\featly\engine
venv\Scripts\python -m engine.main
```
В консоли: «Connected to ws://…», периодически «Waitlist poll», при заказе — выдача.
Запуск под планировщиком Windows (опционально).

### 4.4 Проверка связки
1. В панели: «🤖 Движок» → 🟢 online.
2. Создай тестовый заказ (купи свой лот или добавь заказ вручную в БЧ) → диалог в чате
   FunPay → после подтверждения ника движок примет трейд и выдаст предмет.
3. Скрин-лог движка: `engine/logs/engine_YYYY-MM-DD.log`.

---

## 5. Ожидаемый «день продавца» (самопроверка)

| Что видишь | Статус |
|---|---|
| `/admin` открывается, движок 🟢 | система живая |
| Заказ → покупатель подтверждает ник → «Заходи в игру», сервер, «Кинь трейд» | диалог работает |
| Движок выдал → заказ COMPLETED в hub, склад уменьшился, лут «Наличие» обновлён | выдача работает |
| Покупатель подтверждает на FunPay → «Спасибо за покупку» | закрытие сделки |
| Движок упал > N мин → алерт в настроенный TG-чат | мониторинг работает |

---

## 6. Границы настройки (что НЕ нужно на сервере)

- Секреты задаются 1 раз в `.env` (v3 сам их генерирует и хранит).
- Движок на другую машину — через панель «🔑 Подключения» можно скопировать готовый env-блок.
- systemd/Docker/обновление кода — вручную (панель их не трогает).

---

## 7. Частые проблемы

| Симптом | Причина/решение |
|---|---|
| Плагин: «api_key не задан…» | заполнить `settings.json → api_key` (из hub `.env` `FEATLY_API_KEY`) |
| Панель: «Hub не отвечает» | `backend_url` неверный / hub не запущен / порт занят старым backend'ом |
| `/admin`: «Нет доступа» | `admin_tg_id` пуст или не твой |
| Движок: `ConnectionClosed`, вечный reconnect | неверный `FEATLY_WS_SECRET` или несовпадающий `bot_id` |
| Движок не подключается из-за сети | открыть 8000/tcp на VDS (ufw/security group) |
| Файл `.env` пропал/изменён | секреты сгенерируются новые → клиенты разъедутся; храни копию! |