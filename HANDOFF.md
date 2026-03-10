# HANDOFF – IntelBot

> Читать в начале каждой сессии. Обновлять в конце.

---

## Статус проекта

**Фаза:** Этап 7 завершён (feedback-обучение). Деплой выполнен на VPS.
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
- [x] **bot/** — handlers (start, settings FSM, feedback, stats), sender (instant + digest)
- [x] **22 unit-теста** — все зелёные
- [x] **Dockerfile** — torch CPU-only (без CUDA), образ ~1.5GB
- [x] **importance_score (1-10)** — добавлен в LLM-промпт, модель, pipeline, дайджест (топ-20 по score)
- [x] **Этап 6 — деплой на VPS** (Timeweb, Ubuntu, IP: 85.239.51.247):
  - Docker, Swap 2 ГБ, SSH-ключ, Groq API, конфиг клиента ai_news_1
  - Парсинг работает, бот отвечает на /start, /settings
- [x] **Этап 7 — Feedback-обучение:**
  - `update_importance_by_feedback` — like +2, saved +3, dislike -2, clamp 1-10
  - `/stats` — топ-3 хештеги + % тональностей лайкнутых за 7 дней
  - RAG-буст лайкнутых (`build_context` с `liked_news_ids`)
  - Фильтр источников — `get_low_priority_source_ids` (≥70% дизлайков → пропуск)
  - OOM исправлен: модель заменена на `all-MiniLM-L6-v2` (~90 МБ)
  - Репозиторий сделан **публичным**, деплой через git clone работает

---

## VPS

- **IP:** 85.239.51.247 | **Логин:** root | **Пароль:** uh1+FEExZdw_96
- **Рабочая папка:** `~/intelbot2/` (старая `~/intelbot/` можно удалить)
- **Репозиторий:** https://github.com/khabarovskseleznev-source/Bot-Parser
- **Команды:**
  ```bash
  cd ~/intelbot2 && docker compose logs bot -f          # логи
  cd ~/intelbot2 && docker compose restart bot          # перезапуск
  # Деплой новой версии:
  cd ~/intelbot2 && git pull && docker compose build --no-cache && docker compose up -d
  ```
- **Диск:** 55% занято (6.2 ГБ свободно) — после очистки Docker-кэша

---

## Первый клиент: ai_news_1

- **Файл:** `data/clients/ai_news_1/config.json`
- **Ниша:** ИИ-новости и новые продукты
- **chat_id:** 5026462041
- **Источники (RSS):** TechCrunch, Ars Technica, The Verge, Habr AI, vc.ru, YouTube (Computerphile, NVIDIA, Karpathy, Kilcher, AI Explained, 3Blue1Brown)
- **Ключевые слова:** AI, LLM, GPT, Claude, Gemini, Llama, нейросеть, OpenAI, Anthropic...
- **Доставка:** раз в день в 09:00 UTC, формат полный
- **Telegram-каналы:** не подключены (my.telegram.org не даёт создать API-приложение)

---

## Следующий шаг

**Этап 8 — Мониторинг + второй клиент:**

1. **Мониторинг uptime** — Uptime Kuma (docker container на том же VPS)
2. **Удалить** старую папку `~/intelbot/` на VPS (`rm -rf ~/intelbot`)
3. **Второй клиент** — новая ниша (строительство / FMCG / тендеры)
4. **Админ-команды:** `/add_client`, `/list_clients`

---

## Открытые вопросы

- Telegram API для парсинга каналов — my.telegram.org не даёт создать приложение
- Автоматический онбординг: HTML-форма → Google Sheets → config.json → перезапуск бота
