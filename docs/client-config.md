# Конфигурация клиента

## Где хранится

- **Схема (источник истины):** `configs/client_config_schema.py` — Pydantic-модель, определяет структуру.
- **Рабочий конфиг:** `data/clients/<id>/config.json` — заполняется при онбординге клиента, валидируется при загрузке.

## Pydantic-схема

```python
# configs/client_config_schema.py
from pydantic import BaseModel, Field
from typing import List, Optional, Literal

class SourceConfig(BaseModel):
    type: Literal['telegram', 'rss', 'website']
    url: str
    name: str
    is_active: bool = True
    fetch_interval_minutes: int = 60
    selector: Optional[dict] = None  # для website: {"title": "h1", "content": "article"}

class AnalysisConfig(BaseModel):
    summary: bool = True
    sentiment: bool = True
    ner: bool = True
    hashtags: bool = True
    deduplication: bool = True

class DeliveryConfig(BaseModel):
    frequency: Literal['instant', 'hourly', 'daily'] = 'instant'
    daily_time: Optional[str] = None  # "08:00"
    only_keywords: bool = True

class ClientConfig(BaseModel):
    client_id: str
    client_name: str
    telegram_chat_id: int
    sources: List[SourceConfig]
    keywords: List[str]
    exclude_keywords: List[str] = Field(default_factory=list)
    competitors: List[str] = Field(default_factory=list)
    analysis: AnalysisConfig = AnalysisConfig()
    delivery: DeliveryConfig = DeliveryConfig()
```

## Пример рабочего конфига (`data/clients/stroi_1/config.json`)

```json
{
  "client_id": "stroi_1",
  "client_name": "СтройКомпания",
  "telegram_chat_id": 123456789,
  "sources": [
    {"type": "telegram", "url": "@stroi_news", "name": "Строй Новости", "fetch_interval_minutes": 30},
    {"type": "rss", "url": "http://stroi.ru/rss", "name": "Stroi.ru"},
    {
      "type": "website",
      "url": "https://example.ru/news",
      "name": "Example",
      "selector": {"title": "h2.news-title", "content": "div.news-body", "date": "span.date"}
    }
  ],
  "keywords": ["остекление", "фасад", "тендер"],
  "exclude_keywords": ["реклама", "вакансия"],
  "competitors": ["ПИК", "ЛСР"],
  "analysis": {"summary": true, "sentiment": true, "ner": true, "hashtags": true},
  "delivery": {"frequency": "instant"}
}
```

## Идентификация клиента

При старте бот загружает все конфиги из `data/clients/*/config.json`, валидирует через `ClientConfig`.
Входящее сообщение → ищем `telegram_chat_id` → получаем `client_id`.
Если не найден → новый пользователь (предложить онбординг).
