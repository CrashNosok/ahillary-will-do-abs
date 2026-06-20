# ahillary-will-do-abs

Личный локальный трекер похудения и тренировок (один пользователь): еда, активность,
замеры тела, тренировки, прогресс и LLM-рекомендации. Стек: **FastAPI + SQLModel + SQLite**
(backend) и **Vite + React + TS** (frontend). Работает только локально на `localhost`.

## Структура

```
backend/    FastAPI + SQLModel + SQLite (ruff для линта/формата)
frontend/   Vite + React + TS (prettier для формата)
samples/    реальные образцы данных (FatSecret CSV, Welltory скрин)
data/        база и загруженные файлы — создаётся в рантайме, в git не попадает
docs/        процедуры и заметки (review-playbook.md)
```

> Sprint 0 — это скелет. Реальные приложения (FastAPI `/health`, Vite-страница) и их
> зависимости добавляются в следующих карточках (S0.2 — backend-приложение, S0.8 — frontend).
> Здесь зафиксированы структура, dev-тулинг и команды запуска.

## Требования

- Python ≥ 3.11
- Node.js ≥ 18 + npm

## Backend

Установка (один раз):

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # затем заполнить ключи (Anthropic, SECRET_KEY, SEED_USER_*)
```

Запуск сервиса (одна команда):

```bash
uvicorn app.main:app --reload   # доступно начиная с S0.2
```

Проверка кода (ruff):

```bash
ruff check .
ruff format --check .
```

## Frontend

Установка (один раз):

```bash
cd frontend
npm install
```

Запуск дев-сервера (одна команда):

```bash
npm run dev   # Vite-приложение появится в S0.8
```

Проверка формата (prettier):

```bash
npm run format:check   # авто-фикс: npm run format
```

## Конфигурация

Все секреты — в `backend/.env` (в git не попадает). Список ключей — в
[`backend/.env.example`](backend/.env.example). Файлы (скрины/видео) хранятся на диске
под `data/`, в БД — только пути.
