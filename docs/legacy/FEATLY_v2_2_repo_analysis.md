# 🔍 Анализ репозиториев и рекомендации по стеку Featly v2.2

> Результат анализа предложенных Gemini репозиториев + дополнительный поиск полезных библиотек.

---

## 1. Репозитории от Gemini — разбор

### 1.1 kszabi1 / Roblox-Automation-Hub

| Параметр | Оценка |
|----------|--------|
| **Ссылка** | https://github.com/kszabi1/Roblox-Automation-Hub |
| **Что внутри** | External Python-боты для Roblox. PyAutoGUI + CV. Anti-AFK. Cross-platform (Windows/macOS). |
| **Поддерживаемые игры** | Ultimate Camp Tycoon, RIVALS. MM2 — **не упоминается**. |
| **Лицензия** | ⚠️ **Запрещает коммерческое использование** без письменного разрешения. |
| **Полезность для Featly** | **Низкая / Средняя** |

**Вывод:** Можно изучить подход к CV и структуру anti-AFK, но **код копировать нельзя** из-за лицензии. Для MM2 шаблоны всё равно придётся делать свои.

---

### 1.2 iiPythonx / RoBot

| Параметр | Оценка |
|----------|--------|
| **Ссылка** | https://github.com/iiPythonx/RoBot |
| **Что внутри** | `api/windows.py` — `WindowManager` с `focusROBLOX()`, `leaveGame()`, `resetChar()`, `Chat()`. Использует `pygetwindow`. GUI на pygame. |
| **Последнее обновление** | 2020 (устарел) |
| **Полезность для Featly** | **Средняя** |

**Что забрать:**
- Концепт `WindowManager` — фокус окна Roblox перед действиями
- `leaveGame()` / `resetChar()` — можно адаптировать под ESC → Leave

**Что НЕ забрать:**
- `pygetwindow` — устарел, есть лучше альтернативы (см. PyWinCtl ниже)
- GUI на pygame — не нужен, у нас funpay-universal для управления

---

### 1.3 matas38 / roblox-vip-server-joiner

| Параметр | Оценка |
|----------|--------|
| **Ссылка** | Не найден напрямую, есть аналог: https://github.com/berkay-digital/roblox-private-server-joiner |
| **Что внутри** | Deep link `roblox://placeId=...&linkCode=...` для захода на приватный сервер. Мониторинг дисконнектов. |
| **Полезность для Featly** | **Низкая** |

**Вывод:** VIP-ротация убрана в v2.2. Статическая ссылка на сервер MM2 достаточна. Deep link может быть полезен только для **первичного захода** бота на сервер при старте, но это делается один раз вручную.

---

### 1.4 robotjs (JSAutoGUI)

| Параметр | Оценка |
|----------|--------|
| **Ссылка** | https://github.com/hurdlegroup/robotjs |
| **Что внутри** | Node.js desktop automation на C++. Мышь, клавиатура, скриншоты, pixel color. |
| **Полезность для Featly** | **Низкая** |

**Вывод:** Windows Engine планируется на Python (OpenCV + PyAutoGUI). Переписывать на Node.js нет смысла — PyAutoGUI стабильнее для CV-задач. Если бы бэкенд и кликер были на одном языке — имело бы смысл. Но у нас разделение: Python на ноутбуке, Node.js/Python на VPS.

---

## 2. Найденные альтернативы — must have

### 2.1 PyDirectInput / pydirectinput-rgx ⭐ CRITICAL

| Параметр | Оценка |
|----------|--------|
| **Оригинал** | https://github.com/learncodebygaming/pydirectinput |
| **Форк (рекомендуется)** | https://github.com/ReggX/pydirectinput_rgx или https://github.com/Adamcf123/pydirectinput_rgx |
| **PyPI** | `pip install pydirectinput-rgx` |

**Почему это важно:**

PyAutoGUI использует устаревшие Windows API: `mouse_event()` и `keybd_event()` + Virtual Key Codes. **Roblox (DirectX-игра) может игнорировать эти события** — клики и нажатия просто не срабатывают.

PyDirectInput использует:
- `SendInput()` — современный Windows API
- **Scan Codes** вместо Virtual Key Codes
- DirectInput-совместимость

**Это значит:** клики по кнопкам трейда, ввод текста в поиск, нажатия Accept — будут работать гарантированно.

**API полностью совместим с PyAutoGUI:**
```python
import pydirectinput as pdi

pdi.click(100, 200)
pdi.typewrite("batwing", interval=0.01)
pdi.press("esc")
pdi.keyDown("shift")
pdi.keyUp("shift")
```

