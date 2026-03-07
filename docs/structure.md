# Структура проекта

```
project/
├── main.py                     # Точка входа: запуск бота и планировщика
├── scheduler.py                # Задачи по расписанию (парсинг, дайджесты)
├── config.py                   # Базовые настройки (токен бота, пути и т.д.)
├── .env                        # Переменные окружения (токены, секреты) — не в git
├── .env.example                # Шаблон .env для новых разработчиков
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
│
├── bot/                        # Telegram-бот (aiogram)
│   ├── handlers/               # Обработчики команд — один файл на команду
│   │   ├── start.py            # /start
│   │   ├── settings.py         # /settings
│   │   ├── sources.py          # /sources
│   │   ├── last.py             # /last
│   │   └── feedback.py         # Inline-кнопки "интересно / неинтересно"
│   ├── keyboards.py            # Inline и reply клавиатуры
│   └── middlewares.py          # Логирование запросов, авторизация
│
├── parsers/                    # Сбор данных
│   ├── base.py                 # Базовый класс парсера
│   ├── rss.py                  # RSS (feedparser)
│   ├── telegram.py             # Telegram-каналы (Telethon)
│   ├── website.py              # Сайты (aiohttp + BS4)
│   └── social.py               # Задел: парсеры соцсетей
│
├── processors/                 # Анализ и обработка
│   ├── embeddings.py           # Генерация эмбеддингов (SentenceTransformer)
│   ├── vector_store.py         # ChromaDB: добавление и поиск (коллекция per client)
│   ├── rag.py                  # RAG-пайплайн: поиск похожих + формирование промпта
│   ├── llm.py                  # Ollama API: саммари, тональность, теги
│   ├── ner.py                  # Опционально: NER через slovnet
│   └── deduplicator.py         # TF-IDF + cosine similarity
│
├── database/                   # SQLite + SQLAlchemy
│   ├── models.py               # Модели: Client, Source, News, Settings, Feedback
│   ├── crud.py                 # CRUD-операции для каждой модели
│   └── db.py                   # Подключение, сессии
│
├── configs/                    # Шаблоны конфигураций (только схемы — не рабочие конфиги)
│   └── client_config_schema.py # Pydantic-модель ClientConfig (источник истины для структуры)
│
├── data/                       # Данные клиентов — монтируется в Docker, не в git
│   ├── global.db               # SQLite: метаданные всех клиентов
│   ├── logs/                   # Loguru-логи с ротацией
│   └── clients/
│       └── client_<id>/
│           ├── chroma/         # Векторная БД ChromaDB для этого клиента
│           ├── raw/            # Архив сырых новостей (JSONL по датам)
│           └── config.json     # Рабочий конфиг клиента (валидируется через ClientConfig)
│
└── tests/
    ├── test_parsers.py
    ├── test_rag.py
    └── ...
```

## Разграничение конфигов

| Папка | Назначение |
|---|---|
| `configs/client_config_schema.py` | Pydantic-схема — источник истины для структуры конфига. Не содержит данных клиентов. |
| `data/clients/<id>/config.json` | Рабочий конфиг конкретного клиента. Загружается при старте и валидируется через схему. |
