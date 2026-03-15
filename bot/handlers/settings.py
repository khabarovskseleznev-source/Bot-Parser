"""
Обработчик команды /settings.

FSM-диалог для управления:
  - keywords (ключевые слова фильтра)
  - frequency (частота доставки: instant / hourly / daily)
  - digest_mode (формат дайджеста: compact / full)
"""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from database.crud import get_client_by_chat_id
from database.db import get_session
from database.models import Settings

router = Router(name="settings")

_FREQ_LABELS = {
    "instant": "Мгновенно",
    "hourly": "Каждый час",
    "daily": "Раз в день",
}

_DIGEST_LABELS = {
    "compact": "Компактный",
    "full": "Полный",
}


class SettingsForm(StatesGroup):
    waiting_keywords = State()


# ─── Клавиатуры ──────────────────────────────────────────────────────────────

def _main_kb(freq: str = "instant", digest_mode: str = "compact") -> InlineKeyboardMarkup:
    def freq_btn(label: str, value: str) -> InlineKeyboardButton:
        mark = "✓ " if freq == value else ""
        return InlineKeyboardButton(text=f"{mark}{label}", callback_data=f"cfg:freq:{value}")

    def digest_btn(label: str, value: str) -> InlineKeyboardButton:
        mark = "✓ " if digest_mode == value else ""
        return InlineKeyboardButton(text=f"{mark}{label}", callback_data=f"cfg:digest:{value}")

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Ключевые слова", callback_data="cfg:keywords")],
        [
            freq_btn("Мгновенно", "instant"),
            freq_btn("Каждый час", "hourly"),
            freq_btn("Раз в день", "daily"),
        ],
        [
            digest_btn("Компактный дайджест", "compact"),
            digest_btn("Полный дайджест", "full"),
        ],
    ])


# ─── Helpers ─────────────────────────────────────────────────────────────────

async def _get_or_create_settings(chat_id: int) -> tuple[int, Settings]:
    """Вернуть (client_db_id, Settings) по telegram chat_id.

    Args:
        chat_id: Telegram chat ID.

    Returns:
        Кортеж (client.id, settings).

    Raises:
        ValueError: Клиент не найден в БД.
    """
    async for session in get_session():
        client = await get_client_by_chat_id(session, chat_id)
        if client is None:
            raise ValueError(f"Клиент не найден: chat_id={chat_id}")

        result = await session.execute(
            select(Settings).where(Settings.client_id == client.id)
        )
        s = result.scalar_one_or_none()
        if s is None:
            s = Settings(client_id=client.id)
            session.add(s)
            await session.commit()
            await session.refresh(s)

        return client.id, s

    raise RuntimeError("Unreachable")


def _settings_text(s: Settings) -> str:
    kw = ", ".join(s.keywords) if s.keywords else "<i>не заданы</i>"
    freq = _FREQ_LABELS.get(s.frequency, s.frequency)
    digest = _DIGEST_LABELS.get(s.digest_mode, s.digest_mode)
    return (
        f"<b>Настройки</b>\n\n"
        f"Ключевые слова: {kw}\n"
        f"Частота доставки: {freq}\n"
        f"Формат дайджеста: {digest}"
    )


# ─── Handlers ─────────────────────────────────────────────────────────────────

@router.message(Command("settings"))
async def cmd_settings(message: Message) -> None:
    """Показать текущие настройки с кнопками управления."""
    try:
        _, s = await _get_or_create_settings(message.chat.id)
    except ValueError:
        await message.answer("Сначала отправьте /start для регистрации.")
        return

    await message.answer(_settings_text(s), reply_markup=_main_kb(s.frequency, s.digest_mode))


@router.callback_query(F.data == "cfg:keywords")
async def cb_keywords(callback: CallbackQuery, state: FSMContext) -> None:
    """Запросить новые ключевые слова."""
    await state.set_state(SettingsForm.waiting_keywords)
    await callback.message.answer(
        "Введите ключевые слова через запятую.\n"
        "Пример: <code>тендер, строительство, цемент</code>\n\n"
        "Отправьте <code>-</code> чтобы очистить список."
    )
    await callback.answer()


