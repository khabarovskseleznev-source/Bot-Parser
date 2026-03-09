# HANDOFF – IntelBot

> Читать в начале каждой сессии. Обновлять в конце.

---

## Статус проекта

**Фаза:** Этап 6 завершён. Следующая задача — feedback-обучение (улучшение выдачи новостей по реакциям).
**Последнее обновление:** 2026-03-09

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

**Этап 7 — Feedback-обучение (улучшение выдачи новостей по реакциям пользователя):**

Реакции (👍/👎/🔖) сохраняются в таблицу `feedback`, но пока никак не используются.
Задача: сделать так, чтобы реакции влияли на будущую выдачу.

**Что реализовать:**
1. **Корректировка importance_score по лайкам/дизлайкам** — при записи реакции обновлять score у новости
   (like: +2, dislike: -2, saved: +3, clamped 1–10)
2. **Команда `/stats`** — топ-3 темы за неделю (по хештегам лайкнутых), % тональностей
3. **RAG-буст лайкнутых** — при построении контекста отдавать приоритет новостям с liked=True
4. **Фильтр источников** — если из источника идут только дизлайки, снижать его приоритет

**Приоритет реализации:** 1 → 2 → 3 → 4

**Следующий этап (после feedback):**
- Мониторинг uptime (Uptime Kuma)
- Админ-команды: `/add_client`, `/list_clients`
- Автоматический онбординг: HTML-форма → Google Sheets → config.json → перезапуск бота
- Второй клиент (новая ниша)

---

## Открытые вопросы

- Telegram API для парсинга каналов — my.telegram.org не даёт создать приложение (попробовать позже)
- Мониторинг uptime (Uptime Kuma или healthcheck)
- Админ-команды: `/add_client`, `/list_clients` — следующий этап
- Автоматический онбординг через HTML-форму → Google Sheets → config.json
