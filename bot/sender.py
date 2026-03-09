"""
Форматирование и отправка новостей пользователю.

Каждое сообщение содержит:
  - Заголовок + ссылка
  - Краткое изложение (summary)
  - Тональность (sentiment)
  - Хештеги
  - Инлайн-кнопки: Нравится / Не интересно / Сохранить

После успешной отправки вызывает mark_sent() в БД.
"""

import asyncio

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions
from loguru import logger

from database.crud import get_client_settings, get_unsent_news, mark_sent
from database.db import get_session
from database.models import News

_SENTIMENT_EMOJI = {
    "positive": "🟢",
    "neutral": "🔵",
    "negative": "🔴",
}


def _format_message(news: News) -> str:
    """Сформировать HTML-текст сообщения для Telegram.

    Args:
        news: Объект News с заполненными полями анализа.

    Returns:
        Строка HTML-разметки.
    """
    sentiment_label = news.sentiment or "neutral"
    emoji = _SENTIMENT_EMOJI.get(sentiment_label, "🔵")
    sentiment_text = {
        "positive": "Позитивно",
        "neutral": "Нейтрально",
        "negative": "Негативно",
    }.get(sentiment_label, sentiment_label)

    title_part = f'<b><a href="{news.url}">{news.title}</a></b>'

    summary_part = ""
    if news.summary:
        summary_part = f"\n\n{news.summary}"

    hashtags_part = ""
    if news.hashtags:
        tags = " ".join(f"#{tag.lstrip('#')}" for tag in news.hashtags)
        hashtags_part = f"\n\n{tags}"

    sentiment_part = f"\n\n{emoji} {sentiment_text}"

    return f"{title_part}{summary_part}{hashtags_part}{sentiment_part}"


def _feedback_kb(news_id: int) -> InlineKeyboardMarkup:
    """Создать инлайн-клавиатуру с кнопками реакций.

    Args:
        news_id: ID новости в БД.

    Returns:
        InlineKeyboardMarkup.
    """
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="👍", callback_data=f"fb:like:{news_id}"),
        InlineKeyboardButton(text="👎", callback_data=f"fb:dislike:{news_id}"),
        InlineKeyboardButton(text="🔖 Сохранить", callback_data=f"fb:saved:{news_id}"),
    ]])


class NewsSender:
    """Отправитель новостей в Telegram.

    Args:
        bot: Экземпляр aiogram Bot.
    """

    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def send_news(self, chat_id: int, news: News) -> bool:
        """Отправить новость в чат и пометить как отправленную.

        Args:
            chat_id: Telegram chat ID получателя.
            news: Объект News для отправки.

        Returns:
            True — если отправка успешна, False — если возникла ошибка.
        """
        text = _format_message(news)
        kb = _feedback_kb(news.id)

        try:
            await self._bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=kb,
                link_preview_options=LinkPreviewOptions(is_disabled=False),
            )
        except TelegramAPIError as exc:
            logger.error(
                "Ошибка отправки новости id={} в chat_id={}: {}",
                news.id, chat_id, exc,
            )
            return False

        async for session in get_session():
            await mark_sent(session=session, news_id=news.id)

        logger.info("Новость id={} отправлена в chat_id={}", news.id, chat_id)
        return True

    async def send_digest(self, client_id: int, chat_id: int) -> None:
        """Отправить накопленные новости дайджестом.

        Режим отправки (compact / full) берётся из Settings клиента:
          - compact: одно сообщение со списком заголовков и ссылок.
          - full: каждая новость отдельным сообщением с паузой 2с.

        Args:
            client_id: Числовой ID клиента в БД.
            chat_id: Telegram chat ID получателя.
        """
        async for session in get_session():
            news_list = await get_unsent_news(session, client_id)
            if not news_list:
                logger.debug("Дайджест: нет новостей для client_id={}", client_id)
                return

            settings = await get_client_settings(session, client_id)
            digest_mode = settings.digest_mode if settings else "compact"

        # Сортируем по importance_score (по убыванию), берём топ-20
        news_list = sorted(
            news_list,
            key=lambda n: n.importance_score or 0,
            reverse=True,
        )[:20]

        logger.info(
            "Дайджест: {} новостей для client_id={}, режим={}",
            len(news_list), client_id, digest_mode,
        )

        if digest_mode == "compact":
            await self._send_compact_digest(chat_id, news_list)
        else:
            await self._send_full_digest(chat_id, news_list)

    async def _send_compact_digest(self, chat_id: int, news_list: list[News]) -> None:
        """Отправить компактный дайджест — один список заголовков со ссылками."""
        lines = [f"<b>Дайджест новостей ({len(news_list)})</b>\n"]
        for i, news in enumerate(news_list, 1):
            sentiment_emoji = _SENTIMENT_EMOJI.get(news.sentiment or "neutral", "🔵")
            lines.append(f'{i}. {sentiment_emoji} <a href="{news.url}">{news.title}</a>')

        text = "\n".join(lines)
        # Telegram ограничивает сообщение до 4096 символов
        if len(text) > 4096:
            text = text[:4090] + "\n..."

        try:
            await self._bot.send_message(
                chat_id=chat_id,
                text=text,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
        except TelegramAPIError as exc:
            logger.error("Ошибка отправки компактного дайджеста в chat_id={}: {}", chat_id, exc)
            return

        async for session in get_session():
            for news in news_list:
                await mark_sent(session=session, news_id=news.id)

        logger.info("Компактный дайджест отправлен в chat_id={}", chat_id)

    async def _send_full_digest(self, chat_id: int, news_list: list[News]) -> None:
        """Отправить каждую новость отдельным сообщением с паузой 2с."""
        sent_ids: list[int] = []

        for news in news_list:
            ok = await self.send_news(chat_id=chat_id, news=news)
            if ok:
                sent_ids.append(news.id)
            await asyncio.sleep(2)

        logger.info(
            "Полный дайджест: отправлено {}/{} новостей в chat_id={}",
            len(sent_ids), len(news_list), chat_id,
        )