@router.message(SettingsForm.waiting_keywords)
async def process_keywords(message: Message, state: FSMContext) -> None:
    """Сохранить новые ключевые слова."""
    await state.clear()
    text = (message.text or "").strip()

    if text == "-":
        keywords: list[str] = []
    else:
        keywords = [kw.strip() for kw in text.split(",") if kw.strip()]

    async for session in get_session():
        client = await get_client_by_chat_id(session, message.chat.id)
        if client is None:
            await message.answer("Сначала отправьте /start.")
            return

        result = await session.execute(
            select(Settings).where(Settings.client_id == client.id)
        )
        s = result.scalar_one_or_none()
        if s is None:
            s = Settings(client_id=client.id, keywords=keywords)
            session.add(s)
        else:
            s.keywords = keywords
            flag_modified(s, "keywords")

        await session.commit()
        logger.info("Обновлены ключевые слова: client_id={}, keywords={}", client.id, keywords)

    kw_text = ", ".join(keywords) if keywords else "<i>список очищен</i>"
    await message.answer(f"Ключевые слова сохранены: {kw_text}")


@router.callback_query(F.data.startswith("cfg:freq:"))
async def cb_frequency(callback: CallbackQuery) -> None:
    """Установить частоту доставки новостей."""
    freq = callback.data.split(":")[-1]  # instant / hourly / daily
    if freq not in _FREQ_LABELS:
        await callback.answer("Неизвестная частота.", show_alert=True)
        return

    async for session in get_session():
        client = await get_client_by_chat_id(session, callback.message.chat.id)
        if client is None:
            await callback.answer("Сначала отправьте /start.", show_alert=True)
            return

        result = await session.execute(
            select(Settings).where(Settings.client_id == client.id)
        )
        s = result.scalar_one_or_none()
        if s is None:
            s = Settings(client_id=client.id, frequency=freq)
            session.add(s)
        else:
            s.frequency = freq

        await session.commit()
        logger.info("Обновлена частота: client_id={}, frequency={}", client.id, freq)

    label = _FREQ_LABELS[freq]
    await callback.answer(f"Частота: {label}", show_alert=False)

    # Перезагружаем актуальные настройки для отображения
    try:
        _, s = await _get_or_create_settings(callback.message.chat.id)
        await callback.message.edit_text(_settings_text(s), reply_markup=_main_kb(s.frequency, s.digest_mode))
    except Exception:
        pass  # если edit не удался — ничего страшного, данные уже сохранены


@router.callback_query(F.data.startswith("cfg:digest:"))
async def cb_digest_mode(callback: CallbackQuery) -> None:
    """Установить формат дайджеста (compact / full)."""
    mode = callback.data.split(":")[-1]
    if mode not in _DIGEST_LABELS:
        await callback.answer("Неизвестный режим.", show_alert=True)
        return

    async for session in get_session():
        client = await get_client_by_chat_id(session, callback.message.chat.id)
        if client is None:
            await callback.answer("Сначала отправьте /start.", show_alert=True)
            return

        result = await session.execute(
            select(Settings).where(Settings.client_id == client.id)
        )
        s = result.scalar_one_or_none()
        if s is None:
            s = Settings(client_id=client.id, digest_mode=mode)
            session.add(s)
        else:
            s.digest_mode = mode

        await session.commit()
        logger.info("Обновлён digest_mode: client_id={}, digest_mode={}", client.id, mode)

    label = _DIGEST_LABELS[mode]
    await callback.answer(f"Формат дайджеста: {label}", show_alert=False)

    try:
        _, s = await _get_or_create_settings(callback.message.chat.id)
        await callback.message.edit_text(_settings_text(s), reply_markup=_main_kb(s.frequency, s.digest_mode))
    except Exception:
        pass
