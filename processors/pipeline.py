"""
Оркестратор RAG + LLM пайплайна.

Принимает список ParsedItem от планировщика, прогоняет через:
  1. Дедупликация (hash + semantic)
  2. Сохранение в SQLite
  3. LLM анализ (summary / sentiment / hashtags)
  4. Обновление записи в SQLite
  5. Добавление эмбеддинга в ChromaDB
  6. Отправка в Telegram (через NewsSender, если задан)

Подключается к scheduler.ParserScheduler как on_items callback.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from configs.client_config_schema import SourceConfig
from database.crud import (
    compute_hash,
    get_client_settings,
    get_liked_news_ids,
    get_low_priority_source_ids,
    get_or_create_source,
    save_news,
    update_news_analysis,
)
from database.db import get_session
from parsers.base import ParsedItem
from processors.deduplicator import Deduplicator
from processors.embeddings import get_embedding  # fallback если embedding не из дедупликатора
from processors.llm import LLMClient
from processors.rag import RAGPipeline
from processors.vector_store import VectorStore

if TYPE_CHECKING:
    from bot.sender import NewsSender


class NewsPipeline:
    """Оркестратор обработки новостей.

    Args:
        client_id: Числовой ID клиента (из таблицы clients).
        client_str_id: Строковый ID клиента (из конфига, для ChromaDB).
        chroma_path: Корневая директория для ChromaDB (data/chroma).
        telegram_chat_id: Chat ID клиента для отправки новостей.
        openrouter_api_key: API ключ OpenRouter.
        sender: Экземпляр NewsSender для доставки в Telegram (опционально).
    """

    def __init__(
        self,
        client_id: int,
        client_str_id: str,
        chroma_path: Path,
        telegram_chat_id: int = 0,
        openrouter_api_key: str = "",
        sender: Optional["NewsSender"] = None,
        min_content_length: int = 0,
        deduplication_threshold: float = 0.85,
    ) -> None:
        self._client_id = client_id
        self._telegram_chat_id = telegram_chat_id
        self._sender = sender
        self._min_content_length = min_content_length
        self._vector_store = VectorStore(
            client_id=client_str_id,
            persist_directory=chroma_path,
        )
        self._deduplicator = Deduplicator(self._vector_store, similarity_threshold=deduplication_threshold)
        self._rag = RAGPipeline(self._vector_store)
        self._llm = LLMClient(api_key=openrouter_api_key)

    @property
    def client_id(self) -> int:
        """Числовой ID клиента в БД."""
        return self._client_id

    async def _process_item(
        self,
        session: AsyncSession,
        source_config: SourceConfig,
        item: ParsedItem,
        keywords: list[str],
        low_priority_ids: set[int],
        liked_ids: set[int],
        frequency: str,
    ) -> None:
        """Обработать одну новость.

        Args:
            session: Сессия SQLAlchemy.
            source_config: Конфиг источника из ClientConfig.
            item: Распарсенная новость.
            keywords: Ключевые слова клиента (предзагружены на batch).
            low_priority_ids: Множество низкоприоритетных source_id.
            liked_ids: Множество news_id лайкнутых новостей.
            frequency: Режим доставки (instant/hourly/daily).
        """
        # 1. Получить/создать источник в БД
        source = await get_or_create_source(
            session=session,
            client_id=self._client_id,
            url=source_config.url,
            name=source_config.name,
            source_type=source_config.type,
            fetch_interval=source_config.fetch_interval_minutes,
        )

        # 2. Дедупликация
        dup_result = await self._deduplicator.check(
            session=session,
            client_id=self._client_id,
            title=item.title,
            content=item.content,
        )

        # 3. Сохранить в SQLite (дубликаты тоже сохраняем для статистики)
        news = await save_news(
            session=session,
            client_id=self._client_id,
            source_id=source.id,
            url=item.url,
            title=item.title,
            content=item.content,
            published_at=item.published_at,
            is_duplicate=dup_result.is_duplicate,
        )

        if dup_result.is_duplicate:
            logger.debug(
                "Дубликат пропущен ({}): client={}, title={!r}",
                dup_result.reason,
                self._client_id,
                item.title[:60],
            )
            return

        # 3.4. Фильтр по минимальной длине контента
        if self._min_content_length > 0 and len(item.content) < self._min_content_length:
            news.keyword_filtered = True
            await session.commit()
            logger.debug(
                "Фильтр длины: контент {}симв < {}симв, пропущено: client={}, title={!r}",
                len(item.content), self._min_content_length, self._client_id, item.title[:60],
            )
            return

        # 3.5. Keyword-фильтрация
        if keywords:
            text_lower = (item.title + " " + item.content).lower()
            if not any(kw.lower() in text_lower for kw in keywords):
                news.keyword_filtered = True
                await session.commit()
                logger.debug(
                    "Keyword-фильтр: новость не прошла: client={}, title={!r}",
                    self._client_id,
                    item.title[:60],
                )
                return

        # 3.6. Фильтр низкоприоритетных источников (преобладающие дизлайки)
        if source.id in low_priority_ids:
            news.keyword_filtered = True
            await session.commit()
            logger.debug(
                "Source-фильтр: источник source_id={} низкоприоритетный, новость пропущена: client={}, title={!r}",
                source.id, self._client_id, item.title[:60],
            )
            return

        # 4. RAG-контекст для LLM (с бустом лайкнутых новостей)
        rag_ctx = await self._rag.build_context(item.title, item.content, liked_news_ids=liked_ids)

        # 5. Анализ через LLM
        llm_result = await self._llm.analyze(
            title=item.title,
            content=item.content,
            rag_context=rag_ctx.context_text,
        )

        # 6. Записать результаты анализа в БД
        await update_news_analysis(
            session=session,
            news_id=news.id,
            title_ru=llm_result.title_ru or None,
            summary=llm_result.summary,
            sentiment=llm_result.sentiment,
            hashtags=llm_result.hashtags,
            importance_score=llm_result.importance_score,
        )

        # 7. Добавить эмбеддинг в ChromaDB (переиспользуем из дедупликатора)
        embedding = dup_result.embedding
        if embedding is None:
            text_for_embed = item.title + " " + item.content
            embedding = await get_embedding(text_for_embed)
        content_hash = compute_hash(item.title + item.content)

        await self._vector_store.add(
            doc_id=content_hash,
            embedding=embedding,
            document=text_for_embed[:1000],
            metadata={
                "client_id": str(self._client_id),
                "news_id": str(news.id),
                "title": item.title[:200],
                "summary": llm_result.summary[:400],
                "sentiment": llm_result.sentiment,
                "url": item.url,
            },
        )

        logger.info(
            "Обработана новость: client={}, id={}, sentiment={}, title={!r}",
            self._client_id,
            news.id,
            llm_result.sentiment,
            item.title[:60],
        )

        # 8. Отправка в Telegram (только instant-режим; hourly/daily — через дайджест-джоб)
        if self._sender and self._telegram_chat_id and frequency == "instant":
            # Обновляем объект news локально, чтобы не делать лишний SELECT
            news.title_ru = llm_result.title_ru or None
            news.summary = llm_result.summary
            news.sentiment = llm_result.sentiment
            news.hashtags = llm_result.hashtags
            news.importance_score = llm_result.importance_score
            await self._sender.send_news(
                chat_id=self._telegram_chat_id,
                news=news,
            )

    async def process(
        self,
        source_config: SourceConfig,
        items: list[ParsedItem],
    ) -> None:
        """Обработать список новостей от одного источника.

        Args:
            source_config: Конфиг источника.
            items: Список новостей от парсера.
        """
        if not items:
            return

        logger.info(
            "Pipeline: {} новостей от источника '{}'",
            len(items),
            source_config.name,
        )

        async for session in get_session():
            # Предзагрузка данных один раз на весь batch (вместо per-item)
            client_settings = await get_client_settings(session, self._client_id)
            keywords = client_settings.keywords if client_settings else []
            frequency = client_settings.frequency if client_settings else "instant"
            low_priority_ids = await get_low_priority_source_ids(session, self._client_id)
            liked_ids = await get_liked_news_ids(session, self._client_id)

            for item in items:
                try:
                    await self._process_item(
                        session, source_config, item,
                        keywords=keywords,
                        low_priority_ids=low_priority_ids,
                        liked_ids=liked_ids,
                        frequency=frequency,
                    )
                except Exception:
                    logger.exception(
                        "Ошибка обработки новости: source={}, url={}",
                        source_config.name,
                        item.url,
                    )


def make_on_items_callback(
    pipelines: dict[str, "NewsPipeline"],
):
    """Создать on_items callback для ParserScheduler.

    Args:
        pipelines: Словарь {client_str_id: NewsPipeline}.

    Returns:
        Async функция-callback, совместимая с OnItemsCallback.
    """

    async def on_items(
        client_id: str,
        source_config: SourceConfig,
        items: list[ParsedItem],
    ) -> None:
        pipeline = pipelines.get(client_id)
        if pipeline is None:
            logger.warning("Pipeline не найден для клиента: {}", client_id)
            return
        await pipeline.process(source_config, items)

    return on_items
