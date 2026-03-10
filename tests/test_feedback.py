"""
Тесты feedback-обучения: update_importance_by_feedback, get_feedback_stats,
get_liked_news_ids, get_low_priority_source_ids, update_news_analysis.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from database.crud import (
    get_feedback_stats,
    get_liked_news_ids,
    get_low_priority_source_ids,
    get_or_create_client,
    get_or_create_source,
    save_feedback,
    save_news,
    update_importance_by_feedback,
    update_news_analysis,
)
from database.models import News


# ---------------------------------------------------------------------------
# Вспомогательные фикстуры / хелперы
# ---------------------------------------------------------------------------

async def _make_client(session: AsyncSession, str_id: str, chat_id: int):
    return await get_or_create_client(
        session=session,
        client_str_id=str_id,
        name=str_id,
        telegram_chat_id=chat_id,
    )


async def _make_source(session: AsyncSession, client_id: int, url: str = "https://x.com/rss"):
    return await get_or_create_source(
        session=session,
        client_id=client_id,
        url=url,
        name="src",
        source_type="rss",
    )


async def _make_news(session: AsyncSession, client_id: int, source_id: int, n: int = 1) -> News:
    return await save_news(
        session=session,
        client_id=client_id,
        source_id=source_id,
        url=f"https://x.com/news/{n}",
        title=f"Заголовок {n}",
        content=f"Контент {n}",
    )


# ---------------------------------------------------------------------------
# update_importance_by_feedback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_like_increases_score(db_session: AsyncSession) -> None:
    client = await _make_client(db_session, "fb1", 1_001)
    source = await _make_source(db_session, client.id)
    news = await _make_news(db_session, client.id, source.id)

    # Начальный score не задан → стартует с 5
    await update_importance_by_feedback(db_session, news.id, "like")
    await db_session.refresh(news)
    assert news.importance_score == 7  # 5 + 2


@pytest.mark.asyncio
async def test_saved_increases_score_by_3(db_session: AsyncSession) -> None:
    client = await _make_client(db_session, "fb2", 1_002)
    source = await _make_source(db_session, client.id)
    news = await _make_news(db_session, client.id, source.id)

    await update_importance_by_feedback(db_session, news.id, "saved")
    await db_session.refresh(news)
    assert news.importance_score == 8  # 5 + 3


@pytest.mark.asyncio
async def test_dislike_decreases_score(db_session: AsyncSession) -> None:
    client = await _make_client(db_session, "fb3", 1_003)
    source = await _make_source(db_session, client.id)
    news = await _make_news(db_session, client.id, source.id)

    await update_importance_by_feedback(db_session, news.id, "dislike")
    await db_session.refresh(news)
    assert news.importance_score == 3  # 5 - 2


@pytest.mark.asyncio
async def test_score_clamps_at_10(db_session: AsyncSession) -> None:
    """Многократные like не превышают 10."""
    client = await _make_client(db_session, "fb4", 1_004)
    source = await _make_source(db_session, client.id)
    news = await _make_news(db_session, client.id, source.id)

    for _ in range(5):
        await update_importance_by_feedback(db_session, news.id, "like")
    await db_session.refresh(news)
    assert news.importance_score == 10


@pytest.mark.asyncio
async def test_score_clamps_at_1(db_session: AsyncSession) -> None:
    """Многократные dislike не опускаются ниже 1."""
    client = await _make_client(db_session, "fb5", 1_005)
    source = await _make_source(db_session, client.id)
    news = await _make_news(db_session, client.id, source.id)

    for _ in range(5):
        await update_importance_by_feedback(db_session, news.id, "dislike")
    await db_session.refresh(news)
    assert news.importance_score == 1


@pytest.mark.asyncio
async def test_existing_score_is_adjusted(db_session: AsyncSession) -> None:
    """Если LLM уже выставил score, корректируем от него, не от 5."""
    client = await _make_client(db_session, "fb6", 1_006)
    source = await _make_source(db_session, client.id)
    news = await _make_news(db_session, client.id, source.id)

    # LLM выставил 9
    await update_news_analysis(db_session, news.id, importance_score=9)
    await update_importance_by_feedback(db_session, news.id, "like")
    await db_session.refresh(news)
    assert news.importance_score == 10  # 9 + 2, clamped to 10 — actually min(10, 11) = 10


@pytest.mark.asyncio
async def test_unknown_reaction_is_ignored(db_session: AsyncSession) -> None:
    """Неизвестная реакция не меняет score."""
    client = await _make_client(db_session, "fb7", 1_007)
    source = await _make_source(db_session, client.id)
    news = await _make_news(db_session, client.id, source.id)

    await update_importance_by_feedback(db_session, news.id, "unknown_reaction")
    await db_session.refresh(news)
    # score не изменился — остался None
    assert news.importance_score is None


@pytest.mark.asyncio
async def test_nonexistent_news_does_not_raise(db_session: AsyncSession) -> None:
    """Обращение к несуществующей новости не бросает исключение."""
    await update_importance_by_feedback(db_session, 99999, "like")


# ---------------------------------------------------------------------------
# update_news_analysis
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_news_analysis_sets_fields(db_session: AsyncSession) -> None:
    client = await _make_client(db_session, "ua1", 2_001)
    source = await _make_source(db_session, client.id)
    news = await _make_news(db_session, client.id, source.id)

    await update_news_analysis(
        db_session,
        news.id,
        summary="Краткое изложение",
        sentiment="positive",
        hashtags=["AI", "LLM"],
        importance_score=8,
    )
    await db_session.refresh(news)

    assert news.summary == "Краткое изложение"
    assert news.sentiment == "positive"
    assert news.hashtags == ["AI", "LLM"]
    assert news.importance_score == 8


@pytest.mark.asyncio
async def test_update_news_analysis_partial_update(db_session: AsyncSession) -> None:
    """Обновление только части полей не затирает остальные."""
    client = await _make_client(db_session, "ua2", 2_002)
    source = await _make_source(db_session, client.id)
    news = await _make_news(db_session, client.id, source.id)

    await update_news_analysis(db_session, news.id, summary="Первый summary", sentiment="neutral")
    await update_news_analysis(db_session, news.id, importance_score=7)
    await db_session.refresh(news)

    assert news.summary == "Первый summary"
    assert news.sentiment == "neutral"
    assert news.importance_score == 7


@pytest.mark.asyncio
async def test_update_news_analysis_nonexistent_does_not_raise(db_session: AsyncSession) -> None:
    await update_news_analysis(db_session, 99999, summary="ghost")


# ---------------------------------------------------------------------------
# get_liked_news_ids
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_liked_news_ids_includes_like_and_saved(db_session: AsyncSession) -> None:
    client = await _make_client(db_session, "ln1", 3_001)
    source = await _make_source(db_session, client.id)
    n1 = await _make_news(db_session, client.id, source.id, 1)
    n2 = await _make_news(db_session, client.id, source.id, 2)
    n3 = await _make_news(db_session, client.id, source.id, 3)

    await save_feedback(db_session, client.id, n1.id, "like")
    await save_feedback(db_session, client.id, n2.id, "saved")
    await save_feedback(db_session, client.id, n3.id, "dislike")

    ids = await get_liked_news_ids(db_session, client.id)
    assert n1.id in ids
    assert n2.id in ids
    assert n3.id not in ids


@pytest.mark.asyncio
async def test_liked_news_ids_empty_when_no_feedback(db_session: AsyncSession) -> None:
    client = await _make_client(db_session, "ln2", 3_002)
    ids = await get_liked_news_ids(db_session, client.id)
    assert ids == set()


@pytest.mark.asyncio
async def test_liked_news_ids_respects_client_isolation(db_session: AsyncSession) -> None:
    """Лайки клиента A не попадают к клиенту B."""
    ca = await _make_client(db_session, "ln3a", 3_003)
    cb = await _make_client(db_session, "ln3b", 3_004)
    src_a = await _make_source(db_session, ca.id, "https://a.com/rss")
    src_b = await _make_source(db_session, cb.id, "https://b.com/rss")
    n_a = await _make_news(db_session, ca.id, src_a.id)
    n_b = await _make_news(db_session, cb.id, src_b.id)

    await save_feedback(db_session, ca.id, n_a.id, "like")

    ids_a = await get_liked_news_ids(db_session, ca.id)
    ids_b = await get_liked_news_ids(db_session, cb.id)
    assert n_a.id in ids_a
    assert len(ids_b) == 0


# ---------------------------------------------------------------------------
# get_feedback_stats
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_feedback_stats_counts(db_session: AsyncSession) -> None:
    client = await _make_client(db_session, "fs1", 4_001)
    source = await _make_source(db_session, client.id)

    for i in range(3):
        n = await _make_news(db_session, client.id, source.id, i)
        await save_feedback(db_session, client.id, n.id, "like")
    n_dis = await _make_news(db_session, client.id, source.id, 10)
    await save_feedback(db_session, client.id, n_dis.id, "dislike")
    n_sv = await _make_news(db_session, client.id, source.id, 11)
    await save_feedback(db_session, client.id, n_sv.id, "saved")

    stats = await get_feedback_stats(db_session, client.id)
    assert stats["total_liked"] == 3
    assert stats["total_disliked"] == 1
    assert stats["total_saved"] == 1


@pytest.mark.asyncio
async def test_feedback_stats_top_hashtags(db_session: AsyncSession) -> None:
    client = await _make_client(db_session, "fs2", 4_002)
    source = await _make_source(db_session, client.id)

    tags_list = [["AI", "LLM"], ["AI", "GPT"], ["AI", "LLM", "OpenAI"]]
    for i, tags in enumerate(tags_list):
        n = await _make_news(db_session, client.id, source.id, i)
        await update_news_analysis(db_session, n.id, hashtags=tags)
        await save_feedback(db_session, client.id, n.id, "like")

    stats = await get_feedback_stats(db_session, client.id)
    top_tags = [t for t, _ in stats["top_hashtags"]]
    assert top_tags[0] == "AI"  # встречается 3 раза


@pytest.mark.asyncio
async def test_feedback_stats_sentiment_distribution(db_session: AsyncSession) -> None:
    client = await _make_client(db_session, "fs3", 4_003)
    source = await _make_source(db_session, client.id)

    for sentiment in ["positive", "positive", "neutral"]:
        n = await _make_news(db_session, client.id, source.id, id(sentiment))
        await update_news_analysis(db_session, n.id, sentiment=sentiment)
        await save_feedback(db_session, client.id, n.id, "like")

    stats = await get_feedback_stats(db_session, client.id)
    assert stats["sentiment_counts"]["positive"] == 2
    assert stats["sentiment_counts"]["neutral"] == 1


@pytest.mark.asyncio
async def test_feedback_stats_empty(db_session: AsyncSession) -> None:
    client = await _make_client(db_session, "fs4", 4_004)
    stats = await get_feedback_stats(db_session, client.id)
    assert stats["total_liked"] == 0
    assert stats["total_disliked"] == 0
    assert stats["total_saved"] == 0
    assert stats["top_hashtags"] == []


# ---------------------------------------------------------------------------
# get_low_priority_source_ids
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_low_priority_source_detected(db_session: AsyncSession) -> None:
    """Источник с 4/5 дизлайков (80%) должен войти в low_priority."""
    client = await _make_client(db_session, "lp1", 5_001)
    source = await _make_source(db_session, client.id)

    for i in range(4):
        n = await _make_news(db_session, client.id, source.id, i)
        await save_feedback(db_session, client.id, n.id, "dislike")
    n_like = await _make_news(db_session, client.id, source.id, 99)
    await save_feedback(db_session, client.id, n_like.id, "like")

    low = await get_low_priority_source_ids(db_session, client.id, min_feedbacks=5)
    assert source.id in low


@pytest.mark.asyncio
async def test_good_source_not_in_low_priority(db_session: AsyncSession) -> None:
    """Источник с преобладающими лайками не попадает в low_priority."""
    client = await _make_client(db_session, "lp2", 5_002)
    source = await _make_source(db_session, client.id)

    for i in range(5):
        n = await _make_news(db_session, client.id, source.id, i)
        await save_feedback(db_session, client.id, n.id, "like")

    low = await get_low_priority_source_ids(db_session, client.id, min_feedbacks=5)
    assert source.id not in low


@pytest.mark.asyncio
async def test_source_below_min_feedbacks_not_filtered(db_session: AsyncSession) -> None:
    """Источник с малым числом реакций игнорируется независимо от доли дизлайков."""
    client = await _make_client(db_session, "lp3", 5_003)
    source = await _make_source(db_session, client.id)

    for i in range(3):
        n = await _make_news(db_session, client.id, source.id, i)
        await save_feedback(db_session, client.id, n.id, "dislike")

    # min_feedbacks=5, у нас только 3
    low = await get_low_priority_source_ids(db_session, client.id, min_feedbacks=5)
    assert source.id not in low


@pytest.mark.asyncio
async def test_low_priority_respects_client_isolation(db_session: AsyncSession) -> None:
    """Низкоприоритетный источник клиента A не влияет на клиента B."""
    ca = await _make_client(db_session, "lp4a", 5_004)
    cb = await _make_client(db_session, "lp4b", 5_005)
    src_a = await _make_source(db_session, ca.id, "https://lp4a.com/rss")
    _src_b = await _make_source(db_session, cb.id, "https://lp4b.com/rss")

    for i in range(5):
        n = await _make_news(db_session, ca.id, src_a.id, i)
        await save_feedback(db_session, ca.id, n.id, "dislike")

    low_b = await get_low_priority_source_ids(db_session, cb.id, min_feedbacks=5)
    assert src_a.id not in low_b
