# FEATLY Plugin — Changelog

> Журнал изменений модуля funpay-universal (interface 1.17+).
> Общопроектные изменения — в корневом `changelog.md`.

## [3.1.0] — 2026-08-16

- `X-API-Key` из `settings.json → api_key` (без ключа hub отвечает 403)
- Умная автовыдача: ник из `Order.player` («Имя персонажа»), режимы `auto` / `auto_trusted` / `ask`;
  настройка `add_friends` (запрос в друзья вкл/выкл)
- Панель: экран «🚀 Автовыдача»; «🏠 Hub» (настройки hub через `/settings`); «🔑 Подключения»
  (одноразовый показ секретов + env-блок для движка); `backend_ws_url`, `alert_on_zero`,
  скрытый `api_key` в «⚙️ Настройки»
- Возврат: retry (3× backoff) только для идемпотентных GET
- Персистентные диалоги (`data/dialogs_cache.json`)
- Валидация ввода в панели (отрицательные числа, URL-схемы)
- `!смена` — реальное обновление ника в hub; `!отмена` — FSM-подтверждение

## [3.0.0] — 2026-08-16

- Миграция на интерфейс funpay-universal **1.17**:
  `BOT_EVENT_HANDLERS` / `FUNPAY_EVENT_HANDLERS` / `TELEGRAM_BOT_ROUTERS`,
  хендлеры `(bot, event)`, отправка через `bot.send_message`
- Полное логирование каждого этапа (модуль, события, диалоги, hub, Roblox, TG, кэш)
- `settings.json` создаётся при включении модуля (`ensure_settings`)
- `ensure_settings`: подсказка про `admin_tg_id` в логе при создании

## [2.2.0] — 2026-08-06 (пред. версия)

- Старый интерфейс плагина (`EVENT_HANDLERS`, `(deal, acc)`) — **не совместим с 1.17**,
  оставлен в истории для справки