"""
Планировщик задач парсинга.

Запускает парсеры по расписанию (APScheduler) для каждого источника каждого клиента.
После получения данных вызывает переданный callback для дальнейшей обработки.

Пример использования:
    scheduler = ParserScheduler(client_configs, settings, on_items=process_items)
    await scheduler.start()
    ...
    await scheduler.stop()
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from configs.client_config_schema import ClientConfig, SourceConfig
from parsers.base import BaseParser, ParsedItem
from parsers.rss import RSSParser
from parsers.social import SocialParser
from parsers.telegram import TelegramChannelParser
from parsers.website import WebsiteParser

# Тип callback-функции: получает client_id, source_config и список новостей
OnItemsCallback = Callable[[str, SourceConfig, list[ParsedItem]], Awaitable[None]]


def _build_parser(
    source: SourceConfig,
    api_id: int,
    api_hash: str,
    session_dir: Path,
) -> BaseParser:
    """Создать парсер нужного типа по конфигу источника.

    Args:
        source: Конфиг источника из ClientConfig.
        api_id: Telegram API ID (используется только для type=telegram).
        api_hash: Telegram API Hash (используется только для type=telegram).
        session_dir: Директория для хранения файлов сессий Telethon.

    Returns:
        Инстанс парсера, унаследованного от BaseParser.
    """
    match source.type:
        case "rss":
            return RSSParser(source_name=source.name, url=source.url)
        case "telegram":
            return TelegramChannelParser(
                source_name=source.name,
                url=source.url,
                api_id=api_id,
                api_hash=api_hash,
                session_path=session_dir,
            )
        case "website":
            if source.selector is None:
                logger.warning(
                    "Источник '{}' типа website не имеет selector — пропускаю.", source.name
                )
                return SocialParser(source_name=source.name, url=source.url)
            return WebsiteParser(
                source_name=source.name,
                url=source.url,
                selector=source.selector,
            )
        case "social":
            return SocialParser(source_name=source.name, url=source.url)
        case _:
            logger.warning("Неизвестный тип источника '{}', использую SocialParser.", source.type)
            return SocialParser(source_name=source.name, url=source.url)


class ParserScheduler:
    """Планировщик парсинга для всех клиентов и источников.

    Args:
        client_configs: Словарь {client_id: ClientConfig}.
        data_path: Корневая директория данных (./data).
        api_id: Telegram API ID.
        api_hash: Telegram API Hash.
        on_items: Async callback, вызываемый после каждого успешного запуска парсера.
    """

    def __init__(
        self,
        client_configs: dict[str, ClientConfig],
        data_path: Path,
        api_id: int,
        api_hash: str,
        on_items: Optional[OnItemsCallback] = None,
    ) -> None:
        self._client_configs = client_configs
        self._data_path = data_path
        self._api_id = api_id
        self._api_hash = api_hash
        self._on_items = on_items
        self._scheduler = AsyncIOScheduler(timezone="UTC")

    def _register_jobs(self) -> None:
        """Зарегистрировать задачи для всех активных источников всех клиентов."""
        for client_id, config in self._client_configs.items():
            for source in config.sources:
                if not source.is_active:
                    continue

                session_dir = self._data_path / "clients" / client_id
                session_dir.mkdir(parents=True, exist_ok=True)

                parser = _build_parser(
                    source=source,
                    api_id=self._api_id,
                    api_hash=self._api_hash,
                    session_dir=session_dir,
                )

                job_id = f"{client_id}__{source.name}"
                self._scheduler.add_job(
                    self._run_parser,
                    trigger=IntervalTrigger(minutes=source.fetch_interval_minutes),
                    args=[client_id, source, parser],
                    id=job_id,
                    name=f"[{client_id}] {source.name}",
                    replace_existing=True,
                    max_instances=1,  # не запускать повторно, если предыдущий ещё работает
                )
                logger.info(
                    "Задача зарегистрирована: {} (каждые {} мин)",
                    job_id,
                    source.fetch_interval_minutes,
                )

    async def _run_parser(
        self,
        client_id: str,
        source: SourceConfig,
        parser: BaseParser,
    ) -> None:
        """Запустить парсер и передать результаты в callback.

        Ошибки не пробрасываются — логируются и задача продолжает работать.
        """
        logger.debug("Запуск парсера: {} / {}", client_id, source.name)
        try:
            items = await parser.fetch()
        except Exception:
            logger.exception("Необработанная ошибка в парсере: {} / {}", client_id, source.name)
            return

        if not items:
            logger.debug("Нет новых элементов: {} / {}", client_id, source.name)
            return

        logger.info(
            "Получено {} элементов: {} / {}",
            len(items),
            client_id,
            source.name,
        )

        if self._on_items:
            try:
                await self._on_items(client_id, source, items)
            except Exception:
                logger.exception(
                    "Ошибка в on_items callback: {} / {}", client_id, source.name
                )

    async def start(self) -> None:
        """Запустить планировщик и зарегистрировать все задачи."""
        self._register_jobs()
        self._scheduler.start()
        logger.info(
            "Планировщик запущен. Задач: {}", len(self._scheduler.get_jobs())
        )

    async def stop(self) -> None:
        """Остановить планировщик."""
        self._scheduler.shutdown(wait=False)
        logger.info("Планировщик остановлен.")

    def reload_client(self, client_id: str, config: ClientConfig) -> None:
        """Перезагрузить задачи для одного клиента (при изменении конфига).

        Args:
            client_id: ID клиента.
            config: Новый конфиг клиента.
        """
        # Удалить старые задачи клиента
        for job in self._scheduler.get_jobs():
            if job.id.startswith(f"{client_id}__"):
                job.remove()

        # Добавить обновлённые
        self._client_configs[client_id] = config
        for source in config.sources:
            if not source.is_active:
                continue

            session_dir = self._data_path / "clients" / client_id
            session_dir.mkdir(parents=True, exist_ok=True)

            parser = _build_parser(
                source=source,
                api_id=self._api_id,
                api_hash=self._api_hash,
                session_dir=session_dir,
            )

            job_id = f"{client_id}__{source.name}"
            self._scheduler.add_job(
                self._run_parser,
                trigger=IntervalTrigger(minutes=source.fetch_interval_minutes),
                args=[client_id, source, parser],
                id=job_id,
                name=f"[{client_id}] {source.name}",
                replace_existing=True,
                max_instances=1,
            )

        logger.info("Конфиг клиента {} перезагружен в планировщике.", client_id)