**Дополнительно в форке rgx:**
- `unicode_typewrite()` — для любых символов
- `scancode_press()` — low-level контроль
- `hold()` context manager — удобные хоткеи
- Поддержка multi-monitor
- Отключение mouse acceleration для точности

**Рекомендация:** Заменить `pyautogui` на `pydirectinput-rgx` во всём Windows Engine. Оставить PyAutoGUI только для `pyautogui.position()` (калибровка координат) и `pyautogui.screenshot()` (если не используем mss).

---

### 2.2 MSS (Multi-ScreenShot) ⭐ HIGHLY RECOMMENDED

| Параметр | Оценка |
|----------|--------|
| **Ссылка** | https://github.com/BoboTiG/python-mss |
| **PyPI** | `pip install mss` |
| **Документация** | https://python-mss.readthedocs.io/ |

**Почему это важно:**

`pyautogui.screenshot()` медленный (делает скрин через PIL → WinAPI). При CV-сканировании каждые 2 секунды это не критично, но:
- **mss в 3-5 раз быстрее** (30-60 FPS vs 10-15 FPS у pyautogui)
- Работает через **ctypes** напрямую, без промежуточных слоёв
- Нативно возвращает **NumPy array** — сразу в OpenCV без конвертаций
- Поддержка **multi-monitor** из коробки

**Использование с OpenCV:**
```python
import mss
import numpy as np
import cv2

with mss.mss() as sct:
    # Захват всего монитора
    screenshot = sct.grab(sct.monitors[1])
    # Конвертация в OpenCV формат (BGRA → BGR)
    img = np.array(screenshot)
    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    # Или сразу grayscale для matchTemplate
    gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
```

**Рекомендация:** Заменить `pyautogui.screenshot()` на `mss` в `ScreenCapture` классе. PyAutoGUI оставить только для калибровки координат (`pyautogui.position()`).

---

### 2.3 PyWinCtl ⭐ RECOMMENDED

| Параметр | Оценка |
|----------|--------|
| **Ссылка** | https://github.com/Kalmat/PyWinCtl |
| **PyPI** | `pip install pywinctl` |

**Почему это важно:**

Вместо устаревшего `pygetwindow` (из RoBot) — современная кроссплатформенная библиотека:

- `getWindowsWithTitle("Roblox")` — найти окно
- `win.activate()` — фокус (bring to front)
- `win.moveTo(0, 0)` + `win.resizeTo(1280, 720)` — фиксировать позицию
- `win.alwaysOnTop(True)` — закрепить поверх всех окон
- `win.watchdog` — мониторинг состояния окна (закрылось? свернулось?)

**Для Featly критично:**
```python
import pywinctl as pwc

# Найти и зафиксировать окно Roblox
wins = pwc.getWindowsWithTitle("Roblox", condition=pwc.Re.CONTAINS)
if wins:
    roblox = wins[0]
    roblox.activate()
    roblox.moveTo(0, 0)
    roblox.resizeTo(1280, 720)
    roblox.alwaysOnTop(True)

    # Мониторинг: если окно закрылось — алерт
    def on_closed(is_alive):
        if not is_alive:
            send_alert("Roblox окно закрылось!")

    roblox.watchdog.start(isAliveCB=on_closed)
```

**Рекомендация:** Использовать вместо `pygetwindow` из RoBot. Добавить в Windows Engine: автофокус окна перед каждым действием + watchdog на случай закрытия.

---

## 3. Обновлённый стек Windows Engine

| Компонент | Было | Стало | Почему |
|-----------|------|-------|--------|
| Клики / клавиатура | PyAutoGUI | **pydirectinput-rgx** | DirectX-совместимость, Scan Codes |
| Скриншоты | PyAutoGUI screenshot | **mss** | 3-5x быстрее, нативный NumPy |
| Управление окном | pygetwindow (RoBot) | **PyWinCtl** | Современный, watchdog, alwaysOnTop |
| CV | OpenCV | **OpenCV** | Остаётся |
| OCR | pytesseract | **pytesseract** | Остаётся |
| WS клиент | websockets | **websockets** | Остаётся |

### Обновлённый requirements.txt для Windows Engine

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

## 4. Что из репозиториев Gemini реально полезно

