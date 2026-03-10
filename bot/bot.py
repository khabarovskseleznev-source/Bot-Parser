"""
Инициализация Telegram-бота (aiogram 3.x).

Создаёт Bot и Dispatcher, регистрирует роутеры handlers.
"""

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from loguru import logger

from bot.handlers import feedback, settings, start, stats


def create_bot(token: str) -> Bot:
    """Создать экземпляр Bot с HTML-разметкой по умолчанию.

    Args:
        token: Токен бота из .env.

    Returns:
        Объект Bot.
    """
    return Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    """Создать Dispatcher и зарегистрировать все роутеры.

    Returns:
        Настроенный Dispatcher.
    """
    dp = Dispatcher()

    dp.include_router(start.router)
    dp.include_router(settings.router)
    dp.include_router(feedback.router)
    dp.include_router(stats.router)

    logger.info("Роутеры зарегистрированы: start, settings, feedback, stats")
    return dp
