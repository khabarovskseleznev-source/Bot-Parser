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
    get_or_create_source,
    save_news,
    update_news_analysis,
)
from database.db import get_session
from parsers.base import ParsedItem
from processors.deduplicator import Deduplicator
from processors.embeddings import get_embedding
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
        ollama_url: URL Ollama.
        ollama_model: Название модели Ollama.
        sender: Экземпляр NewsSender для доставки в Telegram (опционально).
    """

    def __init__(
        self,
        client_id: int,
        client_str_id: str,
        chroma_path: Path,
        telegram_chat_id: int = 0,
        ollama_url: str = "http://localhost:11434",
        ollama_model: str = "saiga_llama3_8b",
        sender: Optional["NewsSender"] = None,
    ) -> None:
        self._client_id = client_id
        self._telegram_chat_id = telegram_chat_id
        self._sender = sender
        self._vector_store = VectorStore(
            client_id=client_str_id,
            persist_directory=chroma_path,
        )
        self._deduplicator = Deduplicator(self._vector_store)
        self._rag = RAGPipeline(self._vector_store)
        self._llm = LLMClient(base_url=ollama_url, model=ollama_model)

    async def _process_item(
        self,
        session: AsyncSession,
        source_config: SourceConfig,
        item: ParsedItem,
    ) -> None:
        """Обработать одну новость.

        Args:
            session: Сессия SQLAlchemy.
            source_config: Конфиг источника из ClientConfig.
            item: Распарсенная новость.
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

        # 3.5. Keyword-фильтрация
        client_settings = await get_client_settings(session, self._client_id)
        keywords = client_settings.keywords if client_settings else []
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

        # 4. RAG-контекст для LLM
        rag_ctx = await self._rag.build_context(item.title, item.content)

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
            summary=llm_result.summary,
            sentiment=llm_result.sentiment,
            hashtags=llm_result.hashtags,
        )

        # 7. Добавить эмбеддинг в ChromaDB
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
        frequency = client_settings.frequency if client_settings else "instant"
        if self._sender and self._telegram_chat_id and frequency == "instant":
            # Обновляем объект news локально, чтобы не делать лишний SELECT
            news.summary = llm_result.summary
            news.sentiment = llm_result.sentiment
            news.hashtags = llm_result.hashtags
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
            for item in items:
                try:
                    await self._process_item(session, source_config, item)
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
