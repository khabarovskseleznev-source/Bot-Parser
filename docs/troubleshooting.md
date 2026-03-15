# Troubleshooting — IntelBot

Справочник по ошибкам и их решениям. Обновлять при каждой новой находке.

---

## 1. OOM Killer убивает бот при старте

**Симптом:** контейнер падает через 30–60 сек после старта, в `dmesg` видно:
```
Out of memory: Killed process XXXX (python)
```
**Причина:** все источники стартуют одновременно (`next_run_time=now()`), модель эмбеддингов (`all-MiniLM-L6-v2`) загружается параллельно несколько раз → пик RAM ~775 МБ при лимите 961 МБ.

**Решение:** stagger-задержка в `scheduler.py` — каждый источник стартует на 30 сек позже предыдущего:
```python
stagger_seconds += 30
next_run_time = datetime.now(timezone.utc) + timedelta(seconds=stagger_seconds)
```

**Проверка:** `dmesg | grep -i oom` — не должно быть новых записей.

---

## 2. Keywords-фильтр не работает — приходят нерелевантные новости

**Симптом:** бот присылает новости не по теме, в БД `keyword_filtered = 0` у всех записей.

**Причина:** таблица `settings` в SQLite пустая. `pipeline.py` берёт keywords из `settings.keywords`, а не из `config.json` напрямую. При первом запуске settings не создаются автоматически.

**Решение:** добавить `upsert_client_settings()` в `main.py` при инициализации клиента (после `get_or_create_client`). Функция создаёт/обновляет запись в `settings` с keywords из `config.json`.

**Проверка:**
```bash
docker compose exec bot python3 -c "
import sqlite3, json
conn = sqlite3.connect('data/global.db')
cur = conn.cursor()
cur.execute('SELECT keywords FROM settings WHERE client_id = 1')
print(json.loads(cur.fetchone()[0]))
"
```

---

## 3. Изменения в коде не применяются после `docker compose restart`

**Симптом:** правишь файл на хосте, перезапускаешь бот — изменения не применяются.

**Причина:** `docker-compose.yml` монтирует только `data/` и `logs/`. Код запекается в образ при `docker compose build`.

**Решения (от быстрого к надёжному):**

| Способ | Команда | Когда использовать |
|---|---|---|
| Быстрый (без пересборки) | `docker compose cp file.py bot:/app/path/file.py && docker compose restart bot` | 1–2 файла |
| Пересборка образа | `docker compose build --no-cache bot && docker compose up -d bot` | много файлов или зависимости |
| SSH + git pull | `git pull && docker compose build --no-cache && docker compose up -d` | после коммита в репо |

> **Важно:** `data/clients/<id>/config.json` монтируется через volume `./data:/app/data`, поэтому config.json достаточно скопировать через `scp` и перезапустить бот.

---

## 4. Долгий `docker compose build` обрывает SSH

**Симптом:** сборка образа (~5 мин) убивает SSH-сессию.

**Причина:** fail2ban или таймаут SSH.

**Решение:** запускать сборку в фоне:
```bash
nohup docker compose build --no-cache > /tmp/build.log 2>&1 &
tail -f /tmp/build.log  # следить за прогрессом
```
Или использовать Timeweb web-консоль (вкладка "Консоль") — не зависит от SSH.

---

## 5. ChromaDB несовместима после смены embedding-модели

**Симптом:** ошибки при старте ChromaDB, старые векторы не читаются.

**Причина:** старые векторы в `data/chroma/` имеют размерность 768 (paraphrase-multilingual-MiniLM-L12-v2), новая модель — 384 (all-MiniLM-L6-v2).

**Решение:** удалить старые данные ChromaDB:
```bash
rm -rf ~/intelbot2/data/chroma
docker compose restart bot
```
> Векторная история теряется, дедупликация начнётся заново — это нормально.

---

## 6. Бот загружает старого клиента после переименования папки

**Симптом:** переименовал `data/clients/ai_news_1` в `_disabled_ai_news_1`, но бот всё равно его загружает.

**Причина:** код запечён в Docker-образ при `build`. Папка `data/clients/` монтируется через volume, но бот читает её через `load_client_configs` — а там `_disabled_` не фильтруется.

**Решение:** удалить папку на VPS (`rm -rf data/clients/ai_news_1`) ИЛИ добавить фильтрацию в `config.py`:
```python
# В load_client_configs — пропускать папки начинающиеся с "_"
if client_id.startswith("_"):
    continue
```

---

## 7. Неправильный файл БД (intelbot.db вместо global.db)

**Симптом:** `python3 -c "import sqlite3; conn = sqlite3.connect('data/intelbot.db')"` — таблица `news` не найдена.

**Причина:** рабочая БД называется `data/global.db`, а не `data/intelbot.db`.

**Проверка правильного пути:**
```bash
docker compose exec bot python3 -c "
import sqlite3, os
for f in os.listdir('data'):
    if f.endswith('.db'):
        conn = sqlite3.connect(f'data/{f}')
        cur = conn.cursor()
        cur.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")
        print(f, [r[0] for r in cur.fetchall()])
"
```

---

## 8. Website-источники не парсятся (SocialParser-заглушка)

**Симптом:** в логах `SocialParser не реализован. Источник X пропущен.`

**Причина:** источники с `"type": "website"` без поля `"selector"` попадают в `SocialParser` (заглушка).

**Решение:**
- Добавить `"selector"` в конфиг источника (CSS-селектор ссылок на статьи)
- ИЛИ конвертировать источник в RSS если есть лента

**Пример добавления RSS вместо website:**
```json
{"type": "rss", "url": "https://example.com/rss.xml", ...}
```

---

## 9. OpenRouter 429 Too Many Requests

**Симптом:** `LLM: ошибка подключения к Groq: 429` (название сообщения устаревшее, реально это OpenRouter).

**Причина:** бесплатный лимит OpenRouter на модель исчерпан (RPM/RPD лимиты).

**Решение:** бот продолжает работу (fallback — новость сохраняется без summary/sentiment). Если 429 постоянные:
- Сменить модель в `.env` (`OPENROUTER_MODEL`)
- Проверить баланс на openrouter.ai
- Текущая стабильная модель: `nvidia/nemotron-nano-12b-v2-vl:free`

---

## Чеклист при добавлении нового клиента

- [ ] Создать `data/clients/<id>/config.json` по схеме из `configs/client_config_schema.py`
- [ ] Проверить `frequency` — только `"instant"`, `"hourly"`, `"daily"` (не `twice_daily`!)
- [ ] Указать `daily_time` если `frequency: "daily"` (формат `"HH:MM"`)
- [ ] Источники типа `website` — нужен CSS `selector` или использовать RSS
- [ ] Скопировать config на VPS: `scp data/clients/<id>/config.json root@VPS:~/intelbot2/data/clients/<id>/config.json`
- [ ] Перезапустить бот: `docker compose restart bot`
- [ ] Проверить логи: `docker compose logs bot --tail=20` — убедиться что клиент загружен и settings записаны
- [ ] Проверить settings в БД: `SELECT keywords FROM settings WHERE client_id = X`
- [ ] Убедиться что бот не падает от OOM через 2–3 минуты