| Репозиторий | Что забрать | Что игнорировать |
|-------------|-------------|------------------|
| **Roblox-Automation-Hub** | Подход к организации CV-модулей, структура anti-AFK | Код (лицензия), шаблоны под другие игры |
| **RoBot** | Концепт `WindowManager`, `leaveGame()` | `pygetwindow` (устарел), GUI на pygame, код 2020 года |
| **roblox-vip-server-joiner** | Deep link формат `roblox://` | Весь функционал (VIP-ротация не нужна) |
| **robotjs** | Ничего | Весь репозиторий (не наш стек) |

---

## 5. Дополнительные находки (не от Gemini)

### 5.1 nwsynx / roblox-tools

| Параметр | Оценка |
|----------|--------|
| **Ссылка** | https://github.com/nwsynx/roblox-tools |
| **Что внутри** | Anti-AFK, Proximity Prompt Spam, Auto Clicker. GUI на dearpygui. Использует `pydirectinput`. |
| **Полезность** | **Средняя** |

**Что забрать:** Реализацию anti-AFK с `pydirectinput` (spin camera, move, jump, emotes). Но делать свой GUI не нужен — управление через funpay-universal TG.

### 5.2 RbxAPI / Pyblox

| Параметр | Оценка |
|----------|--------|
| **Ссылка** | https://github.com/RbxAPI/Pyblox |
| **Что внутри** | Python API wrapper для Roblox. Cookie-аутентификация. Users, Groups, Assets. |
| **Полезность** | **Низкая** |

**Вывод:** Библиотека 2018 года, маркирована как "incredibly unstable". Для нашей задачи (только `request-friendship` + `validate_username`) проще `aiohttp` напрямую. Не добавлять зависимость.

### 5.3 ro.py (roblox)

| Параметр | Оценка |
|----------|--------|
| **Ссылка** | https://github.com/ro-py/ro.py |
| **PyPI** | `pip install roblox` |
| **Что внутри** | Асинхронный OOP wrapper для Roblox API. |
| **Полезность** | **Средняя** |

**Вывод:** Современный, асинхронный. Но v2.0 в разработке, текущая версия на PyPI устарела. Если нужен полноценный Roblox API-клиент — можно рассмотреть. Для Featly (2 endpoint'а) — избыточно.

---

## 6. Итоговая рекомендация по стеку

### Плагин (funpay-universal)

```
funpay-universal (core)
├── Featly Plugin
│   ├── aiohttp          # Roblox API + Backend REST
│   ├── pydantic         # Валидация данных
│   └── (funpay-universal уже включает aiogram 3)
```

### Бэкенд (VPS)

**Вариант A — Node.js (как в ТЗ):**
```
Node.js + Express      # REST API
ws                     # WebSocket сервер
pg                     # PostgreSQL
TypeScript + Zod       # Типизация + валидация
```

**Вариант B — Python (единый стек):**
```
FastAPI                # REST API + auto-docs
websockets             # WS сервер
asyncpg                # Асинхронный PostgreSQL
SQLAlchemy 2.0 + Alembic  # ORM + миграции
```

**Рекомендация:** Если хочешь единый стек на VPS — бери **FastAPI (Вариант B)**. Плагин и бэкенд на Python, проще поддерживать одному человеку. Node.js имеет смысл только если в команде есть Node-разработчик.

### Windows Engine (ноутбук)

```
pydirectinput-rgx   # Клики / клавиатура (DirectX ✅)
mss                 # Скриншоты (быстрые ✅)
PyWinCtl            # Управление окном Roblox ✅
OpenCV              # Template matching ✅
pytesseract         # OCR ✅
websockets          # Связь с бэкендом ✅
pyyaml              # Конфиги ✅
```

---

## 7. Чек-лист: что установить перед кодингом

### VPS (Ubuntu 24)

```bash
# Python 3.12
sudo apt install python3.12 python3.12-venv python3.12-dev

# PostgreSQL
sudo apt install postgresql postgresql-contrib

# Node.js (если выбран вариант A)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Tesseract (если OCR на VPS — обычно нет)
sudo apt install tesseract-ocr tesseract-ocr-eng
```

### Ноутбук (Windows)

```bash
# Python 3.12 с python.org (Add to PATH!)

# Создать venv
python -m venv featly_env
featly_env\Scripts\activate

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

> **Резюме:** Из репозиториев Gemini реально полезен только концепт `WindowManager` из RoBot (но с заменой на PyWinCtl). Главные находки — **pydirectinput-rgx** и **mss**, которые критически улучшают надёжность Windows Engine. Всё остальное либо устарело, либо под другие игры, либо не наш стек.
