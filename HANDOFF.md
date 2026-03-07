# HANDOFF – IntelBot

> Читать в начале каждой сессии. Обновлять в конце.

---

## Статус проекта

**Фаза:** Этап 5 — интеграционный тест и доработки
**Последнее обновление:** 2026-03-07

---

## Что сделано

- [x] Концепция, бизнес-модель, архитектура — закрыты
- [x] `CLAUDE.md` — точка входа для ассистента
- [x] Скелет проекта:
  - Структура папок (`bot/handlers/`, `parsers/`, `processors/`, `database/`, `configs/`, `data/`)
  - `requirements.txt` и `.env.example`
  - `configs/client_config_schema.py` — Pydantic-схема конфига клиента
  - `database/models.py` — SQLAlchemy модели (Client, Source, News, Settings, Feedback)
  - `database/db.py` — async подключение, сессии, создание таблиц
  - `config.py` — AppSettings (pydantic-settings) + `load_client_configs()`
  - `main.py` — точка входа, логирование, инициализация БД, запуск scheduler
- [x] Документация в `docs/`:
  - `stack.md`, `structure.md`, `data-model.md`, `client-config.md`
  - `rag-pipeline.md`, `setup.md`, `backlog.md`, `roadmap.md`
- [x] **Парсеры** (`parsers/`):
  - `base.py` — абстрактный BaseParser + dataclass ParsedItem
  - `rss.py` — RSS/Atom через feedparser, asyncio.to_thread, retry (tenacity)
  - `telegram.py` — Telethon, публичные каналы, сессии per-канал
  - `website.py` — aiohttp + BS4, CSS-селекторы из SelectorConfig, index + статьи
  - `social.py` — заглушка
- [x] **`scheduler.py`** — APScheduler AsyncIOScheduler:
  - Задачи per-source, IntervalTrigger, max_instances=1
  - `on_items` callback подключён к pipeline
  - `reload_client()` — динамическое обновление задач без перезапуска
- [x] Дорожная карта — `docs/roadmap.md`
- [x] **Этап 2 — processors/ (RAG + LLM pipeline):**
  - `database/crud.py` — CRUD (save_news, get_by_hash, mark_sent, save_feedback, get_or_create_client, get_or_create_source)
  - `processors/embeddings.py` — sentence-transformers, asyncio.to_thread, ленивая загрузка модели
  - `processors/deduplicator.py` — hash-check SHA-256 (SQL) + cosine similarity (ChromaDB, порог 0.92)
  - `processors/vector_store.py` — ChromaDB PersistentClient, коллекции `client_{client_id}`, cosine space
  - `processors/rag.py` — поиск top-k + формирование few-shot текстового контекста
  - `processors/llm.py` — Ollama HTTP API, промпт, JSON-парсинг (summary/sentiment/hashtags), fallback
  - `processors/pipeline.py` — оркестратор, `make_on_items_callback()` для scheduler
  - `main.py` — обновлён: `build_pipelines()`, pipeline подключён к scheduler
- [x] **Этап 3 — bot/ (Telegram-бот, handlers, доставка новостей):**
  - `bot/bot.py` — `create_bot()` + `create_dispatcher()`, регистрация роутеров
  - `bot/handlers/start.py` — `/start`: приветствие, `get_or_create_client`, создание Settings по умолчанию
  - `bot/handlers/settings.py` — `/settings`: FSM-диалог, управление keywords, frequency, digest_mode
  - `bot/handlers/feedback.py` — инлайн-кнопки `fb:<reaction>:<news_id>`, `save_feedback`
  - `bot/sender.py` — `NewsSender.send_news()`, `send_digest()` (compact/full режимы)
  - `processors/pipeline.py` — keyword-фильтр + instant/hourly/daily ветвление
  - `main.py` — полностью обновлён: два планировщика (парсинг + дайджест)
- [x] **Этап 4 — тестирование и деплой:**
  - `database/models.py` — добавлены поля `News.keyword_filtered`, `Settings.digest_mode`
  - `database/crud.py` — добавлены `get_client_settings()`, `get_unsent_news()`
  - `migrate.py` — скрипт миграции для существующих БД
  - `data/clients/test_client/config.json` — тестовый конфиг (RSS Lenta.ru)
  - `tests/conftest.py`, `test_crud.py`, `test_config_schema.py`, `test_keyword_filter.py`
  - `pytest.ini` — asyncio_mode=auto
  - `Dockerfile`, `docker-compose.yml`, `.dockerignore`

---

## Закрытые архитектурные решения

| Вопрос | Решение |
|---|---|
| JSONL vs SQLAlchemy | SQLite + SQLAlchemy для метаданных; JSONL только для архива сырых данных |
| ChromaDB vs FAISS | ChromaDB — персистентность из коробки, не нужен отдельный сервер |
| Эмбеддинги | `paraphrase-multilingual-MiniLM-L12-v2` — мультиязычная, для русского текста |
| Конфиги клиентов | Схема в `configs/client_config_schema.py`, рабочий конфиг в `data/clients/<id>/config.json` |
| handlers.py | Разбит на `handlers/` — отдельный файл на каждую команду |
| Логирование | Loguru |
| Валидация конфигов | Pydantic v2 |
| Планировщик | APScheduler AsyncIOScheduler, задача per-source, max_instances=1 |
| Доставка новостей | `NewsSender.send_news()` — instant; `send_digest()` — hourly/daily |
| Keyword-фильтрация | Сохранять в БД + ChromaDB, не отправлять (news.keyword_filtered=True) |
| Формат дайджеста | `Settings.digest_mode`: compact (один список) / full (по одному с паузой 2с) |
| Feedback | Callback-данные формата `fb:<reaction>:<news_id>`, сохранение в таблицу `feedback` |
| Docker | `docker-compose up --build`; ollama как отдельный сервис |

---

## Следующий шаг

**Этап 5 — интеграционный тест:**

1. Заполнить `.env` реальными токенами и запустить `python main.py`
2. Убедиться что `/start` создаёт клиента и Settings в БД
3. Запустить `pytest -v` — все unit-тесты должны пройти
4. При наличии существующей БД запустить `python migrate.py` перед стартом
5. Проверить отправку дайджеста вручную (вызвать `sender.send_digest(client_id, chat_id)`)
6. При необходимости вынести `OLLAMA_URL` и таймаут модели в `.env`

---

## Открытые вопросы

- Нужен ли rate-limit guard в `_send_full_digest` (сейчас пауза 2с между сообщениями)?
- Стоит ли хранить историю дайджестов в отдельной таблице для аналитики?

---

## Как обновлять этот файл

1. Выполненные пункты → перенести в "Что сделано"
2. "Следующий шаг" — конкретно, не абстрактно
3. Закрытые вопросы — убрать, новые — добавить
4. Обновить дату
