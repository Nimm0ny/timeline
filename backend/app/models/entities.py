from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.session import Base


def utcnow():
    return datetime.now(timezone.utc)


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    subtitle: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    columns_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    events: Mapped[list["TimelineEvent"]] = relationship(
        "TimelineEvent", back_populates="topic", cascade="all, delete-orphan"
    )


class ImageAsset(Base):
    __tablename__ = "images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    thumb_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    original_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_orphan: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    events: Mapped[list["TimelineEvent"]] = relationship("TimelineEvent", back_populates="image")


class TimelineEvent(Base):
    __tablename__ = "timeline_events"
    __table_args__ = (
        Index("ix_timeline_events_topic_date_id", "topic_id", "date_key", "id"),
        Index("ix_timeline_events_topic_year_month", "topic_id", "date_year", "date_month"),
        Index("ix_timeline_events_topic_deleted", "topic_id", "deleted_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), nullable=False, index=True)
    year: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_key: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    date_key: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    date_year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    date_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    date_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    headline: Mapped[str | None] = mapped_column(String(255), nullable=True)
    era: Mapped[str] = mapped_column(String(255), nullable=False)
    body_markdown: Mapped[str] = mapped_column(Text, default="", nullable=False)
    extra_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    attachments_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    related_event_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    image_id: Mapped[int | None] = mapped_column(ForeignKey("images.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
    favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    topic: Mapped[Topic] = relationship("Topic", back_populates="events")
    image: Mapped[ImageAsset | None] = relationship("ImageAsset", back_populates="events")
    items: Mapped[list["EventItem"]] = relationship(
        "EventItem",
        back_populates="event",
        cascade="all, delete-orphan",
        order_by="EventItem.sort_order",
    )


class EventItem(Base):
    __tablename__ = "event_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("timeline_events.id"), nullable=False, index=True)
    tag: Mapped[str] = mapped_column(String(64), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    event: Mapped[TimelineEvent] = relationship("TimelineEvent", back_populates="items")


class AppConfigEntry(Base):
    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="", nullable=False)
