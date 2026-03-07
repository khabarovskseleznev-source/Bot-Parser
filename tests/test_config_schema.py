"""
Тесты Pydantic-схемы конфигурации клиента.
"""

import json

import pytest
from pydantic import ValidationError

from configs.client_config_schema import ClientConfig


def _base_config() -> dict:
    return {
        "client_id": "test",
        "client_name": "Test",
        "telegram_chat_id": 123456789,
        "sources": [
            {
                "type": "rss",
                "url": "https://example.com/rss",
                "name": "Test RSS",
            }
        ],
        "keywords": ["строительство"],
    }


def test_valid_config_parses() -> None:
    cfg = ClientConfig(**_base_config())
    assert cfg.client_id == "test"
    assert len(cfg.sources) == 1
    assert cfg.sources[0].type == "rss"
    assert cfg.delivery.frequency == "instant"


def test_config_from_json_file(tmp_path) -> None:
    data = _base_config()
    f = tmp_path / "config.json"
    f.write_text(json.dumps(data, ensure_ascii=False))
    loaded = ClientConfig.model_validate_json(f.read_text())
    assert loaded.client_name == "Test"


def test_invalid_source_type_raises() -> None:
    data = _base_config()
    data["sources"][0]["type"] = "unknown_type"
    with pytest.raises(ValidationError):
        ClientConfig(**data)


def test_invalid_frequency_raises() -> None:
    data = _base_config()
    data["delivery"] = {"frequency": "weekly"}
    with pytest.raises(ValidationError):
        ClientConfig(**data)


def test_website_source_with_selector() -> None:
    data = _base_config()
    data["sources"] = [
        {
            "type": "website",
            "url": "https://example.com",
            "name": "Example",
            "selector": {"title": "h1", "content": ".content"},
        }
    ]
    cfg = ClientConfig(**data)
    assert cfg.sources[0].selector is not None
    assert cfg.sources[0].selector.title == "h1"


def test_keywords_default_empty_list() -> None:
    data = _base_config()
    data["keywords"] = []
    cfg = ClientConfig(**data)
    assert cfg.keywords == []


def test_exclude_keywords_defaults_to_empty() -> None:
    cfg = ClientConfig(**_base_config())
    assert cfg.exclude_keywords == []
