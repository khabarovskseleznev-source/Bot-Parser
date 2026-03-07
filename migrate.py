"""
Скрипт миграции БД — добавляет новые колонки если не существуют.

Запускать вручную: python migrate.py
"""

import asyncio

import aiosqlite

from config import settings


async def migrate() -> None:
    db_path = str(settings.db_path)
    async with aiosqlite.connect(db_path) as db:
        # Получаем текущие колонки таблиц
        async with db.execute("PRAGMA table_info(news)") as cursor:
            news_cols = {row[1] async for row in cursor}
        async with db.execute("PRAGMA table_info(settings)") as cursor:
            settings_cols = {row[1] async for row in cursor}

        migrations = []

        if "keyword_filtered" not in news_cols:
            migrations.append(
                "ALTER TABLE news ADD COLUMN keyword_filtered BOOLEAN NOT NULL DEFAULT 0"
            )
        if "digest_mode" not in settings_cols:
            migrations.append(
                "ALTER TABLE settings ADD COLUMN digest_mode VARCHAR(50) NOT NULL DEFAULT 'compact'"
            )

        if not migrations:
            print("Нет новых миграций.")
            return

        for sql in migrations:
            print(f"Выполняю: {sql}")
            await db.execute(sql)

        await db.commit()
        print("Миграция завершена.")


if __name__ == "__main__":
    asyncio.run(migrate())
