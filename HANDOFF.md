# HANDOFF – IntelBot

> Читать в начале каждой сессии. Обновлять в конце.

---

## Статус проекта

**Фаза:** Этап 3 — bot/ (Telegram-бот, handlers, доставка новостей)
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

---

## Следующий шаг

**Этап 3 — bot/ (Telegram-бот, handlers, доставка новостей):**

1. `bot/bot.py` — инициализация aiogram 3.x Bot + Dispatcher, регистрация роутеров
2. `bot/handlers/start.py` — `/start`, приветствие, регистрация клиента
3. `bot/handlers/settings.py` — `/settings`, управление ключевыми словами и частотой доставки
4. `bot/handlers/feedback.py` — обработка инлайн-кнопок (like/dislike/saved) через `save_feedback`
5. `bot/sender.py` — форматирование и отправка новостей (`mark_sent` после отправки)
6. Интеграция sender с pipeline: вызов `sender.send_news()` в конце `pipeline._process_item()`
7. Подключение бота к `main.py`: `asyncio.gather(bot.run(), scheduler_event_wait)`

---

## Открытые вопросы

Нет открытых вопросов.

---

## Как обновлять этот файл

1. Выполненные пункты → перенести в "Что сделано"
2. "Следующий шаг" — конкретно, не абстрактно
3. Закрытые вопросы — убрать, новые — добавить
4. Обновить дату
