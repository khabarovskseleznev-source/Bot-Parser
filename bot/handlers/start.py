"""
Обработчик команды /start.

Приветствует пользователя и регистрирует клиента в БД (get_or_create_client).
"""

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from loguru import logger
from sqlalchemy import select

from database.crud import get_or_create_client
from database.db import get_session
from database.models import Settings

router = Router(name="start")

_WELCOME = (
    "<b>Добро пожаловать в IntelBot!</b>\n\n"
    "Я собираю новости из ваших источников, анализирую их с помощью ИИ "
    "и отправляю краткие саммари с тональностью и хештегами.\n\n"
    "Команды:\n"
    "/settings — настройки ключевых слов и частоты доставки\n"
    "/stats — статистика реакций за 7 дней\n"
    "/start — это сообщение"
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Обработать /start: зарегистрировать клиента и отправить приветствие.

    Args:
        message: Входящее сообщение Telegram.
    """
    chat_id = message.chat.id
    user_name = message.from_user.full_name if message.from_user else str(chat_id)

    async for session in get_session():
        # Зарегистрировать клиента (идемпотентно)
        client = await get_or_create_client(
            session=session,
            client_str_id=str(chat_id),
            name=user_name,
            telegram_chat_id=chat_id,
        )

        # Создать настройки по умолчанию, если их ещё нет
        result = await session.execute(
            select(Settings).where(Settings.client_id == client.id)
        )
        if result.scalar_one_or_none() is None:
            session.add(Settings(client_id=client.id))
            await session.commit()
            logger.info("Настройки по умолчанию созданы: client_id={}", client.id)

    logger.info("/start от chat_id={} ({})", chat_id, user_name)
    await message.answer(_WELCOME)
