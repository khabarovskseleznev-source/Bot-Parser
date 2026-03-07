"""
Парсер Telegram-каналов через Telethon.

Читает публичные каналы по username или invite-ссылке.
Требует TELEGRAM_API_ID и TELEGRAM_API_HASH в .env.

Сессия Telethon хранится в data/clients/<client_id>/telethon.session.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from telethon import TelegramClient
from telethon.tl.types import Message, MessageMediaDocument, MessageMediaPhoto
from tenacity import retry, stop_after_attempt, wait_exponential

from parsers.base import BaseParser, ParsedItem


def _build_url(channel_username: str, message_id: int) -> str:
    """Сформировать URL поста в Telegram."""
    username = channel_username.lstrip("@")
    return f"https://t.me/{username}/{message_id}"


def _extract_text(message: Message) -> str:
    """Извлечь текст из сообщения Telegram."""
    text = message.text or message.message or ""
    return text.strip()


def _has_media(message: Message) -> bool:
    """Проверить, есть ли медиавложение (фото или документ)."""
    return isinstance(message.media, (MessageMediaPhoto, MessageMediaDocument))


class TelegramChannelParser(BaseParser):
    """Парсер публичного Telegram-канала.

    Args:
        source_name: Название источника.
        url: Username канала (например, @channelname или просто channelname).
        api_id: Telegram API ID (из my.telegram.org).
        api_hash: Telegram API Hash.
        session_path: Путь к файлу сессии Telethon.
        limit: Максимальное количество постов за один запрос.
        min_id: ID поста, с которого начинать (исключительно). 0 = все последние.
    """

    def __init__(
        self,
        source_name: str,
        url: str,
        api_id: int,
        api_hash: str,
        session_path: Path,
        limit: int = 50,
        min_id: int = 0,
    ) -> None:
        super().__init__(source_name, url)
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_path = session_path
        self.limit = limit
        self.min_id = min_id

    @property
    def _channel_username(self) -> str:
        """Нормализованный username канала."""
        username = self.url.strip().lstrip("@")
        # Поддержка ссылок вида https://t.me/channelname
        if "/" in username:
            username = username.rstrip("/").split("/")[-1]
        return username

    async def fetch(self) -> list[ParsedItem]:
        """Получить последние посты из Telegram-канала.

        Returns:
            Список ParsedItem от новых к старым.
        """
        session_file = str(self.session_path / f"telethon_{self._channel_username}")

        client = TelegramClient(
            session_file,
            self.api_id,
            self.api_hash,
        )

        items: list[ParsedItem] = []
        try:
            await client.start()

            messages = await client.get_messages(
                self._channel_username,
                limit=self.limit,
                min_id=self.min_id,
            )

            for message in messages:
                if not isinstance(message, Message):
                    continue

                text = _extract_text(message)
                if not text:
                    # Пропускаем посты без текста (только медиа без подписи)
                    continue

                # Для постов без заголовка берём первые 100 символов как title
                title = text[:100].replace("\n", " ")
                if len(text) > 100:
                    title += "..."

                published_at: Optional[datetime] = None
                if message.date:
                    published_at = message.date.replace(tzinfo=timezone.utc)

                items.append(
                    ParsedItem(
                        url=_build_url(self._channel_username, message.id),
                        title=title,
                        content=text,
                        source_name=self.source_name,
                        published_at=published_at,
                        extra={
                            "message_id": message.id,
                            "has_media": _has_media(message),
                            "views": getattr(message, "views", None),
                            "forwards": getattr(message, "forwards", None),
                        },
                    )
                )

        except Exception:
            self.logger.exception(
                "Ошибка парсинга Telegram-канала: {}", self._channel_username
            )
            return []
        finally:
            await client.disconnect()

        self.logger.info(
            "Получено {} постов из Telegram: {}", len(items), self.source_name
        )
        return items
