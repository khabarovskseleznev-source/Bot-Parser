"""
CRUD-операции с базой данных.

Все операции фильтрованы по client_id для мультиарендности.
"""

import hashlib
from datetime import datetime, timezone
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
    return result.scalars().first()


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
    importance_score: Optional[int] = None,
    title_ru: Optional[str] = None,
) -> None:
    """Записать результаты LLM-анализа в существующую новость.

    Args:
        session: Сессия SQLAlchemy.
        news_id: ID новости.
        summary: Краткое изложение.
        sentiment: Тональность (positive / neutral / negative).
        hashtags: Список хештегов.
        entities: Извлечённые сущности.
        importance_score: Оценка важности 1-10.
        title_ru: Перевод заголовка на русский.
    """
    news = await session.get(News, news_id)
    if news is None:
        logger.warning("update_news_analysis: новость id={} не найдена", news_id)
        return

    if title_ru is not None:
        news.title_ru = title_ru
    if summary is not None:
        news.summary = summary
    if sentiment is not None:
        news.sentiment = sentiment
    if hashtags is not None:
        news.hashtags = hashtags
    if entities is not None:
        news.entities = entities
    if importance_score is not None:
        news.importance_score = importance_score

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


_REACTION_SCORE_DELTA: dict[str, int] = {
    "like": 2,
    "dislike": -2,
    "saved": 3,
}


async def update_importance_by_feedback(
    session: AsyncSession,
    news_id: int,
    reaction: str,
) -> None:
    """Скорректировать importance_score новости по реакции пользователя.

    Дельта: like +2, saved +3, dislike -2. Значение зажато в диапазоне 1–10.
    Если score ещё не выставлен LLM, начинаем с нейтральной точки 5.

    Args:
        session: Сессия SQLAlchemy.
        news_id: ID новости.
        reaction: Реакция ('like', 'dislike', 'saved').
    """
    delta = _REACTION_SCORE_DELTA.get(reaction)
    if delta is None:
        return

    news = await session.get(News, news_id)
    if news is None:
        logger.warning("update_importance_by_feedback: новость id={} не найдена", news_id)
        return

    current = news.importance_score if news.importance_score is not None else 5
    news.importance_score = max(1, min(10, current + delta))
    await session.commit()
    logger.debug(
        "importance_score новости id={}: {} → {}",
        news_id, current, news.importance_score,
    )


async def get_feedback_stats(
    session: AsyncSession,
    client_id: int,
    days: int = 7,
) -> dict:
    """Собрать статистику реакций за последние N дней.

    Args:
        session: Сессия SQLAlchemy.
        client_id: ID клиента.
        days: Количество дней для выборки.

    Returns:
        Словарь: top_hashtags, sentiment_counts, total_liked, total_disliked, total_saved.
    """
    from collections import Counter
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    result = await session.execute(
        select(Feedback).where(
            Feedback.client_id == client_id,
            Feedback.created_at >= cutoff,
        )
    )
    feedbacks = list(result.scalars().all())

    total_liked = sum(1 for f in feedbacks if f.reaction == "like")
    total_disliked = sum(1 for f in feedbacks if f.reaction == "dislike")
    total_saved = sum(1 for f in feedbacks if f.reaction == "saved")

    liked_news_ids = [f.news_id for f in feedbacks if f.reaction in ("like", "saved")]

    hashtag_counter: Counter = Counter()
    sentiment_counts: dict[str, int] = {}

    if liked_news_ids:
        news_result = await session.execute(
            select(News).where(News.id.in_(liked_news_ids))
        )
        for news in news_result.scalars().all():
            if news.hashtags:
                for tag in news.hashtags:
                    hashtag_counter[tag] += 1
            if news.sentiment:
                sentiment_counts[news.sentiment] = sentiment_counts.get(news.sentiment, 0) + 1

    return {
        "top_hashtags": hashtag_counter.most_common(3),
        "sentiment_counts": sentiment_counts,
        "total_liked": total_liked,
        "total_disliked": total_disliked,
        "total_saved": total_saved,
    }


async def get_liked_news_ids(
    session: AsyncSession,
    client_id: int,
    limit: int = 200,
) -> set[int]:
    """Вернуть множество news_id, которые клиент лайкнул или сохранил.

    Args:
        session: Сессия SQLAlchemy.
        client_id: ID клиента.
        limit: Максимальное число записей (последние по времени).

    Returns:
        Множество news_id.
    """
    result = await session.execute(
        select(Feedback.news_id)
        .where(
            Feedback.client_id == client_id,
            Feedback.reaction.in_(["like", "saved"]),
        )
        .order_by(Feedback.created_at.desc())
        .limit(limit)
    )
    return {row[0] for row in result.all()}


