# HANDOFF – IntelBot

> Читать в начале каждой сессии. Обновлять в конце.

---

## Статус проекта

**Фаза:** Парсеры и планировщик готовы → следующий модуль: processors (Этап 2 — RAG + LLM)
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
  - `on_items` callback (пока None, подключить в Этапе 2)
  - `reload_client()` — динамическое обновление задач без перезапуска
- [x] Дорожная карта — `docs/roadmap.md`

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

**Этап 2 — processors/ (RAG + LLM):**

1. `database/crud.py` — CRUD-операции (save_news, get_by_hash, mark_sent, save_feedback)
2. `processors/embeddings.py` — генерация эмбеддингов (sentence-transformers, asyncio.to_thread)
3. `processors/vector_store.py` — ChromaDB: add, query, коллекции `client_{client_id}`
4. `processors/deduplicator.py` — hash-check (SHA-256) + TF-IDF cosine similarity
5. `processors/rag.py` — поиск k ближайших + формирование few-shot контекста
6. `processors/llm.py` — вызов Ollama, промпт, парсинг ответа (summary/sentiment/hashtags)
7. Подключить pipeline в `scheduler.py` → `on_items`

---

## Открытые вопросы

Нет открытых вопросов.

---

## Как обновлять этот файл

1. Выполненные пункты → перенести в "Что сделано"
2. "Следующий шаг" — конкретно, не абстрактно
3. Закрытые вопросы — убрать, новые — добавить
4. Обновить дату
