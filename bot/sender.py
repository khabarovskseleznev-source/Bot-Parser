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
import html

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

    display_title = html.escape(news.title_ru if news.title_ru else news.title)
    safe_url = html.escape(news.url, quote=True)
    title_part = f'<b><a href="{safe_url}">{display_title}</a></b>'

    summary_part = ""
    if news.summary:
        summary_part = f"\n\n{html.escape(news.summary)}"

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
        # Извлекаем данные из сессии в простые структуры, чтобы не зависеть от ORM-состояния
        digest_mode = "compact"
        news_data: list[dict] = []

        async for session in get_session():
            news_list = await get_unsent_news(session, client_id)
            if not news_list:
                logger.debug("Дайджест: нет новостей для client_id={}", client_id)
                return

            settings_obj = await get_client_settings(session, client_id)
            digest_mode = settings_obj.digest_mode if settings_obj else "compact"

            # Сортируем по importance_score (по убыванию), берём топ-20
            news_list = sorted(
                news_list,
                key=lambda n: n.importance_score or 0,
                reverse=True,
            )[:20]

            # Собираем данные в словари, пока объекты ещё привязаны к сессии
            for news in news_list:
                news_data.append({
                    "id": news.id,
                    "url": news.url,
                    "title": news.title,
                    "title_ru": news.title_ru,
                    "summary": news.summary,
                    "sentiment": news.sentiment,
                    "hashtags": news.hashtags,
                    "importance_score": news.importance_score,
                })

        if not news_data:
            return

        logger.info(
            "Дайджест: {} новостей для client_id={}, режим={}",
            len(news_data), client_id, digest_mode,
        )

        if digest_mode == "compact":
            await self._send_compact_digest(chat_id, news_data)
        else:
            await self._send_full_digest(chat_id, news_data)

    async def _send_compact_digest(self, chat_id: int, news_data: list[dict]) -> None:
        """Отправить компактный дайджест — один список заголовков со ссылками."""
        lines = [f"<b>Дайджест новостей ({len(news_data)})</b>\n"]
        for i, nd in enumerate(news_data, 1):
            sentiment_emoji = _SENTIMENT_EMOJI.get(nd.get("sentiment") or "neutral", "🔵")
            display_title = html.escape(nd.get("title_ru") or nd["title"])
            safe_url = html.escape(nd["url"], quote=True)
            lines.append(f'{i}. {sentiment_emoji} <a href="{safe_url}">{display_title}</a>')

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
            for nd in news_data:
                await mark_sent(session=session, news_id=nd["id"])

        logger.info("Компактный дайджест отправлен в chat_id={}", chat_id)

    async def _send_full_digest(self, chat_id: int, news_data: list[dict]) -> None:
        """Отправить каждую новость отдельным сообщением с паузой 2с."""
        sent_count = 0

        for nd in news_data:
            text = self._format_dict_message(nd)
            kb = _feedback_kb(nd["id"])
            try:
                await self._bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=kb,
                    link_preview_options=LinkPreviewOptions(is_disabled=False),
                )
            except TelegramAPIError as exc:
                logger.error("Ошибка отправки новости id={} в chat_id={}: {}", nd["id"], chat_id, exc)
                await asyncio.sleep(2)
                continue

            async for session in get_session():
                await mark_sent(session=session, news_id=nd["id"])

            sent_count += 1
            await asyncio.sleep(2)

        logger.info(
            "Полный дайджест: отправлено {}/{} новостей в chat_id={}",
            sent_count, len(news_data), chat_id,
        )

    @staticmethod
    def _format_dict_message(nd: dict) -> str:
        """Сформировать HTML-текст из словаря данных новости."""
        sentiment_label = nd.get("sentiment") or "neutral"
        emoji = _SENTIMENT_EMOJI.get(sentiment_label, "🔵")
        sentiment_text = {
            "positive": "Позитивно",
            "neutral": "Нейтрально",
            "negative": "Негативно",
        }.get(sentiment_label, sentiment_label)

        display_title = html.escape(nd.get("title_ru") or nd["title"])
        safe_url = html.escape(nd["url"], quote=True)
        title_part = f'<b><a href="{safe_url}">{display_title}</a></b>'

        summary_part = ""
        if nd.get("summary"):
            summary_part = f"\n\n{html.escape(nd['summary'])}"

        hashtags_part = ""
        if nd.get("hashtags"):
            tags = " ".join(f"#{tag.lstrip('#')}" for tag in nd["hashtags"])
            hashtags_part = f"\n{tags}"

        sentiment_part = f"\n\n{emoji} {sentiment_text}"

        return f"{title_part}{summary_part}{hashtags_part}{sentiment_part}"