async def get_low_priority_source_ids(
    session: AsyncSession,
    client_id: int,
    min_feedbacks: int = 5,
    dislike_threshold: float = 0.7,
) -> set[int]:
    """Вернуть source_id источников с преобладающими дизлайками.

    Источник считается низкоприоритетным, если:
    - получил не менее min_feedbacks реакций
    - доля дизлайков >= dislike_threshold

    Args:
        session: Сессия SQLAlchemy.
        client_id: ID клиента.
        min_feedbacks: Минимальное количество реакций для учёта.
        dislike_threshold: Порог доли дизлайков (0.0 - 1.0).

    Returns:
        Множество source_id низкоприоритетных источников.
    """
    from collections import defaultdict

    # Получаем все реакции + source_id через join
    result = await session.execute(
        select(Feedback.reaction, News.source_id)
        .join(News, Feedback.news_id == News.id)
        .where(Feedback.client_id == client_id)
    )
    rows = result.all()

    # Считаем реакции по источникам
    counts: dict[int, dict[str, int]] = defaultdict(lambda: {"like": 0, "dislike": 0, "saved": 0})
    for reaction, source_id in rows:
        if reaction in counts[source_id]:
            counts[source_id][reaction] += 1

    low_priority: set[int] = set()
    for source_id, c in counts.items():
        total = c["like"] + c["dislike"] + c["saved"]
        if total >= min_feedbacks and total > 0:
            dislike_ratio = c["dislike"] / total
            if dislike_ratio >= dislike_threshold:
                low_priority.add(source_id)
                logger.info(
                    "Источник source_id={} помечен низкоприоритетным: дизлайков {:.0%} ({}/{})",
                    source_id, dislike_ratio, c["dislike"], total,
                )

    return low_priority


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


async def get_client_by_chat_id(
    session: AsyncSession,
    chat_id: int,
) -> Optional[Client]:
    """Найти клиента по Telegram chat ID.

    Args:
        session: Сессия SQLAlchemy.
        chat_id: Telegram chat ID.

    Returns:
        Объект Client или None.
    """
    result = await session.execute(
        select(Client).where(Client.telegram_chat_id == chat_id)
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

    Поиск ведётся по client_str_id (уникальный строковый ID из конфига),
    а не по telegram_chat_id — это позволяет нескольким клиентам
    иметь одинаковый chat_id (например, бот тестируется в одном чате).

    Args:
        session: Сессия SQLAlchemy.
        client_str_id: Строковый ID клиента из конфига (уникален).
        name: Название клиента.
        telegram_chat_id: Telegram chat ID клиента.
        config_path: Путь к файлу конфига.

    Returns:
        Объект Client.
    """
    result = await session.execute(
        select(Client).where(Client.client_str_id == client_str_id)
    )
    client = result.scalar_one_or_none()
    if client is not None:
        # Обновляем chat_id на случай его изменения в конфиге
        if client.telegram_chat_id != telegram_chat_id:
            client.telegram_chat_id = telegram_chat_id
            await session.commit()
        return client

    client = Client(
        client_str_id=client_str_id,
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


async def upsert_client_settings(
    session: AsyncSession,
    client_id: int,
    keywords: list[str],
    exclude_keywords: list[str],
    frequency: str,
    analysis_flags: dict,
) -> Settings:
    """Создать или обновить настройки клиента из config.json.

    Args:
        session: Сессия SQLAlchemy.
        client_id: ID клиента.
        keywords: Список ключевых слов для фильтрации.
        exclude_keywords: Список стоп-слов.
        frequency: Частота доставки ("instant", "hourly", "daily").
        analysis_flags: Словарь флагов анализа (summary, sentiment и т.д.).

    Returns:
        Объект Settings.
    """
    result = await session.execute(
        select(Settings).where(Settings.client_id == client_id)
    )
    s = result.scalar_one_or_none()
    if s is None:
        s = Settings(client_id=client_id)
        session.add(s)
    s.keywords = keywords
    s.exclude_keywords = exclude_keywords
    s.frequency = frequency
    s.analysis_flags = analysis_flags
    await session.commit()
    logger.info("Settings upserted: client_id={}, keywords={}", client_id, keywords)
    return s


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
