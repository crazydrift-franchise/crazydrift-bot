# CrazyDrift Backend

FastAPI + aiogram + PostgreSQL + Redis + Claude AI

## Структура

```
app/
  main.py              # FastAPI app + webhook setup
  config.py            # Settings from .env
  database.py          # SQLAlchemy async engine
  models/              # DB models (Lead, User, FAQ, etc.)
  repositories/        # DB queries
  services/ai/         # Claude API service
  bot/
    handlers/          # Telegram message handlers
    keyboards/         # Bot keyboard layouts
    states/            # FSM states for lead form
  api/routes/          # REST API endpoints
  tasks/               # APScheduler jobs
migrations/            # Alembic migrations
scripts/               # seed.py — initial data
docker/                # nginx.conf
```

## Деплой на сервере (после SSL)

### 1. Создать .env
```bash
cp .env.example .env
nano .env
# Заполнить все значения
```

### 2. Запустить
```bash
docker compose up -d --build
```

### 3. Применить миграции и seed
```bash
docker compose exec backend alembic upgrade head
docker compose exec backend python -m scripts.seed
```

### 4. Проверить
```bash
docker compose logs -f backend
curl http://localhost:8000/health
```

## API endpoints

| Method | URL | Описание |
|--------|-----|----------|
| POST | /api/auth/login | Авторизация |
| GET | /api/leads/ | Список лидов |
| GET | /api/leads/{id} | Карточка лида |
| POST | /api/leads/{id}/analyze | AI-анализ лида |
| GET | /api/leads/{id}/events | Логи лида |
| GET | /api/faq/categories | FAQ категории |
| GET | /api/faq/items | FAQ вопросы |
| GET | /api/knowledge/ | База знаний |
| GET | /api/touches/ | Касания |
| GET | /api/gpt/ | GPT настройки |
| POST | /api/gpt/test | Тест промпта |
| GET | /api/analytics/stats | Статистика |
| GET | /api/analytics/daily | По дням |
| POST | /api/analytics/weekly-report | AI отчёт |
| POST | /webhook/telegram | Telegram webhook |

## Переменные окружения

См. `.env.example`

## Как подключить к фронтенду

В `chatbotfr-deploy/.env` добавить:
```
VITE_API_URL=https://panel-crazyfr.ru/api
```

В `services/claude.ts` заменить прямые вызовы Anthropic API
на вызовы `VITE_API_URL` — тогда ключ не будет виден в браузере.
