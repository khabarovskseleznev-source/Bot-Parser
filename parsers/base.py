"""
Базовый абстрактный класс парсера.

Все парсеры (RSS, Telegram, Website, Social) наследуют от BaseParser
и обязаны реализовать метод fetch().
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from loguru import logger


@dataclass
class ParsedItem:
    """Результат парсинга одной новости."""

    url: str
    title: str
    content: str
    source_name: str
    published_at: Optional[datetime] = None
    # Дополнительные поля, специфичные для источника
    extra: dict = field(default_factory=dict)


class BaseParser(ABC):
    """Абстрактный базовый класс для всех парсеров.

    Args:
        source_name: Человекочитаемое название источника.
        url: URL источника (RSS-лента, Telegram-канал, сайт и т.д.).
    """

    def __init__(self, source_name: str, url: str) -> None:
        self.source_name = source_name
        self.url = url
        self.logger = logger.bind(parser=self.__class__.__name__, source=source_name)

    @abstractmethod
    async def fetch(self) -> list[ParsedItem]:
        """Получить список новых публикаций из источника.

        Returns:
            Список ParsedItem. Может быть пустым.

        Raises:
            Не должен пробрасывать исключения наружу — логировать и возвращать [].
        """

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(source={self.source_name!r}, url={self.url!r})"
