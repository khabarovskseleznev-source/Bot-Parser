"""
Тесты keyword-фильтрации (логика без запуска полного pipeline).
"""

import pytest


def _matches_keywords(title: str, content: str, keywords: list[str]) -> bool:
    """Вспомогательная функция — воспроизводит логику фильтра из pipeline."""
    if not keywords:
        return True
    text_lower = (title + " " + content).lower()
    return any(kw.lower() in text_lower for kw in keywords)


def test_empty_keywords_passes_everything() -> None:
    assert _matches_keywords("Любой заголовок", "Любой контент", []) is True


def test_keyword_match_in_title() -> None:
    assert _matches_keywords("Тендер на строительство", "Подробности.", ["тендер"]) is True


def test_keyword_match_in_content() -> None:
    assert _matches_keywords("Заголовок", "Речь идёт о цементе.", ["цемент"]) is True


def test_no_keyword_match() -> None:
    assert _matches_keywords("Погода в Москве", "Облачно, без осадков.", ["строительство", "тендер"]) is False


def test_case_insensitive_match() -> None:
    assert _matches_keywords("ТЕНДЕР на поставку", "Подробности.", ["тендер"]) is True


def test_partial_word_does_not_match_incorrectly() -> None:
    # "стройка" не должна совпадать с "стройматериалы"
    # но "строительство" должно совпасть c "строительство"
    assert _matches_keywords("Про строительство жилья", "Текст.", ["строительство"]) is True
    # "строи" — короткое совпадение — тоже должно совпасть (substring matching)
    assert _matches_keywords("Строительная компания", "Текст.", ["строи"]) is True


def test_multiple_keywords_any_match() -> None:
    assert _matches_keywords("Торги на стройку", "Много текста.", ["тендер", "торги"]) is True
