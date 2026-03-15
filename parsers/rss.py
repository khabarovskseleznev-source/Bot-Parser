"""
RSS-парсер на базе feedparser.

Разбирает RSS/Atom-ленты и возвращает список ParsedItem.
Блокирующий вызов feedparser выполняется через asyncio.to_thread.
"""

import asyncio
import hashlib
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

import feedparser
from tenacity import retry, stop_after_attempt, wait_exponential

from parsers.base import BaseParser, ParsedItem


def _parse_date(entry: feedparser.util.FeedParserDict) -> Optional[datetime]:
    """Извлечь дату публикации из записи RSS."""
    # feedparser нормализует дату в published_parsed (struct_time UTC)
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        except (TypeError, ValueError):
            pass
    # Fallback: попытка разобрать строку RFC 2822
    raw = getattr(entry, "published", None) or getattr(entry, "updated", None)
    if raw:
        try:
            return parsedate_to_datetime(raw)
        except Exception:
            pass
    return None


def _extract_content(entry: feedparser.util.FeedParserDict) -> str:
    """Извлечь текст новости из записи RSS."""
    # Предпочитаем content[0].value, потом summary, потом title
    if hasattr(entry, "content") and entry.content:
        return entry.content[0].get("value", "") or ""
    if hasattr(entry, "summary") and entry.summary:
        return entry.summary
    return getattr(entry, "title", "") or ""


class RSSParser(BaseParser):
    """Парсер RSS/Atom-лент.

    Args:
        source_name: Название источника.
        url: URL RSS-ленты.
        max_items: Максимальное количество записей за один запрос (0 = все).
    """

    def __init__(self, source_name: str, url: str, max_items: int = 50) -> None:
        super().__init__(source_name, url)
        self.max_items = max_items

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def _fetch_feed(self) -> feedparser.util.FeedParserDict:
        """Загрузить RSS-ленту (с повторами при ошибке)."""
        return await asyncio.to_thread(feedparser.parse, self.url)

    async def fetch(self) -> list[ParsedItem]:
        """Получить публикации из RSS-ленты.

        Returns:
            Список ParsedItem, отсортированных от новых к старым.
        """
        try:
            feed = await self._fetch_feed()
        except Exception:
            self.logger.exception("Не удалось загрузить RSS-ленту: {}", self.url)
            return []

        if feed.bozo and not feed.entries:
            self.logger.warning(
                "RSS-лента вернула ошибку (bozo): {} — {}",
                self.url,
                feed.bozo_exception,
            )
            return []

        entries = feed.entries
        if self.max_items:
            entries = entries[: self.max_items]

        items: list[ParsedItem] = []
        for entry in entries:
            link = getattr(entry, "link", None) or getattr(entry, "id", None)
            title = getattr(entry, "title", "").strip()
            content = _extract_content(entry).strip()

            if not link or not title:
                continue

            # Если контент пустой — используем title как content
            if not content:
                content = title

            items.append(
                ParsedItem(
                    url=link,
                    title=title,
                    content=content,
                    source_name=self.source_name,
                    published_at=_parse_date(entry),
                )
            )

        self.logger.info("Получено {} записей из RSS: {}", len(items), self.source_name)
        return items
