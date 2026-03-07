# Настройка и деплой

## Локальный запуск

```bash
# 1. Клонировать репозиторий
git clone <url> && cd news-monitor-bot

# 2. Создать виртуальное окружение
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Установить зависимости
pip install -r requirements.txt

# 4. Настроить переменные окружения
cp .env.example .env
# Заполнить .env (см. ниже)

# 5. Запустить
python main.py
```

## Переменные окружения (`.env`)

```env
BOT_TOKEN=токен_от_BotFather
ADMIN_IDS=id1,id2
TELEGRAM_API_ID=...         # для Telethon
TELEGRAM_API_HASH=...       # для Telethon
DATA_PATH=./data
OLLAMA_URL=http://localhost:11434
DEFAULT_MODEL=saiga_llama3_8b
```

## Ollama

```bash
ollama pull saiga_llama3_8b
```

## Docker

```bash
docker-compose up --build
```

Папка `data/` монтируется в контейнер — данные клиентов сохраняются между перезапусками.

## Сервер

Ubuntu 22.04, Docker, NVIDIA Container Toolkit (если нужен GPU для LLM).
Запуск через `docker-compose` или systemd.

---

## Онбординг нового клиента

1. Создать папку `data/clients/client_<id>/`
2. Создать `data/clients/client_<id>/config.json` по схеме из [client-config.md](client-config.md)
3. Перезапустить бота — конфиг подхватится автоматически при старте
