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
