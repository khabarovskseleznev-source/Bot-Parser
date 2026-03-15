# HANDOFF – IntelBot

> Читать в начале каждой сессии. Обновлять в конце.

---

## Статус проекта

**Фаза:** Этап 7 завершён + ревизия + деплой telegram_news. Бот работает на VPS, новости приходят.
**Последнее обновление:** 2026-03-16

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

## Второй клиент: telegram_news

- **Файл:** `data/clients/telegram_news/config.json`
- **Ниша:** Новости о Telegram, регулирование в России, ограничения, Durov, Роскомнадзор
- **Источники:** РБК, ТАСС, Коммерсантъ, Интерфакс, Habr, Meduza, Новая газета, The Moscow Times, CNews
- **Ключевые слова:** Telegram, Durov, блокировка, Роскомнадзор, ограничения, мессенджер, регулирование
- **Доставка:** instant (сразу после парсинга и keyword-фильтра)
- **Таблица источников:** обновлена в Google Sheets (лист "Источники") — 13 новых источников (ID 3-15)
- **Деплой (2026-03-16):** конфиг с CSS-селекторами скопирован на VPS через SCP, delivery переключён на instant, 14 накопленных новостей отправлены

- [x] **Ревизия кода (2026-03-15):**
  - groq_api_key → openrouter_api_key (config, pipeline, main)
  - XSS-защита: html.escape в sender для title/url/summary
  - Pipeline: batch-предзагрузка keywords/liked/low_priority (вместо per-item запросов)
  - Embedding: переиспользование из дедупликатора (убрано двойное вычисление)
  - LLMClient: переиспользование aiohttp.ClientSession
  - DRY: get_client_by_chat_id() в crud.py, убраны дубли в handlers
  - sender.send_digest: ORM → dict до закрытия сессии (fix detached objects)
  - parsers/rss: reraise=True в retry
  - Удалён дублирующий migrate.py
  - loguru: f-string → placeholder-формат

---

## Следующий шаг

**Этап 8 — Качество контента + мониторинг:**

1. **Настройка качества контента** — keyword-фильтр пропускает ~1% новостей, нужна калибровка
2. **Известный баг:** `UnboundLocalError: text_for_embed` в `processors/pipeline.py`
3. **ai_news_1 отсутствует в БД** — только telegram_news (client id=1)
4. **Мониторинг uptime** — Uptime Kuma (docker container на том же VPS)
5. **Удалить** старую папку `~/intelbot/` на VPS (`rm -rf ~/intelbot`)
6. **Третий клиент** — новая ниша (строительство / FMCG / тендеры / иное)
7. **Админ-команды:** `/add_client`, `/list_clients`

---

## Открытые вопросы

- Telegram API для парсинга каналов — my.telegram.org не даёт создать приложение
- Автоматический онбординг: HTML-форма → Google Sheets → config.json → перезапуск бота
