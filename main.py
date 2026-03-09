"""
Точка входа приложения.

Запускает Telegram-бота и планировщик задач.
"""

import asyncio
import os
import ssl

import certifi

# macOS fix: системные сертификаты не доверяют многим CA
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
ssl._create_default_https_context = ssl.create_default_context  # noqa: SLF001

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from bot.bot import create_bot, create_dispatcher
from bot.sender import NewsSender
from config import load_client_configs, settings
from database.crud import get_or_create_client
from database.db import create_tables, get_session, init_db, run_migrations
from processors.pipeline import NewsPipeline, make_on_items_callback
from scheduler import ParserScheduler


def setup_logging() -> None:
    """Настроить Loguru: вывод в консоль и файл с ротацией."""
    settings.logs_path.mkdir(parents=True, exist_ok=True)

    logger.add(
        settings.logs_path / "app_{time:YYYY-MM-DD}.log",
        rotation="00:00",       # новый файл каждый день
        retention="30 days",
        compression="zip",
        level="INFO",
        encoding="utf-8",
    )


async def build_pipelines(
    client_configs: dict,
    sender: NewsSender,
) -> dict[str, NewsPipeline]:
    """Инициализировать NewsPipeline для каждого клиента.

    Синхронизирует клиентов из конфигов с таблицей clients в БД.

    Args:
        client_configs: Словарь {client_str_id: ClientConfig}.
        sender: Экземпляр NewsSender для отправки новостей.

    Returns:
        Словарь {client_str_id: NewsPipeline}.
    """
    chroma_path = settings.data_path / "chroma"
    chroma_path.mkdir(parents=True, exist_ok=True)

    pipelines: dict[str, NewsPipeline] = {}

    async for session in get_session():
        for client_str_id, config in client_configs.items():
            client = await get_or_create_client(
                session=session,
                client_str_id=client_str_id,
                name=config.client_name,
                telegram_chat_id=config.telegram_chat_id,
                config_path=str(settings.clients_path / client_str_id / "config.json"),
            )

            pipelines[client_str_id] = NewsPipeline(
                client_id=client.id,
                client_str_id=client_str_id,
                chroma_path=chroma_path,
                telegram_chat_id=config.telegram_chat_id,
                groq_api_key=settings.groq_api_key,
                sender=sender,
            )
            logger.info("Pipeline создан: {} (db_id={})", client_str_id, client.id)

    return pipelines


def _register_digest_jobs(
    digest_scheduler: AsyncIOScheduler,
    client_configs: dict,
    pipelines: dict[str, NewsPipeline],
    sender: NewsSender,
) -> None:
    """Зарегистрировать джобы отправки дайджеста для клиентов с hourly/daily режимом.

    Args:
        digest_scheduler: Планировщик для дайджест-задач.
        client_configs: Словарь {client_str_id: ClientConfig}.
        pipelines: Словарь {client_str_id: NewsPipeline}.
        sender: Экземпляр NewsSender.
    """
    for client_str_id, config in client_configs.items():
        pipeline = pipelines.get(client_str_id)
        if pipeline is None:
            continue

        frequency = config.delivery.frequency
        if frequency == "instant":
            continue  # instant-режим не использует дайджест-джобы

        client_id = pipeline._client_id
        chat_id = config.telegram_chat_id

        if frequency == "hourly":
            digest_scheduler.add_job(
                sender.send_digest,
                trigger=IntervalTrigger(hours=1),
                args=[client_id, chat_id],
                id=f"digest_hourly__{client_str_id}",
                name=f"[{client_str_id}] hourly digest",
                replace_existing=True,
                max_instances=1,
            )
            logger.info("Дайджест hourly зарегистрирован: {}", client_str_id)

        elif frequency == "daily":
            # Парсим время из конфига (например "09:00"), fallback на 08:00 UTC
            daily_time = config.delivery.daily_time or "08:00"
            try:
                hour, minute = map(int, daily_time.split(":"))
            except ValueError:
                hour, minute = 8, 0

            digest_scheduler.add_job(
                sender.send_digest,
                trigger=CronTrigger(hour=hour, minute=minute, timezone="UTC"),
                args=[client_id, chat_id],
                id=f"digest_daily__{client_str_id}",
                name=f"[{client_str_id}] daily digest {daily_time} UTC",
                replace_existing=True,
                max_instances=1,
            )
            logger.info(
                "Дайджест daily зарегистрирован: {} в {}:00 UTC",
                client_str_id,
                daily_time,
            )


async def main() -> None:
    setup_logging()
    logger.info("Запуск IntelBot...")

    # Создать необходимые папки
    settings.data_path.mkdir(parents=True, exist_ok=True)
    settings.clients_path.mkdir(parents=True, exist_ok=True)

    # Инициализация БД
    init_db(str(settings.db_path))
    await create_tables()
    await run_migrations(str(settings.db_path))

    # Загрузка конфигов клиентов
    client_configs = load_client_configs(settings.clients_path)

    # Инициализация Telegram-бота
    bot = create_bot(settings.bot_token)
    dp = create_dispatcher()
    sender = NewsSender(bot)

    # Инициализация пайплайнов (синхронизация с БД + ChromaDB)
    pipelines = await build_pipelines(client_configs, sender)
    on_items = make_on_items_callback(pipelines)

    # Планировщик парсинга с подключённым pipeline
    scheduler = ParserScheduler(
        client_configs=client_configs,
        data_path=settings.data_path,
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        on_items=on_items,
    )
    await scheduler.start()

    # Планировщик дайджестов (hourly / daily)
    digest_scheduler = AsyncIOScheduler(timezone="UTC")
    _register_digest_jobs(digest_scheduler, client_configs, pipelines, sender)
    digest_scheduler.start()
    logger.info("Планировщик дайджестов запущен.")

    logger.info("Бот запущен. Клиентов: {}", len(client_configs))

    try:
        # Polling блокирует event loop; оба scheduler работают параллельно через APScheduler
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await scheduler.stop()
        digest_scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
