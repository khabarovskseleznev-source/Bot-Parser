"""
CRUD-операции с базой данных.

Все операции фильтрованы по client_id для мультиарендности.
"""

import hashlib
from datetime import datetime
from typing import Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Client, Feedback, News, Settings, Source


def compute_hash(text: str) -> str:
    """Вычислить SHA-256 хеш текста.

    Args:
        text: Исходный текст (обычно title + content).

    Returns:
        Hex-строка SHA-256.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def get_news_by_hash(
    session: AsyncSession,
    client_id: int,
    content_hash: str,
) -> Optional[News]:
    """Найти новость по хешу контента.

    Args:
        session: Сессия SQLAlchemy.
        client_id: ID клиента.
        content_hash: SHA-256 хеш.

    Returns:
        Объект News или None.
    """
    result = await session.execute(
        select(News).where(News.client_id == client_id, News.hash == content_hash)
    )
    return result.scalar_one_or_none()


async def save_news(
    session: AsyncSession,
    client_id: int,
    source_id: int,
    url: str,
    title: str,
    content: str,
    published_at: Optional[datetime] = None,
    is_duplicate: bool = False,
) -> News:
    """Сохранить новость в базу данных.

    Args:
        session: Сессия SQLAlchemy.
        client_id: ID клиента.
        source_id: ID источника.
        url: URL новости.
        title: Заголовок.
        content: Полный текст.
        published_at: Дата публикации (опционально).
        is_duplicate: Флаг дубликата.

    Returns:
        Сохранённый объект News.
    """
    content_hash = compute_hash(title + content)
    news = News(
        client_id=client_id,
        source_id=source_id,
        url=url,
        title=title,
        content=content,
        published_at=published_at,
        hash=content_hash,
        is_duplicate=is_duplicate,
    )
    session.add(news)
    await session.commit()
    await session.refresh(news)
    logger.debug("Новость сохранена: id={}, client={}, hash={}", news.id, client_id, content_hash[:8])
    return news


async def update_news_analysis(
    session: AsyncSession,
    news_id: int,
    summary: Optional[str] = None,
    sentiment: Optional[str] = None,
    hashtags: Optional[list[str]] = None,
    entities: Optional[dict] = None,
) -> None:
    """Записать результаты LLM-анализа в существующую новость.

    Args:
        session: Сессия SQLAlchemy.
        news_id: ID новости.
        summary: Краткое изложение.
        sentiment: Тональность (positive / neutral / negative).
        hashtags: Список хештегов.
        entities: Извлечённые сущности.
    """
    news = await session.get(News, news_id)
    if news is None:
        logger.warning("update_news_analysis: новость id={} не найдена", news_id)
        return

    if summary is not None:
        news.summary = summary
    if sentiment is not None:
        news.sentiment = sentiment
    if hashtags is not None:
        news.hashtags = hashtags
    if entities is not None:
        news.entities = entities

    await session.commit()
    logger.debug("Анализ записан для новости id={}", news_id)


async def mark_sent(session: AsyncSession, news_id: int) -> None:
    """Отметить новость как отправленную пользователю.

    Args:
        session: Сессия SQLAlchemy.
        news_id: ID новости.
    """
    news = await session.get(News, news_id)
    if news is None:
        logger.warning("mark_sent: новость id={} не найдена", news_id)
        return
    news.sent_to_user = True
    await session.commit()
    logger.debug("Новость id={} помечена как отправленная", news_id)


async def save_feedback(
    session: AsyncSession,
    client_id: int,
    news_id: int,
    reaction: str,
) -> Feedback:
    """Сохранить реакцию пользователя на новость.

    Args:
        session: Сессия SQLAlchemy.
        client_id: ID клиента.
        news_id: ID новости.
        reaction: Реакция ('like', 'dislike', 'saved').

    Returns:
        Сохранённый объект Feedback.
    """
    feedback = Feedback(client_id=client_id, news_id=news_id, reaction=reaction)
    session.add(feedback)
    await session.commit()
    await session.refresh(feedback)
    logger.debug("Фидбек сохранён: client={}, news={}, reaction={}", client_id, news_id, reaction)
    return feedback


async def get_source_by_url(
    session: AsyncSession,
    client_id: int,
    url: str,
) -> Optional[Source]:
    """Найти источник по URL и client_id.

    Args:
        session: Сессия SQLAlchemy.
        client_id: ID клиента.
        url: URL источника.

    Returns:
        Объект Source или None.
    """
    result = await session.execute(
        select(Source).where(Source.client_id == client_id, Source.url == url)
    )
    return result.scalar_one_or_none()


async def get_or_create_client(
    session: AsyncSession,
    client_str_id: str,
    name: str,
    telegram_chat_id: int,
    config_path: str = "",
) -> Client:
    """Вернуть существующего клиента или создать нового.

    Args:
        session: Сессия SQLAlchemy.
        client_str_id: Строковый ID клиента из конфига.
        name: Название клиента.
        telegram_chat_id: Telegram chat ID клиента.
        config_path: Путь к файлу конфига.

    Returns:
        Объект Client.
    """
    result = await session.execute(
        select(Client).where(Client.telegram_chat_id == telegram_chat_id)
    )
    client = result.scalar_one_or_none()
    if client is not None:
        return client

    client = Client(
        name=name,
        telegram_chat_id=telegram_chat_id,
        config_path=config_path,
    )
    session.add(client)
    await session.commit()
    await session.refresh(client)
    logger.info("Клиент создан: str_id={}, db_id={}", client_str_id, client.id)
    return client


async def get_client_settings(
    session: AsyncSession,
    client_id: int,
) -> Optional[Settings]:
    """Получить настройки клиента.

    Args:
        session: Сессия SQLAlchemy.
        client_id: ID клиента.

    Returns:
        Объект Settings или None.
    """
    result = await session.execute(
        select(Settings).where(Settings.client_id == client_id)
    )
    return result.scalar_one_or_none()


async def get_unsent_news(
    session: AsyncSession,
    client_id: int,
) -> list[News]:
    """Получить все неотправленные, не-дубликаты, не-отфильтрованные новости клиента.

    Args:
        session: Сессия SQLAlchemy.
        client_id: ID клиента.

    Returns:
        Список объектов News.
    """
    result = await session.execute(
        select(News).where(
            News.client_id == client_id,
            News.sent_to_user.is_(False),
            News.is_duplicate.is_(False),
            News.keyword_filtered.is_(False),
        )
    )
    return list(result.scalars().all())


async def get_or_create_source(
    session: AsyncSession,
    client_id: int,
    url: str,
    name: str,
    source_type: str,
    fetch_interval: int = 60,
) -> Source:
    """Вернуть существующий источник или создать новый.

    Args:
        session: Сессия SQLAlchemy.
        client_id: ID клиента.
        url: URL источника.
        name: Название.
        source_type: Тип ('rss', 'telegram', 'website', 'social').
        fetch_interval: Интервал парсинга в минутах.

    Returns:
        Объект Source.
    """
    source = await get_source_by_url(session, client_id, url)
    if source is not None:
        return source

    source = Source(
        client_id=client_id,
        url=url,
        name=name,
        type=source_type,
        fetch_interval=fetch_interval,
    )
    session.add(source)
    await session.commit()
    await session.refresh(source)
    logger.info("Источник создан: client={}, name={}, type={}", client_id, name, source_type)
    return source
