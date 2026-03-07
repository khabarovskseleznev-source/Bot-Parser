# Модель данных (SQLAlchemy)

База данных: SQLite (`data/global.db`)

## Client

| Поле | Тип | Описание |
|---|---|---|
| `id` | int PK | |
| `name` | str | Название компании |
| `telegram_chat_id` | int | Куда отправлять уведомления |
| `is_active` | bool | |
| `config_path` | str | Путь к `data/clients/<id>/config.json` |
| `created_at` | datetime | |
| `updated_at` | datetime | |

## Source

| Поле | Тип | Описание |
|---|---|---|
| `id` | int PK | |
| `client_id` | int FK | |
| `type` | str | `telegram` / `rss` / `website` / `social` |
| `url` | str | Ссылка или идентификатор |
| `name` | str | Название источника (для отображения) |
| `is_active` | bool | |
| `last_fetch` | datetime | Время последнего успешного парсинга |
| `fetch_interval` | int | Периодичность опроса (минуты) |
| `selector_config` | JSON | Для сайтов: CSS-селекторы (title, content, date) |

## News

| Поле | Тип | Описание |
|---|---|---|
| `id` | int PK | |
| `client_id` | int FK | |
| `source_id` | int FK | |
| `url` | str | Ссылка на оригинал (уникальна в рамках клиента) |
| `title` | str | |
| `content` | text | |
| `published_at` | datetime | |
| `summary` | text | Сгенерированное саммари (nullable) |
| `sentiment` | str | `positive` / `neutral` / `negative` (nullable) |
| `entities` | JSON | Выделенные сущности NER (nullable) |
| `hashtags` | JSON | Массив тегов (nullable) |
| `hash` | str | Хэш контента для быстрой дедупликации |
| `is_duplicate` | bool | Помечено ли как дубликат |
| `sent_to_user` | bool | Отправлено ли пользователю |
| `created_at` | datetime | |

## Settings

| Поле | Тип | Описание |
|---|---|---|
| `client_id` | int PK/FK | |
| `keywords` | JSON | Список ключевых слов |
| `exclude_keywords` | JSON | Стоп-слова |
| `frequency` | str | `instant` / `hourly` / `daily` |
| `analysis_flags` | JSON | Какие виды анализа включены |

## Feedback

| Поле | Тип | Описание |
|---|---|---|
| `id` | int PK | |
| `client_id` | int FK | |
| `news_id` | int FK | |
| `reaction` | str | `like` / `dislike` / `saved` |
| `created_at` | datetime | |

> Фидбек используется для персонализации: дизлайки влияют на будущую фильтрацию новостей клиента.
