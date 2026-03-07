"""
Точка входа приложения.

Запускает Telegram-бота и планировщик задач.
"""

import asyncio

from loguru import logger

from config import load_client_configs, settings
from database.db import create_tables, init_db
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


async def main() -> None:
    setup_logging()
    logger.info("Запуск IntelBot...")

    # Создать необходимые папки
    settings.data_path.mkdir(parents=True, exist_ok=True)
    settings.clients_path.mkdir(parents=True, exist_ok=True)

    # Инициализация БД
    init_db(str(settings.db_path))
    await create_tables()

    # Загрузка конфигов клиентов
    client_configs = load_client_configs(settings.clients_path)

    # Планировщик парсинга
    # on_items будет подключён к pipeline (processors/) в Этапе 2
    scheduler = ParserScheduler(
        client_configs=client_configs,
        data_path=settings.data_path,
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        on_items=None,  # TODO: подключить pipeline
    )
    await scheduler.start()

    # TODO: Инициализация и запуск Telegram-бота (bot/)

    logger.info(f"Бот запущен. Клиентов: {len(client_configs)}")

    try:
        # Держим event loop живым (заменить на asyncio.gather с ботом в Этапе 3)
        await asyncio.Event().wait()
    finally:
        await scheduler.stop()


if __name__ == "__main__":
    asyncio.run(main())
