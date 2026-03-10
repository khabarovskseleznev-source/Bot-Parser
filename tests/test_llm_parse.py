"""
Тесты парсинга ответов LLM (_parse_response) и построения промпта (_build_prompt).

Не делают сетевых вызовов — тестируют только логику разбора.
"""

import pytest

from processors.llm import _build_prompt, _parse_response


# ---------------------------------------------------------------------------
# _parse_response
# ---------------------------------------------------------------------------

def test_parse_valid_json() -> None:
    raw = '{"summary": "Краткое изложение", "sentiment": "positive", "hashtags": ["AI", "LLM"], "importance": 8}'
    result = _parse_response(raw)
    assert result.summary == "Краткое изложение"
    assert result.sentiment == "positive"
    assert result.hashtags == ["AI", "LLM"]
    assert result.importance_score == 8


def test_parse_json_wrapped_in_text() -> None:
    """JSON внутри лишнего текста — должен извлечься."""
    raw = 'Вот анализ:\n{"summary": "S", "sentiment": "neutral", "hashtags": [], "importance": 5}\nконец'
    result = _parse_response(raw)
    assert result.summary == "S"
    assert result.sentiment == "neutral"


def test_parse_invalid_json_returns_defaults() -> None:
    result = _parse_response("не JSON вообще")
    assert result.summary == ""
    assert result.sentiment == "neutral"
    assert result.hashtags == []
    assert result.importance_score == 5


def test_parse_invalid_sentiment_falls_back_to_neutral() -> None:
    raw = '{"summary": "X", "sentiment": "unknown_value", "hashtags": [], "importance": 5}'
    result = _parse_response(raw)
    assert result.sentiment == "neutral"


def test_parse_importance_clamped_above_10() -> None:
    raw = '{"summary": "X", "sentiment": "positive", "hashtags": [], "importance": 15}'
    result = _parse_response(raw)
    assert result.importance_score == 10


def test_parse_importance_clamped_below_1() -> None:
    raw = '{"summary": "X", "sentiment": "negative", "hashtags": [], "importance": -3}'
    result = _parse_response(raw)
    assert result.importance_score == 1


def test_parse_importance_non_integer_falls_back() -> None:
    raw = '{"summary": "X", "sentiment": "neutral", "hashtags": [], "importance": "high"}'
    result = _parse_response(raw)
    assert result.importance_score == 5


def test_parse_hashtags_strips_hash_prefix() -> None:
    raw = '{"summary": "X", "sentiment": "neutral", "hashtags": ["#AI", "#LLM", "GPT"], "importance": 5}'
    result = _parse_response(raw)
    assert "AI" in result.hashtags
    assert "LLM" in result.hashtags
    assert "GPT" in result.hashtags


def test_parse_hashtags_non_list_ignored() -> None:
    raw = '{"summary": "X", "sentiment": "neutral", "hashtags": "not-a-list", "importance": 5}'
    result = _parse_response(raw)
    assert result.hashtags == []


def test_parse_missing_fields_use_defaults() -> None:
    raw = '{"summary": "только summary"}'
    result = _parse_response(raw)
    assert result.summary == "только summary"
    assert result.sentiment == "neutral"
    assert result.hashtags == []
    assert result.importance_score == 5


def test_parse_raw_is_preserved() -> None:
    raw = '{"summary": "X", "sentiment": "neutral", "hashtags": [], "importance": 5}'
    result = _parse_response(raw)
    assert result.raw == raw


# ---------------------------------------------------------------------------
# _build_prompt
# ---------------------------------------------------------------------------

def test_build_prompt_contains_title_and_content() -> None:
    prompt = _build_prompt("Заголовок", "Контент", "")
    assert "Заголовок" in prompt
    assert "Контент" in prompt


def test_build_prompt_with_rag_context_includes_context() -> None:
    prompt = _build_prompt("T", "C", "Примерная новость из RAG")
    assert "Примерная новость из RAG" in prompt


def test_build_prompt_without_rag_no_context_block() -> None:
    prompt = _build_prompt("T", "C", "")
    assert "Примеры аналогичных новостей" not in prompt


def test_build_prompt_content_truncated_at_2000() -> None:
    long_content = "x" * 3000
    prompt = _build_prompt("T", long_content, "")
    # В промпте не должно быть >2000 символов контента подряд
    assert "x" * 2001 not in prompt
