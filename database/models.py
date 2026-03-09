"""
SQLAlchemy модели базы данных.

Таблицы: Client, Source, News, Settings, Feedback
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Client(Base):
    """Клиент бота (компания или пользователь)."""

    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    config_path: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    sources: Mapped[list["Source"]] = relationship(back_populates="client", cascade="all, delete-orphan")
    news: Mapped[list["News"]] = relationship(back_populates="client", cascade="all, delete-orphan")
    settings: Mapped[Optional["Settings"]] = relationship(back_populates="client", uselist=False, cascade="all, delete-orphan")
    feedback: Mapped[list["Feedback"]] = relationship(back_populates="client", cascade="all, delete-orphan")


class Source(Base):
    """Источник новостей для клиента."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(Integer, ForeignKey("clients.id"), index=True)
    type: Mapped[str] = mapped_column(String(50))  # telegram / rss / website / social
    url: Mapped[str] = mapped_column(String(1024))
    name: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_fetch: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    fetch_interval: Mapped[int] = mapped_column(Integer, default=60)  # минуты
    selector_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    client: Mapped["Client"] = relationship(back_populates="sources")
    news: Mapped[list["News"]] = relationship(back_populates="source")


class News(Base):
    """Новость — сырая и обработанная."""

    __tablename__ = "news"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(Integer, ForeignKey("clients.id"), index=True)
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("sources.id"), index=True)
    url: Mapped[str] = mapped_column(String(1024))
    title: Mapped[str] = mapped_column(String(1024))
    content: Mapped[str] = mapped_column(Text)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Результаты анализа
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sentiment: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # positive / neutral / negative
    entities: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    hashtags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    importance_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1-10
    # Служебные поля
    hash: Mapped[str] = mapped_column(String(64), index=True)  # SHA-256 контента
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_to_user: Mapped[bool] = mapped_column(Boolean, default=False)
    keyword_filtered: Mapped[bool] = mapped_column(Boolean, default=False)  # не прошла keyword-фильтр
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    client: Mapped["Client"] = relationship(back_populates="news")
    source: Mapped["Source"] = relationship(back_populates="news")
    feedback: Mapped[list["Feedback"]] = relationship(back_populates="news", cascade="all, delete-orphan")


class Settings(Base):
    """Настройки анализа и доставки для клиента."""

    __tablename__ = "settings"

    client_id: Mapped[int] = mapped_column(Integer, ForeignKey("clients.id"), primary_key=True)
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    exclude_keywords: Mapped[list] = mapped_column(JSON, default=list)
    frequency: Mapped[str] = mapped_column(String(50), default="instant")
    digest_mode: Mapped[str] = mapped_column(String(50), default="compact")  # compact / full
    analysis_flags: Mapped[dict] = mapped_column(JSON, default=dict)

    client: Mapped["Client"] = relationship(back_populates="settings")


class Feedback(Base):
    """Реакция пользователя на новость."""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(Integer, ForeignKey("clients.id"), index=True)
    news_id: Mapped[int] = mapped_column(Integer, ForeignKey("news.id"), index=True)
    reaction: Mapped[str] = mapped_column(String(50))  # like / dislike / saved
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    client: Mapped["Client"] = relationship(back_populates="feedback")
    news: Mapped["News"] = relationship(back_populates="feedback")
