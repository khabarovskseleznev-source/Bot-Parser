# Технологический стек

| Компонент | Технология |
|---|---|
| Язык | Python 3.10+ |
| Telegram Bot | aiogram 3.x |
| Парсинг Telegram | Telethon (публичные каналы) |
| Парсинг RSS | feedparser |
| Парсинг веб-сайтов | aiohttp + BeautifulSoup4 |
| Векторное хранилище | ChromaDB (персистентное, локальное) |
| Эмбеддинги | sentence-transformers `paraphrase-multilingual-MiniLM-L12-v2` |
| LLM | Ollama → `Saiga Llama 3 8B` (русскоязычная) |
| База данных | SQLite + SQLAlchemy (метаданные, клиенты, новости) |
| Валидация конфигов | Pydantic v2 |
| Планировщик | APScheduler |
| Логирование | Loguru (ротация файлов, цветной вывод) |
| Дедупликация | sklearn TfidfVectorizer + cosine similarity |
| Тесты | pytest |
| Деплой | Docker + docker-compose |

## Примечания

- **ChromaDB vs FAISS:** выбран ChromaDB — не требует отдельного сервера, персистентность из коробки.
- **SQLite vs JSONL:** SQLite используется для метаданных (клиенты, источники, новости, фидбек). JSONL — только для архива сырых новостей (`data/clients/<id>/raw/`).
- **Эмбеддинги:** мультиязычная модель выбрана намеренно — контент клиентов преимущественно на русском.
- **asyncio.to_thread:** для блокирующих вызовов (ChromaDB, SentenceTransformer) используется `asyncio.to_thread`.
