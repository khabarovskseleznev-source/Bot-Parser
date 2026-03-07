"""
Точка входа приложения.

Запускает Telegram-бота и планировщик задач.
"""

import asyncio

from loguru import logger

from config import load_client_configs, settings
from database.crud import get_or_create_client
from database.db import create_tables, get_session, init_db
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


async def build_pipelines(client_configs: dict) -> dict[str, NewsPipeline]:
    """Инициализировать NewsPipeline для каждого клиента.

    Синхронизирует клиентов из конфигов с таблицей clients в БД.

    Args:
        client_configs: Словарь {client_str_id: ClientConfig}.

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
                ollama_url=settings.ollama_url,
                ollama_model=settings.default_model,
            )
            logger.info("Pipeline создан: {} (db_id={})", client_str_id, client.id)

    return pipelines


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

    # Инициализация пайплайнов (синхронизация с БД + ChromaDB)
    pipelines = await build_pipelines(client_configs)
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

    # TODO: Инициализация и запуск Telegram-бота (bot/) — Этап 3

    logger.info("Бот запущен. Клиентов: {}", len(client_configs))

    try:
        # Держим event loop живым (заменить на asyncio.gather с ботом в Этапе 3)
        await asyncio.Event().wait()
    finally:
        await scheduler.stop()


if __name__ == "__main__":
    asyncio.run(main())
