"""
Обработчик команды /stats.

Показывает статистику реакций за последние 7 дней:
- Топ-3 темы (хештеги лайкнутых новостей)
- Процентное соотношение тональностей
- Общее количество реакций
"""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from loguru import logger

from database.crud import get_client_by_chat_id, get_feedback_stats
from database.db import get_session

router = Router(name="stats")

_SENTIMENT_LABELS = {
    "positive": "позитивные",
    "neutral": "нейтральные",
    "negative": "негативные",
}


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    """Показать статистику реакций пользователя за 7 дней.

    Args:
        message: Входящее сообщение Telegram.
    """
    chat_id = message.chat.id

    async for session in get_session():
        client = await get_client_by_chat_id(session, chat_id)
        if client is None:
            await message.answer("Сначала отправьте /start.")
            return

        stats = await get_feedback_stats(session=session, client_id=client.id, days=7)

    total = stats["total_liked"] + stats["total_disliked"] + stats["total_saved"]
    logger.info("/stats от client_id={}, реакций за 7 дней: {}", client.id, total)

    if total == 0:
        await message.answer(
            "<b>Статистика за 7 дней</b>\n\nРеакций пока нет. "
            "Ставьте 👍/👎/🔖 под новостями — я буду учиться!"
        )
        return

    lines = ["<b>Статистика за 7 дней</b>\n"]

    # Реакции
    lines.append(
        f"👍 Понравилось: {stats['total_liked']}  "
        f"👎 Не интересно: {stats['total_disliked']}  "
        f"🔖 Сохранено: {stats['total_saved']}"
    )

    # Топ-3 темы
    if stats["top_hashtags"]:
        lines.append("\n<b>Топ темы:</b>")
        for i, (tag, count) in enumerate(stats["top_hashtags"], 1):
            lines.append(f"{i}. {tag} — {count} {'раз' if count == 1 else 'раза'}")
    else:
        lines.append("\nТоп тем: нет данных (хештеги ещё не накоплены)")

    # Тональности
    sentiment_counts = stats["sentiment_counts"]
    if sentiment_counts:
        total_sent = sum(sentiment_counts.values())
        lines.append("\n<b>Тональность лайкнутых:</b>")
        for key, label in _SENTIMENT_LABELS.items():
            count = sentiment_counts.get(key, 0)
            pct = round(count / total_sent * 100) if total_sent else 0
            if count:
                lines.append(f"• {label.capitalize()}: {pct}%")

    await message.answer("\n".join(lines))
