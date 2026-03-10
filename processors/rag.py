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

    async def build_context(
        self,
        title: str,
        content: str,
        liked_news_ids: set[int] | None = None,
    ) -> RAGContext:
        """Найти похожие новости и сформировать few-shot контекст.

        Лайкнутые новости получают приоритет: запрашиваем top_k*3 результатов,
        сортируем так, чтобы лайкнутые шли первыми, берём top_k.

        Args:
            title: Заголовок текущей новости.
            content: Текст текущей новости.
            liked_news_ids: Множество news_id, которые пользователь лайкнул/сохранил.

        Returns:
            RAGContext с примерами и готовым текстом.
        """
        query_text = title + " " + content
        embedding = await get_embedding(query_text)

        fetch_k = self._top_k * 3 if liked_news_ids else self._top_k
        results = await self._vector_store.query(embedding, n_results=fetch_k)
        logger.debug("RAG: найдено {} похожих документов (fetch_k={})", len(results), fetch_k)

        if liked_news_ids:
            # Лайкнутые — в начало, остальные по дистанции
            def _sort_key(hit: dict) -> tuple[int, float]:
                try:
                    nid = int(hit.get("metadata", {}).get("news_id", -1))
                except (TypeError, ValueError):
                    nid = -1
                is_liked = 0 if nid in liked_news_ids else 1
                return (is_liked, hit.get("distance", 1.0))

            results = sorted(results, key=_sort_key)[: self._top_k]
            liked_count = sum(
                1 for h in results
                if str(h.get("metadata", {}).get("news_id", "")) in
                {str(i) for i in liked_news_ids}
            )
            if liked_count:
                logger.debug("RAG: поднято {} лайкнутых новостей в контекст", liked_count)

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
