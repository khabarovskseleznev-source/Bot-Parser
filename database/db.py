"""
Подключение к базе данных и управление сессиями.
"""

from collections.abc import AsyncGenerator

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database.models import Base

_engine = None
_session_factory = None


def init_db(db_path: str) -> None:
    """Инициализировать движок и фабрику сессий.

    Args:
        db_path: Путь к файлу SQLite (например, ./data/global.db).
    """
    global _engine, _session_factory

    url = f"sqlite+aiosqlite:///{db_path}"
    _engine = create_async_engine(url, echo=False)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    logger.info(f"База данных инициализирована: {db_path}")


async def create_tables() -> None:
    """Создать все таблицы если не существуют."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Таблицы созданы (или уже существуют)")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Генератор сессии для использования в зависимостях."""
    async with _session_factory() as session:
        yield session
