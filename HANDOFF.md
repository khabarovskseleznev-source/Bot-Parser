# HANDOFF – IntelBot

> Читать в начале каждой сессии. Обновлять в конце.

---

## Статус проекта

**Фаза:** Этап 5 — завершён. Готов к деплою.
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
- [x] Документация в `docs/`
- [x] **Парсеры** (`parsers/`): rss, telegram, website, social (заглушка)
- [x] **`scheduler.py`** — APScheduler, задачи per-source, `next_run_time=now()` (запуск сразу)
- [x] **Этап 2 — processors/** (RAG + LLM pipeline):
  - embeddings, deduplicator, vector_store, rag, llm, pipeline
- [x] **Этап 3 — bot/**:
  - `bot/bot.py`, `bot/sender.py` (instant + digest compact/full)
  - `bot/handlers/`: start, settings (FSM), feedback (инлайн-кнопки)
  - pipeline: keyword-фильтр + instant/hourly/daily ветвление
  - main.py: два планировщика (парсинг + дайджест)
- [x] **Этап 4 — тестирование и деплой**:
  - `database/models.py` — `News.keyword_filtered`, `Settings.digest_mode`
  - `database/crud.py` — `get_client_settings()`, `get_unsent_news()`
  - `migrate.py`, `pytest.ini`, 22 теста (все зелёные)
  - `Dockerfile`, `docker-compose.yml`, `.dockerignore`
- [x] **Этап 5 — интеграционный тест**:
  - `.env` заполнен реальным BOT_TOKEN и chat_id (5026462041)
  - `/start` работает — клиент и Settings создаются в БД
  - RSS парсинг Lenta.ru работает (50 новостей за цикл)
  - Pipeline end-to-end: parse → embed → dedup → keyword filter → send ✅
  - 22 unit-теста — все проходят
  - SSL fix для macOS: `certifi` + `os.environ.setdefault` в `main.py`
  - Ollama не установлена на macOS 13 (Ventura) — fallback работает корректно

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
| Планировщик | APScheduler AsyncIOScheduler, задача per-source, `next_run_time=now()` |
| Доставка новостей | `NewsSender.send_news()` — instant; `send_digest()` — hourly/daily |
| Keyword-фильтрация | Сохранять в БД + ChromaDB, не отправлять (news.keyword_filtered=True) |
| Формат дайджеста | `Settings.digest_mode`: compact (один список) / full (по одному с паузой 2с) |
| Feedback | Callback-данные формата `fb:<reaction>:<news_id>`, сохранение в таблицу `feedback` |
| Docker | `docker-compose up --build`; ollama как отдельный сервис |
| SSL macOS | `certifi` + `os.environ.setdefault("SSL_CERT_FILE", certifi.where())` в `main.py` |
| ADMIN_IDS в .env | Формат JSON-массива: `[5026462041]` |

---

## Окружение

- **venv:** `.venv/` (Python 3.12)
- **Запуск:** `.venv/bin/python main.py`
- **Тесты:** `.venv/bin/python -m pytest tests/ -v`
- **macOS 13 Ventura** — Ollama через brew не ставится; нужен Ollama.app или деплой на Linux
- **BOT_TOKEN и ADMIN_IDS** — уже в `.env` (не коммитить)

---

## Следующий шаг

**Этап 6 — деплой и Ollama:**

Вариант A — **локально**:
1. Скачать Ollama.app: `curl -L https://ollama.com/download/Ollama-darwin.zip -o ~/Downloads/Ollama.zip && cd ~/Downloads && unzip Ollama.zip && open Ollama.app`
2. Скачать модель: `ollama pull saiga_llama3_8b`
3. Запустить бота и проверить саммари в сообщениях

Вариант B — **деплой на VPS (Ubuntu)**:
1. Выбрать хостинг (Timeweb Cloud, Hetzner, DigitalOcean)
2. `docker-compose up --build` — бот + ollama в контейнерах
3. Настроить `restart: always`, volumes, мониторинг логов

---

## Открытые вопросы

- Rate-limit guard в `_send_full_digest` (сейчас пауза 2с — достаточно ли?)
- Стоит ли хранить историю дайджестов в отдельной таблице для аналитики?
- Добавить источники: RBC RSS (уже в конфиге, `is_active: false`), Telegram-каналы

---

## Как обновлять этот файл

1. Выполненные пункты → перенести в "Что сделано"
2. "Следующий шаг" — конкретно, не абстрактно
3. Закрытые вопросы — убрать, новые — добавить
4. Обновить дату
