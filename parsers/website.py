"""
Парсер произвольных веб-сайтов через aiohttp + BeautifulSoup4.

Использует CSS-селекторы из SelectorConfig для извлечения заголовка,
контента и даты публикации. Список ссылок получается со страницы-индекса
через селектор ссылок (links_selector) или берётся напрямую из url.
"""

import asyncio
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from configs.client_config_schema import SelectorConfig
from parsers.base import BaseParser, ParsedItem

# User-Agent, чтобы не блокировал сервер
_USER_AGENT = (
    "Mozilla/5.0 (compatible; IntelBot/1.0; +https://github.com/intelbot)"
)
_TIMEOUT = aiohttp.ClientTimeout(total=30)


async def _get_html(session: aiohttp.ClientSession, url: str) -> str:
    """Скачать HTML страницы."""
    async with session.get(url, timeout=_TIMEOUT) as response:
        response.raise_for_status()
        return await response.text(errors="replace")


def _extract_text(soup: BeautifulSoup, selector: str) -> str:
    """Извлечь текст по CSS-селектору."""
    tag = soup.select_one(selector)
    return tag.get_text(separator=" ", strip=True) if tag else ""


def _extract_date(soup: BeautifulSoup, selector: Optional[str]) -> Optional[datetime]:
    """Попытаться извлечь дату из тега по CSS-селектору.

    Проверяет атрибут datetime (тег <time>) и текстовое содержимое.
    """
    if not selector:
        return None
    tag = soup.select_one(selector)
    if not tag:
        return None

    # <time datetime="2024-01-15T10:00:00+00:00">
    dt_attr = tag.get("datetime")
    if dt_attr:
        try:
            return datetime.fromisoformat(str(dt_attr))
        except ValueError:
            pass

    # Попытка разобрать текст напрямую — возвращаем None если не получилось
    return None


class WebsiteParser(BaseParser):
    """Парсер произвольного сайта с CSS-селекторами.

    Args:
        source_name: Название источника.
        url: URL страницы-индекса (список статей) или одной статьи.
        selector: CSS-селекторы из конфига клиента.
        links_selector: CSS-селектор для получения ссылок на статьи
            со страницы-индекса. Если None — парсит url как одну статью.
        max_items: Максимальное количество статей за один запрос.
    """

    def __init__(
        self,
        source_name: str,
        url: str,
        selector: SelectorConfig,
        links_selector: Optional[str] = None,
        max_items: int = 20,
    ) -> None:
        super().__init__(source_name, url)
        self.selector = selector
        self.links_selector = links_selector
        self.max_items = max_items

    async def _parse_article(
        self, session: aiohttp.ClientSession, article_url: str
    ) -> Optional[ParsedItem]:
        """Разобрать одну статью и вернуть ParsedItem или None."""
        try:
            html = await _get_html(session, article_url)
        except Exception:
            self.logger.warning("Не удалось загрузить статью: {}", article_url)
            return None

        soup = BeautifulSoup(html, "lxml")

        title = _extract_text(soup, self.selector.title)
        content = _extract_text(soup, self.selector.content)

        if not title or not content:
            self.logger.debug("Пустой заголовок или контент: {}", article_url)
            return None

        published_at = _extract_date(soup, self.selector.date)

        return ParsedItem(
            url=article_url,
            title=title,
            content=content,
            source_name=self.source_name,
            published_at=published_at,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=False,
    )
    async def _get_article_links(self, session: aiohttp.ClientSession) -> list[str]:
        """Получить список URL статей со страницы-индекса."""
        html = await _get_html(session, self.url)
        soup = BeautifulSoup(html, "lxml")

        links = []
        for tag in soup.select(self.links_selector)[: self.max_items]:
            href = tag.get("href")
            if href:
                links.append(urljoin(self.url, str(href)))
        return links

    async def fetch(self) -> list[ParsedItem]:
        """Получить статьи с сайта.

        Returns:
            Список ParsedItem.
        """
        headers = {"User-Agent": _USER_AGENT}

        async with aiohttp.ClientSession(headers=headers) as session:
            # Если задан selectors для списка ссылок — парсим несколько статей
            if self.links_selector:
                try:
                    article_urls = await self._get_article_links(session)
                except Exception:
                    self.logger.exception("Не удалось получить список статей: {}", self.url)
                    return []

                tasks = [self._parse_article(session, url) for url in article_urls]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                items = [
                    r for r in results
                    if isinstance(r, ParsedItem)
                ]
            else:
                # Парсим url как одну статью
                item = await self._parse_article(session, self.url)
                items = [item] if item else []

        self.logger.info(
            "Получено {} статей с сайта: {}", len(items), self.source_name
        )
        return items
