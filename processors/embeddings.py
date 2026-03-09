"""
Генерация текстовых эмбеддингов.

Использует модель all-MiniLM-L6-v2 (sentence-transformers) — ~90 МБ RAM.
Вычисления выполняются в asyncio.to_thread, чтобы не блокировать event loop.
"""

import asyncio
from typing import Optional

from loguru import logger
from sentence_transformers import SentenceTransformer

_model: Optional[SentenceTransformer] = None
_MODEL_NAME = "all-MiniLM-L6-v2"


def _get_model() -> SentenceTransformer:
    """Ленивая инициализация модели (загрузка при первом вызове)."""
    global _model
    if _model is None:
        logger.info("Загрузка модели эмбеддингов: {}", _MODEL_NAME)
        _model = SentenceTransformer(_MODEL_NAME)
        logger.info("Модель эмбеддингов загружена.")
    return _model


def _encode_sync(texts: list[str]) -> list[list[float]]:
    """Синхронная генерация эмбеддингов (запускается в thread-pool).

    Args:
        texts: Список строк для кодирования.

    Returns:
        Список векторов (list of floats).
    """
    model = _get_model()
    vectors = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
    return vectors.tolist()


async def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Асинхронная генерация эмбеддингов для списка текстов.

    Args:
        texts: Список строк. Не должен быть пустым.

    Returns:
        Список эмбеддинг-векторов. Порядок совпадает с входным списком.

    Raises:
        ValueError: Если передан пустой список.
    """
    if not texts:
        raise ValueError("Список текстов для эмбеддинга не может быть пустым.")
    logger.debug("Генерация эмбеддингов: {} текстов", len(texts))
    result = await asyncio.to_thread(_encode_sync, texts)
    return result


async def get_embedding(text: str) -> list[float]:
    """Асинхронная генерация эмбеддинга для одного текста.

    Args:
        text: Входная строка.

    Returns:
        Вектор эмбеддинга.
    """
    vectors = await get_embeddings([text])
    return vectors[0]
