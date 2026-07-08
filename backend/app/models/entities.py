from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.session import Base


def utcnow():
    return datetime.now(timezone.utc)


class Bookshelf(Base):
    __tablename__ = "bookshelves"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    topics: Mapped[list["Topic"]] = relationship("Topic", back_populates="bookshelf")


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    subtitle: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    bookshelf_id: Mapped[int | None] = mapped_column(ForeignKey("bookshelves.id"), nullable=True, index=True)
    columns_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    # Default display style for the notebook's "entry" notes; one of
    # timeline/table/board/gallery/list/outline (see note-types-and-views-design.md).
    display_style: Mapped[str] = mapped_column(String(32), default="timeline", nullable=False)
    # Container type ("数字图书馆" axis-0): notebook/book/album. Presets the offered
    # view set + default view (see docs/notes-app-pivot-design.md §4).
    container_type: Mapped[str] = mapped_column(String(32), default="notebook", nullable=False)
    # Center-column sort levels ([{field,dir},…]) and the timeline grouping
    # dimension (era/year/month), persisted per notebook for cross-device sync
    # (see docs/center-sort-design.md §12).
    sort_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    group_by: Mapped[str] = mapped_column(String(32), default="era", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    bookshelf: Mapped[Bookshelf | None] = relationship("Bookshelf", back_populates="topics")
    notes: Mapped[list["Note"]] = relationship(
        "Note", back_populates="topic", cascade="all, delete-orphan"
    )
    stats: Mapped["TopicStat | None"] = relationship(
        "TopicStat", back_populates="topic", cascade="all, delete-orphan", uselist=False
    )
    era_stats: Mapped[list["TopicEraStat"]] = relationship(
        "TopicEraStat", back_populates="topic", cascade="all, delete-orphan"
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

    notes: Mapped[list["Note"]] = relationship("Note", back_populates="image")


class Note(Base):
    __tablename__ = "notes"
    __table_args__ = (
        Index("ix_notes_topic_date_id", "topic_id", "date_key", "id"),
        Index("ix_notes_topic_year_month", "topic_id", "date_year", "date_month"),
        Index("ix_notes_topic_deleted", "topic_id", "deleted_at"),
        Index(
            "ix_notes_live_topic_date",
            "topic_id",
            "date_key",
            sqlite_where=text("deleted_at IS NULL"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
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
    # Note kind: "entry" (markdown body, default) or "mindmap" (tree in body_json).
    note_type: Mapped[str] = mapped_column(String(32), default="entry", nullable=False)
    body_markdown: Mapped[str] = mapped_column(Text, default="", nullable=False)
    preview_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    search_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Structured body interpreted per note_type; only "mindmap" uses it (tree JSON).
    body_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    attachments_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    related_note_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    image_id: Mapped[int | None] = mapped_column(ForeignKey("images.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
    favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    favorite_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    topic: Mapped[Topic] = relationship("Topic", back_populates="notes")
    image: Mapped[ImageAsset | None] = relationship("ImageAsset", back_populates="notes")
    items: Mapped[list["NoteItem"]] = relationship(
        "NoteItem",
        back_populates="note",
        cascade="all, delete-orphan",
        order_by="NoteItem.sort_order",
    )


class NoteItem(Base):
    __tablename__ = "note_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    note_id: Mapped[int] = mapped_column(ForeignKey("notes.id"), nullable=False, index=True)
    tag: Mapped[str] = mapped_column(String(64), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    note: Mapped[Note] = relationship("Note", back_populates="items")


class TopicStat(Base):
    __tablename__ = "topic_stats"

    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), primary_key=True)
    live_event_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deleted_event_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    favorite_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    image_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    topic: Mapped[Topic] = relationship("Topic", back_populates="stats")


class TopicEraStat(Base):
    __tablename__ = "topic_era_stats"
    __table_args__ = (Index("ix_topic_era_stats_topic_min_date", "topic_id", "min_date_key", "era"),)

    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), primary_key=True)
    era: Mapped[str] = mapped_column(String(255), primary_key=True)
    live_event_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    min_date_key: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    topic: Mapped[Topic] = relationship("Topic", back_populates="era_stats")


class NoteLink(Base):
    """A `[[wikilink]]` edge from one note's body to another (W4 link system).

    The link graph is keyed by note id, not title, so renaming/moving a target never
    breaks the edge (see docs/notes-app-pivot-design.md §6.1). `target_note_id` is NULL
    for a dangling link (`[[title]]` that resolves to no note yet). `context_text` is the
    surrounding line, precomputed at write time so the backlink panel never rescans source
    bodies. `anchor_type`: 'wikilink' (from body) | 'manual' (backfilled related ids) |
    'embed' (a canvas embedding the target — W5)."""

    __tablename__ = "note_links"
    __table_args__ = (
        Index("ix_note_links_target_source", "target_note_id", "source_note_id"),
        Index("ix_note_links_source", "source_note_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_note_id: Mapped[int] = mapped_column(ForeignKey("notes.id"), nullable=False, index=True)
    target_note_id: Mapped[int | None] = mapped_column(ForeignKey("notes.id"), nullable=True, index=True)
    target_title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    anchor_type: Mapped[str] = mapped_column(String(16), default="wikilink", nullable=False)
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    context_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AppConfigEntry(Base):
    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="", nullable=False)
