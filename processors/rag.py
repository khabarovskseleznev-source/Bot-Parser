"""
RAG-пайплайн: формирование few-shot контекста для LLM.

Ищет k ближайших новостей в ChromaDB и собирает контекстный блок,
который подставляется в промпт перед текущей новостью.
"""

from dataclasses import dataclass

from loguru import logger

from processors.embeddings import get_embedding
from processors.vector_store import VectorStore

# Количество примеров по умолчанию
DEFAULT_TOP_K = 3
# Максимальная длина одного примера (символов), чтобы не раздувать промпт
MAX_EXAMPLE_LEN = 400


@dataclass
class RAGContext:
    """Контекст, сформированный RAG-пайплайном."""

    examples: list[dict]  # список {"title": ..., "summary": ..., "sentiment": ...}
    context_text: str      # готовый текстовый блок для подстановки в промпт


class RAGPipeline:
    """Поиск похожих новостей и формирование контекста для LLM.

    Args:
        vector_store: Клиентское ChromaDB-хранилище.
        top_k: Количество примеров для few-shot.
    """

    def __init__(self, vector_store: VectorStore, top_k: int = DEFAULT_TOP_K) -> None:
        self._vector_store = vector_store
        self._top_k = top_k

    async def build_context(self, title: str, content: str) -> RAGContext:
        """Найти похожие новости и сформировать few-shot контекст.

        Args:
            title: Заголовок текущей новости.
            content: Текст текущей новости.

        Returns:
            RAGContext с примерами и готовым текстом.
        """
        query_text = title + " " + content
        embedding = await get_embedding(query_text)

        results = await self._vector_store.query(embedding, n_results=self._top_k)
        logger.debug("RAG: найдено {} похожих документов", len(results))

        examples = []
        lines = []

        for hit in results:
            meta = hit.get("metadata", {})
            example_title = meta.get("title", "")
            example_summary = meta.get("summary", "")
            example_sentiment = meta.get("sentiment", "")

            # Пропускаем записи без анализа (новости ещё не обработаны LLM)
            if not example_summary:
                continue

            examples.append(
                {
                    "title": example_title,
                    "summary": example_summary,
                    "sentiment": example_sentiment,
                }
            )

            # Обрезаем, чтобы не перегружать промпт
            summary_snippet = example_summary[:MAX_EXAMPLE_LEN]
            lines.append(
                f"- Заголовок: {example_title}\n"
                f"  Краткое: {summary_snippet}\n"
                f"  Тональность: {example_sentiment}"
            )

        context_text = "\n\n".join(lines) if lines else ""
        return RAGContext(examples=examples, context_text=context_text)
