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


async def run_migrations(db_path: str) -> None:
    """Применить ALTER TABLE миграции если колонки ещё не существуют.

    Args:
        db_path: Путь к файлу SQLite.
    """
    import aiosqlite

    async with aiosqlite.connect(db_path) as db:
        async with db.execute("PRAGMA table_info(clients)") as cursor:
            clients_cols = {row[1] async for row in cursor}
        async with db.execute("PRAGMA table_info(news)") as cursor:
            news_cols = {row[1] async for row in cursor}
        async with db.execute("PRAGMA table_info(settings)") as cursor:
            settings_cols = {row[1] async for row in cursor}

        migrations: list[str] = []

        if "client_str_id" not in clients_cols:
            migrations.append(
                "ALTER TABLE clients ADD COLUMN client_str_id VARCHAR(255)"
            )
        if "keyword_filtered" not in news_cols:
            migrations.append(
                "ALTER TABLE news ADD COLUMN keyword_filtered BOOLEAN NOT NULL DEFAULT 0"
            )
        if "importance_score" not in news_cols:
            migrations.append("ALTER TABLE news ADD COLUMN importance_score INTEGER")
        if "digest_mode" not in settings_cols:
            migrations.append(
                "ALTER TABLE settings ADD COLUMN digest_mode VARCHAR(50) NOT NULL DEFAULT 'compact'"
            )

        # Проверить наличие UNIQUE constraint на telegram_chat_id (старая схема)
        # SQLite не поддерживает DROP CONSTRAINT — пересоздаём таблицу без него
        async with db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='clients'") as cursor:
            row = await cursor.fetchone()
            clients_ddl = row[0] if row else ""
        if "UNIQUE" in clients_ddl and "telegram_chat_id" in clients_ddl:
            migrations.append("__fix_clients_unique__")

        if not migrations:
            logger.debug("Миграции БД: нет изменений.")
            return

        for sql in migrations:
            if sql == "__fix_clients_unique__":
                logger.info("Миграция БД: удаление UNIQUE constraint на clients.telegram_chat_id")
                await db.execute("PRAGMA foreign_keys=OFF")
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS clients_new (
                        id INTEGER PRIMARY KEY,
                        client_str_id VARCHAR(255) UNIQUE,
                        name VARCHAR(255) NOT NULL DEFAULT '',
                        telegram_chat_id BIGINT NOT NULL DEFAULT 0,
                        is_active BOOLEAN NOT NULL DEFAULT 1,
                        config_path VARCHAR(512) NOT NULL DEFAULT '',
                        created_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
                        updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP)
                    )
                """)
                await db.execute("""
                    INSERT OR IGNORE INTO clients_new
                        (id, client_str_id, name, telegram_chat_id, is_active, config_path, created_at, updated_at)
                    SELECT id, client_str_id, name, telegram_chat_id, is_active, config_path, created_at, updated_at
                    FROM clients
                """)
                await db.execute("DROP TABLE clients")
                await db.execute("ALTER TABLE clients_new RENAME TO clients")
                await db.execute("CREATE INDEX IF NOT EXISTS ix_clients_client_str_id ON clients (client_str_id)")
                await db.execute("CREATE INDEX IF NOT EXISTS ix_clients_telegram_chat_id ON clients (telegram_chat_id)")
                await db.execute("PRAGMA foreign_keys=ON")
            else:
                logger.info("Миграция БД: {}", sql)
                await db.execute(sql)

        await db.commit()
        logger.info("Миграции БД применены: {} шт.", len(migrations))


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Генератор сессии для использования в зависимостях."""
    async with _session_factory() as session:
        yield session
