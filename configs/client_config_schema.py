"""
Pydantic-схема конфигурации клиента.

Источник истины для структуры конфига.
Рабочие конфиги хранятся в data/clients/<id>/config.json
и валидируются через ClientConfig при загрузке.
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field


class SelectorConfig(BaseModel):
    """CSS-селекторы для парсинга веб-сайта."""

    title: str
    content: str
    date: Optional[str] = None


class SourceConfig(BaseModel):
    """Конфигурация одного источника новостей."""

    type: Literal["telegram", "rss", "website", "social"]
    url: str
    name: str
    is_active: bool = True
    fetch_interval_minutes: int = 60
    selector: Optional[SelectorConfig] = None  # только для type="website"


class AnalysisConfig(BaseModel):
    """Настройки анализа новостей."""

    summary: bool = True
    sentiment: bool = True
    ner: bool = True
    hashtags: bool = True
    deduplication: bool = True
    deduplication_threshold: float = 0.85  # порог косинусной меры для TF-IDF


class DeliveryConfig(BaseModel):
    """Настройки доставки новостей пользователю."""

    frequency: Literal["instant", "hourly", "daily"] = "instant"
    daily_time: Optional[str] = None  # "08:00" — только для frequency="daily"
    only_keywords: bool = True  # отправлять только если есть совпадение с keywords


class FiltersConfig(BaseModel):
    """Дополнительные фильтры для новостей."""

    min_content_length: int = 0  # минимальная длина контента в символах (0 = отключено)


class ClientConfig(BaseModel):
    """Полная конфигурация клиента."""

    client_id: str
    client_name: str
    telegram_chat_id: int
    sources: list[SourceConfig]
    keywords: list[str]
    exclude_keywords: list[str] = Field(default_factory=list)
    competitors: list[str] = Field(default_factory=list)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    delivery: DeliveryConfig = Field(default_factory=DeliveryConfig)
    filters: FiltersConfig = Field(default_factory=FiltersConfig)
