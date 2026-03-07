"""
Обработчик инлайн-кнопок обратной связи.

Кнопки прикрепляются к каждому сообщению с новостью через bot/sender.py.
Callback-данные формата: fb:<reaction>:<news_id>
  reaction: like | dislike | saved
"""

from aiogram import F, Router
from aiogram.types import CallbackQuery
from loguru import logger
from sqlalchemy import select

from database.crud import save_feedback
from database.db import get_session
from database.models import Client

router = Router(name="feedback")

_REACTION_LABELS = {
    "like": "Понравилось",
    "dislike": "Не интересно",
    "saved": "Сохранено",
}


@router.callback_query(F.data.startswith("fb:"))
async def cb_feedback(callback: CallbackQuery) -> None:
    """Сохранить реакцию пользователя на новость.

    Args:
        callback: Callback-запрос с данными fb:<reaction>:<news_id>.
    """
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Некорректные данные.", show_alert=True)
        return

    _, reaction, news_id_str = parts
    if reaction not in _REACTION_LABELS:
        await callback.answer("Неизвестная реакция.", show_alert=True)
        return

    try:
        news_id = int(news_id_str)
    except ValueError:
        await callback.answer("Некорректный ID новости.", show_alert=True)
        return

    chat_id = callback.message.chat.id

    async for session in get_session():
        result = await session.execute(
            select(Client).where(Client.telegram_chat_id == chat_id)
        )
        client = result.scalar_one_or_none()
        if client is None:
            await callback.answer("Сначала отправьте /start.", show_alert=True)
            return

        await save_feedback(
            session=session,
            client_id=client.id,
            news_id=news_id,
            reaction=reaction,
        )
        logger.info(
            "Фидбек: client_id={}, news_id={}, reaction={}",
            client.id, news_id, reaction,
        )

    label = _REACTION_LABELS[reaction]
    await callback.answer(label)
