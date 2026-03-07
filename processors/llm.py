"""
Вызов LLM через Ollama HTTP API.

Формирует промпт с few-shot контекстом от RAG, отправляет на Ollama,
парсит структурированный ответ (summary / sentiment / hashtags).

Fallback: если ответ не удалось распарсить — возвращает пустые поля.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Optional

import aiohttp
from loguru import logger

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "saiga_llama3_8b"
REQUEST_TIMEOUT = 120  # секунд

_SENTIMENT_VALUES = {"positive", "neutral", "negative"}


@dataclass
class LLMResult:
    """Структурированный результат анализа LLM."""

    summary: str = ""
    sentiment: str = "neutral"
    hashtags: list[str] = field(default_factory=list)
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
        f"Проанализируй новость и ответь строго в формате JSON без пояснений:\n"
        f'{{"summary": "<краткое изложение 2-3 предложения>", '
        f'"sentiment": "<positive|neutral|negative>", '
        f'"hashtags": ["<тег1>", "<тег2>", "<тег3>"]}}\n\n'
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

    # Пытаемся найти JSON-блок в ответе
    json_str = raw.strip()
    match = re.search(r"\{.*\}", json_str, re.DOTALL)
    if match:
        json_str = match.group(0)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        logger.warning("LLM: не удалось разобрать JSON-ответ: {!r}", raw[:200])
        return result

    result.summary = str(data.get("summary", "")).strip()

    sentiment = str(data.get("sentiment", "neutral")).lower().strip()
    result.sentiment = sentiment if sentiment in _SENTIMENT_VALUES else "neutral"

    hashtags = data.get("hashtags", [])
    if isinstance(hashtags, list):
        result.hashtags = [
            str(h).strip().lstrip("#") for h in hashtags if isinstance(h, str)
        ][:10]

    return result


class LLMClient:
    """Клиент для работы с Ollama.

    Args:
        base_url: URL сервера Ollama (по умолчанию localhost:11434).
        model: Название модели.
        timeout: Таймаут запроса в секундах.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_OLLAMA_URL,
        model: str = DEFAULT_MODEL,
        timeout: int = REQUEST_TIMEOUT,
    ) -> None:
        self._base_url = base_url.rstrip("/")
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
        prompt = _build_prompt(title, content, rag_context)
        payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }

        try:
            async with aiohttp.ClientSession(timeout=self._timeout) as session:
                async with session.post(
                    f"{self._base_url}/api/generate",
                    json=payload,
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    raw = data.get("response", "")
        except aiohttp.ClientError as exc:
            logger.error("LLM: ошибка подключения к Ollama: {}", exc)
            return LLMResult()
        except Exception:
            logger.exception("LLM: непредвиденная ошибка")
            return LLMResult()

        result = _parse_response(raw)
        logger.debug(
            "LLM: sentiment={}, hashtags={}, summary_len={}",
            result.sentiment,
            result.hashtags,
            len(result.summary),
        )
        return result
