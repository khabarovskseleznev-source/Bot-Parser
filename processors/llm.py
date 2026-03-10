"""
Вызов LLM через Groq API (OpenAI-совместимый).

Формирует промпт с few-shot контекстом от RAG, отправляет на Groq,
парсит структурированный ответ (summary / sentiment / hashtags).

Fallback: если ответ не удалось распарсить — возвращает пустые поля.
"""

import json
import os
import re
from dataclasses import dataclass, field

import aiohttp
from loguru import logger

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "meta-llama/llama-3.1-8b-instruct:free"
REQUEST_TIMEOUT = 30  # секунд

_SENTIMENT_VALUES = {"positive", "neutral", "negative"}


@dataclass
class LLMResult:
    """Структурированный результат анализа LLM."""

    summary: str = ""
    sentiment: str = "neutral"
    hashtags: list[str] = field(default_factory=list)
    importance_score: int = 5
    title_ru: str = ""  # перевод заголовка на русский
    raw: str = ""  # сырой ответ для отладки


def _build_prompt(title: str, content: str, rag_context: str) -> str:
    """Составить промпт для LLM.

    Args:
        title: Заголовок новости.
        content: Текст новости (может быть обрезан).
        rag_context: Few-shot контекст от RAG (может быть пустым).

    Returns:
        Готовый промпт-строка.
    """
    context_block = (
        f"Примеры аналогичных новостей:\n{rag_context}\n\n"
        if rag_context
        else ""
    )

    return (
        f"{context_block}"
        f"Проанализируй новость и ответь строго в формате JSON без пояснений.\n"
        f"Все текстовые поля — на русском языке.\n\n"
        f'{{"title_ru": "<перевод заголовка на русский, если уже на русском — оставить>", '
        f'"summary": "<краткое изложение 2-3 предложения на русском>", '
        f'"sentiment": "<positive|neutral|negative>", '
        f'"hashtags": ["<тег1>", "<тег2>", "<тег3>"], '
        f'"importance": <целое число 1-10>}}\n\n'
        f"Критерии importance:\n"
        f"9-10: прорыв, крупный релиз модели, громкое событие отрасли\n"
        f"6-8: новый продукт, важное исследование, значимое партнёрство\n"
        f"1-5: обзор, мнение, общая статья, незначительное обновление\n\n"
        f"Заголовок: {title}\n"
        f"Текст: {content[:2000]}"
    )


def _parse_response(raw: str) -> LLMResult:
    """Разобрать JSON-ответ LLM.

    Пробует несколько стратегий извлечения JSON.
    При неудаче возвращает LLMResult с пустыми полями.

    Args:
        raw: Сырой текст ответа.

    Returns:
        LLMResult.
    """
    result = LLMResult(raw=raw)

    json_str = raw.strip()
    match = re.search(r"\{.*\}", json_str, re.DOTALL)
    if match:
        json_str = match.group(0)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        logger.warning("LLM: не удалось разобрать JSON-ответ: {!r}", raw[:200])
        return result

    result.title_ru = str(data.get("title_ru", "")).strip()
    result.summary = str(data.get("summary", "")).strip()

    sentiment = str(data.get("sentiment", "neutral")).lower().strip()
    result.sentiment = sentiment if sentiment in _SENTIMENT_VALUES else "neutral"

    hashtags = data.get("hashtags", [])
    if isinstance(hashtags, list):
        result.hashtags = [
            str(h).strip().lstrip("#") for h in hashtags if isinstance(h, str)
        ][:10]

    try:
        importance = int(data.get("importance", 5))
        result.importance_score = max(1, min(10, importance))
    except (TypeError, ValueError):
        result.importance_score = 5

    return result


class LLMClient:
    """Клиент для работы с Groq API.

    Args:
        api_key: Groq API key (по умолчанию из GROQ_API_KEY env).
        model: Название модели.
        timeout: Таймаут запроса в секундах.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        timeout: int = REQUEST_TIMEOUT,
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self._model = model
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    async def analyze(
        self,
        title: str,
        content: str,
        rag_context: str = "",
    ) -> LLMResult:
        """Проанализировать новость.

        Args:
            title: Заголовок.
            content: Текст новости.
            rag_context: Few-shot примеры от RAG.

        Returns:
            LLMResult с summary, sentiment, hashtags.
            При ошибке — LLMResult с пустыми полями (fallback).
        """
        if not self._api_key:
            logger.warning("LLM: OPENROUTER_API_KEY не задан, пропускаем анализ")
            return LLMResult()

        prompt = _build_prompt(title, content, rag_context)
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession(timeout=self._timeout) as session:
                async with session.post(
                    OPENROUTER_API_URL,
                    json=payload,
                    headers=headers,
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    raw = data["choices"][0]["message"]["content"]
        except aiohttp.ClientError as exc:
            logger.error("LLM: ошибка подключения к Groq: {}", exc)
            return LLMResult()
        except Exception:
            logger.exception("LLM: непредвиденная ошибка")
            return LLMResult()

        result = _parse_response(raw)
        logger.debug(
            "LLM: sentiment={}, importance={}, hashtags={}, summary_len={}",
            result.sentiment,
            result.importance_score,
            result.hashtags,
            len(result.summary),
        )
        return result
