"""
Тесты CRUD-операций с базой данных.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from database.crud import (
    get_client_settings,
    get_news_by_hash,
    get_or_create_client,
    get_or_create_source,
    get_unsent_news,
    mark_sent,
    save_feedback,
    save_news,
)
from database.models import Settings


@pytest.mark.asyncio
async def test_get_or_create_client_creates_new(db_session: AsyncSession) -> None:
    client = await get_or_create_client(
        session=db_session,
        client_str_id="test",
        name="Test Client",
        telegram_chat_id=111111,
    )
    assert client.id is not None
    assert client.telegram_chat_id == 111111
    assert client.name == "Test Client"


@pytest.mark.asyncio
async def test_get_or_create_client_returns_existing(db_session: AsyncSession) -> None:
    c1 = await get_or_create_client(
        session=db_session, client_str_id="test", name="Test", telegram_chat_id=222222
    )
    c2 = await get_or_create_client(
        session=db_session, client_str_id="test", name="Updated", telegram_chat_id=222222
    )
    assert c1.id == c2.id


@pytest.mark.asyncio
async def test_save_and_get_news(db_session: AsyncSession) -> None:
    client = await get_or_create_client(
        session=db_session, client_str_id="c1", name="C1", telegram_chat_id=333333
    )
    source = await get_or_create_source(
        session=db_session,
        client_id=client.id,
        url="https://example.com/rss",
        name="Test RSS",
        source_type="rss",
    )

    news = await save_news(
        session=db_session,
        client_id=client.id,
        source_id=source.id,
        url="https://example.com/news/1",
        title="Тестовая новость",
        content="Содержание тестовой новости про строительство",
    )
    assert news.id is not None
    assert news.sent_to_user is False
    assert news.keyword_filtered is False

    # Поиск по хешу
    from database.crud import compute_hash
    h = compute_hash("Тестовая новость" + "Содержание тестовой новости про строительство")
    found = await get_news_by_hash(db_session, client.id, h)
    assert found is not None
    assert found.id == news.id


@pytest.mark.asyncio
async def test_mark_sent(db_session: AsyncSession) -> None:
    client = await get_or_create_client(
        session=db_session, client_str_id="c2", name="C2", telegram_chat_id=444444
    )
    source = await get_or_create_source(
        session=db_session,
        client_id=client.id,
        url="https://example.com/rss2",
        name="RSS2",
        source_type="rss",
    )
    news = await save_news(
        session=db_session,
        client_id=client.id,
        source_id=source.id,
        url="https://example.com/news/2",
        title="Ещё новость",
        content="Про тендеры и закупки",
    )

    await mark_sent(db_session, news.id)
    await db_session.refresh(news)
    assert news.sent_to_user is True


@pytest.mark.asyncio
async def test_save_feedback(db_session: AsyncSession) -> None:
    client = await get_or_create_client(
        session=db_session, client_str_id="c3", name="C3", telegram_chat_id=555555
    )
    source = await get_or_create_source(
        session=db_session,
        client_id=client.id,
        url="https://example.com/rss3",
        name="RSS3",
        source_type="rss",
    )
    news = await save_news(
        session=db_session,
        client_id=client.id,
        source_id=source.id,
        url="https://example.com/news/3",
        title="Новость 3",
        content="Контент 3",
    )

    feedback = await save_feedback(db_session, client.id, news.id, "like")
    assert feedback.id is not None
    assert feedback.reaction == "like"


@pytest.mark.asyncio
async def test_get_unsent_news(db_session: AsyncSession) -> None:
    client = await get_or_create_client(
        session=db_session, client_str_id="c4", name="C4", telegram_chat_id=666666
    )
    source = await get_or_create_source(
        session=db_session,
        client_id=client.id,
        url="https://example.com/rss4",
        name="RSS4",
        source_type="rss",
    )

    n1 = await save_news(
        session=db_session,
        client_id=client.id,
        source_id=source.id,
        url="https://example.com/n1",
        title="Новость 1",
        content="Контент 1",
    )
    n2 = await save_news(
        session=db_session,
        client_id=client.id,
        source_id=source.id,
        url="https://example.com/n2",
        title="Новость 2",
        content="Контент 2",
    )
    # Отправляем n1
    await mark_sent(db_session, n1.id)

    unsent = await get_unsent_news(db_session, client.id)
    assert len(unsent) == 1
    assert unsent[0].id == n2.id


@pytest.mark.asyncio
async def test_get_client_settings_none_for_new_client(db_session: AsyncSession) -> None:
    client = await get_or_create_client(
        session=db_session, client_str_id="c5", name="C5", telegram_chat_id=777777
    )
    s = await get_client_settings(db_session, client.id)
    assert s is None


@pytest.mark.asyncio
async def test_get_client_settings_returns_settings(db_session: AsyncSession) -> None:
    client = await get_or_create_client(
        session=db_session, client_str_id="c6", name="C6", telegram_chat_id=888888
    )
    db_session.add(Settings(client_id=client.id, keywords=["тендер"], frequency="hourly"))
    await db_session.commit()

    s = await get_client_settings(db_session, client.id)
    assert s is not None
    assert s.keywords == ["тендер"]
    assert s.frequency == "hourly"
