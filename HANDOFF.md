# HANDOFF – IntelBot

> Читать в начале каждой сессии. Обновлять в конце.

---

## Статус проекта

**Фаза:** Этап 7 завершён (feedback-обучение). Следующая задача — деплой Этапа 7 на VPS + мониторинг.
**Последнее обновление:** 2026-03-10

---

## Что сделано

- [x] Концепция, бизнес-модель, архитектура — закрыты
- [x] `CLAUDE.md` — точка входа для ассистента
- [x] Скелет проекта (структура, модели, БД, config.py, main.py)
- [x] Документация в `docs/`
- [x] **Парсеры** (`parsers/`): rss, telegram, website, social (заглушка)
- [x] **`scheduler.py`** — APScheduler, задачи per-source
- [x] **processors/** — embeddings, deduplicator, vector_store, rag, llm, pipeline
- [x] **bot/** — handlers (start, settings FSM, feedback), sender (instant + digest)
- [x] **22 unit-теста** — все зелёные
- [x] **Dockerfile** — torch CPU-only (без CUDA), образ ~1.5GB
- [x] **importance_score (1-10)** — добавлен в LLM-промпт, модель, pipeline, дайджест (топ-20 по score)
- [x] **migrate.py** — миграция БД на VPS выполнена, колонка importance_score добавлена
- [x] **Этап 6 — деплой на VPS (Timeweb, Ubuntu, IP: 85.239.51.247)**:
- [x] **Этап 7 — Feedback-обучение:**
  - `update_importance_by_feedback` — корректировка importance_score по реакциям (like +2, saved +3, dislike -2, clamp 1-10)
  - `/stats` — топ-3 хештеги + % тональностей лайкнутых за 7 дней (`bot/handlers/stats.py`)
  - RAG-буст лайкнутых — `build_context` принимает `liked_news_ids`, поднимает их вверх (`processors/rag.py`)
  - Фильтр источников — `get_low_priority_source_ids` (≥70% дизлайков → пропуск новостей из источника)
  - Docker 29.3.0 установлен
  - Контейнер `intelbot-bot-1` запущен (`docker compose up -d`)
  - LLM: Groq API (`llama-3.1-8b-instant`), ключ в `.env`
  - `/start`, `/settings`, ключевые слова — работают (проверено на скриншоте)
  - Конфиг первого клиента создан: `data/clients/ai_news_1/config.json`
  - Конфиг загружен на VPS, бот перезапущен, парсинг работает
  - SSH-ключ установлен (fail2ban решён)
  - Swap 2 ГБ добавлен (OOM решён)

---

## VPS

- **IP:** 85.239.51.247
- **Логин:** root
- **Пароль:** uh1+FEExZdw_96
- **Путь:** `~/intelbot/`
- **Команды:**
  ```bash
  cd ~/intelbot && docker compose restart bot   # перезапуск
  docker compose logs bot -f                    # логи
  docker compose down && docker compose up -d   # полный перезапуск
  ```
- **SSH-ключ:** на Mac уже есть `~/.ssh/id_ed25519.pub` — нужно скопировать на VPS:
  ```bash
  ssh-copy-id -i ~/.ssh/id_ed25519.pub root@85.239.51.247
  ```
- **Проблема:** fail2ban блокирует SSH после нескольких быстрых подключений (~30 мин блокировка). Решение — SSH-ключ.

---

## Первый клиент: ai_news_1

- **Файл:** `data/clients/ai_news_1/config.json`
- **Ниша:** ИИ-новости и новые продукты
- **chat_id:** 5026462041
- **Источники (RSS):** TechCrunch, Ars Technica, The Verge, Habr AI, vc.ru, Computerphile YouTube, Two Minute Papers YouTube, NVIDIA Blog
- **Ключевые слова:** AI, LLM, GPT, Claude, Gemini, Llama, нейросеть, OpenAI, Anthropic...
- **Доставка:** раз в день в 09:00, формат полный, только по ключевым словам
- **Telegram-каналы:** не подключены (my.telegram.org не даёт создать API-приложение)

---

## Следующий шаг

**Этап 8 — Деплой Этапа 7 на VPS + мониторинг:**

1. **Деплой** — репозиторий сделан публичным, нужно `git clone` на VPS и пересборка (см. инструкцию выше)
2. **Мониторинг uptime** — Uptime Kuma (docker container на том же VPS)
3. **Админ-команды:** `/add_client`, `/list_clients`
4. **Второй клиент** (новая ниша)

---

## Открытые вопросы

- Telegram API для парсинга каналов — my.telegram.org не даёт создать приложение (попробовать позже)
- Мониторинг uptime (Uptime Kuma или healthcheck)
- Админ-команды: `/add_client`, `/list_clients` — следующий этап
- Автоматический онбординг через HTML-форму → Google Sheets → config.json
