import json
import sqlite3
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateIndex, CreateTable

from backend.app.core.config import CONFIG_FILE, DATA_DIR, DB_FILE, DEFAULT_CONFIG, encode_config_value
from backend.app.db.session import Base, SessionLocal, engine
from backend.app.models.entities import AppConfigEntry, EventItem, ImageAsset, TimelineEvent, Topic
from backend.app.services.date_utils import (
    date_key_to_parts,
    extract_headline_from_legacy_label,
    make_date_key,
)
from backend.app.services.timeline import (
    DEFAULT_TOPIC_COLUMNS,
    ensure_topic_bookshelf_assignments,
    normalize_topic_columns,
    sanitize_topic_name,
)

# Default tag label/color seed (ported from ui/src/constants/tags.js). Used to
# give migrated tag options friendly labels and palette colors; after migration,
# labels/colors live in each topic's "tags" property options.
TAG_SEED = {
    "war": ("战争", "var(--t-war)"),
    "politics": ("政治", "var(--t-politics)"),
    "culture": ("文化", "var(--t-culture)"),
    "science": ("科技", "var(--t-science)"),
    "explore": ("探索", "var(--t-science)"),
    "disaster": ("灾难", "var(--t-war)"),
    "reform": ("改革", "var(--t-reform)"),
    "diplomacy": ("外交", "var(--t-diplomacy)"),
    "economy": ("经济", "var(--t-economy)"),
}
# Palette tokens for tag values not present in TAG_SEED.
TAG_PALETTE = [
    "var(--t-war)", "var(--t-politics)", "var(--t-culture)",
    "var(--t-science)", "var(--t-reform)", "var(--t-diplomacy)", "var(--t-economy)",
]


def build_tag_options(values: list[str]) -> list[dict]:
    """Turn distinct tag values into option defs (id = original value)."""
    options = []
    for index, value in enumerate(dict.fromkeys(v for v in values if v)):
        label, color = TAG_SEED.get(value, (value, TAG_PALETTE[index % len(TAG_PALETTE)]))
        options.append({"id": value, "label": label, "color": color})
    return options


def init_database():
    Base.metadata.create_all(bind=engine)
    ensure_image_asset_schema()
    ensure_timeline_event_schema()
    migrate_to_property_model()
    drop_legacy_auth_artifacts()


def ensure_image_asset_schema():
    inspector = inspect(engine)
    if "images" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("images")}
    statements = []
    if "content_hash" not in existing:
        statements.append("ALTER TABLE images ADD COLUMN content_hash VARCHAR(64)")
    if "thumb_filename" not in existing:
        statements.append("ALTER TABLE images ADD COLUMN thumb_filename VARCHAR(255)")
    if "original_filename" not in existing:
        statements.append("ALTER TABLE images ADD COLUMN original_filename VARCHAR(255)")
    if "width" not in existing:
        statements.append("ALTER TABLE images ADD COLUMN width INTEGER")
    if "height" not in existing:
        statements.append("ALTER TABLE images ADD COLUMN height INTEGER")
    if "bytes" not in existing:
        statements.append("ALTER TABLE images ADD COLUMN bytes INTEGER")

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        connection.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS ix_images_content_hash ON images(content_hash)")
        )


def ensure_timeline_event_schema():
    inspector = inspect(engine)
    topic_columns = set()
    if "topics" in inspector.get_table_names():
        topic_columns = {column["name"] for column in inspector.get_columns("topics")}
        topic_statements = []
        if "bookshelf_id" not in topic_columns:
            topic_statements.append("ALTER TABLE topics ADD COLUMN bookshelf_id INTEGER")
        if "columns_json" not in topic_columns:
            topic_statements.append("ALTER TABLE topics ADD COLUMN columns_json TEXT DEFAULT '[]'")
        if "display_style" not in topic_columns:
            topic_statements.append("ALTER TABLE topics ADD COLUMN display_style VARCHAR(32) DEFAULT 'timeline'")
        if "sort_json" not in topic_columns:
            topic_statements.append("ALTER TABLE topics ADD COLUMN sort_json TEXT DEFAULT '[]'")
        if "group_by" not in topic_columns:
            topic_statements.append("ALTER TABLE topics ADD COLUMN group_by VARCHAR(32) DEFAULT 'era'")
        if topic_statements:
            with engine.begin() as connection:
                for statement in topic_statements:
                    connection.execute(text(statement))
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_topics_bookshelf_id ON topics(bookshelf_id)"))

    if "timeline_events" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("timeline_events")}
    statements = []
    if "date_key" not in existing:
        statements.append("ALTER TABLE timeline_events ADD COLUMN date_key INTEGER")
    if "date_year" not in existing:
        statements.append("ALTER TABLE timeline_events ADD COLUMN date_year INTEGER")
    if "date_month" not in existing:
        statements.append("ALTER TABLE timeline_events ADD COLUMN date_month INTEGER")
    if "date_day" not in existing:
        statements.append("ALTER TABLE timeline_events ADD COLUMN date_day INTEGER")
    if "headline" not in existing:
        statements.append("ALTER TABLE timeline_events ADD COLUMN headline VARCHAR(255)")
    if "body_markdown" not in existing:
        statements.append("ALTER TABLE timeline_events ADD COLUMN body_markdown TEXT DEFAULT ''")
    if "extra_json" not in existing:
        statements.append("ALTER TABLE timeline_events ADD COLUMN extra_json TEXT DEFAULT '{}'")
    if "attachments_json" not in existing:
        statements.append("ALTER TABLE timeline_events ADD COLUMN attachments_json TEXT DEFAULT '[]'")
    if "related_event_ids_json" not in existing:
        statements.append("ALTER TABLE timeline_events ADD COLUMN related_event_ids_json TEXT DEFAULT '[]'")
    if "note_type" not in existing:
        statements.append("ALTER TABLE timeline_events ADD COLUMN note_type VARCHAR(32) DEFAULT 'entry'")
    if "body_json" not in existing:
        statements.append("ALTER TABLE timeline_events ADD COLUMN body_json TEXT")
    if "created_at" not in existing:
        statements.append("ALTER TABLE timeline_events ADD COLUMN created_at DATETIME")
    if "favorite" not in existing:
        statements.append("ALTER TABLE timeline_events ADD COLUMN favorite BOOLEAN DEFAULT 0 NOT NULL")
    if "favorite_at" not in existing:
        statements.append("ALTER TABLE timeline_events ADD COLUMN favorite_at DATETIME")
    if "deleted_at" not in existing:
        statements.append("ALTER TABLE timeline_events ADD COLUMN deleted_at DATETIME")

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_timeline_events_date_key ON timeline_events(date_key)")
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_timeline_events_date_year ON timeline_events(date_year)")
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_timeline_events_topic_date_id "
                "ON timeline_events(topic_id, date_key, id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_timeline_events_topic_year_month "
                "ON timeline_events(topic_id, date_year, date_month)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_timeline_events_topic_deleted "
                "ON timeline_events(topic_id, deleted_at)"
            )
        )
        connection.execute(
            text(
                """
                UPDATE timeline_events
                SET date_key = date_year * 10000 + date_month * 100 + date_day,
                    sort_key = date_year * 10000 + date_month * 100 + date_day
                WHERE date_year < 0
                  AND date_month IS NOT NULL
                  AND date_day IS NOT NULL
                  AND date_key != date_year * 10000 + date_month * 100 + date_day
                """
            )
        )
        backfill_rows = connection.execute(
            text(
                """
                SELECT id, year, sort_key, date_key, date_year, date_month, date_day, headline
                FROM timeline_events
                WHERE date_key IS NULL OR date_year IS NULL OR date_month IS NULL OR date_day IS NULL OR headline IS NULL
                """
            )
        ).mappings()
        for row in backfill_rows:
            sort_key = int(round(float(row["sort_key"] or 0)))
            raw_digits = abs(sort_key)
            year = raw_digits // 10000
            month = (raw_digits // 100) % 100
            day = raw_digits % 100
            if sort_key < 0:
                year *= -1
            date_key = make_date_key(year, month, day)
            headline = extract_headline_from_legacy_label(row["year"] or "", fallback="")
            connection.execute(
                text(
                    """
                    UPDATE timeline_events
                    SET date_key = :date_key,
                        date_year = :date_year,
                        date_month = :date_month,
                        date_day = :date_day,
                        headline = :headline
                    WHERE id = :event_id
                    """
                ),
                {
                    "event_id": row["id"],
                    "date_key": date_key,
                    "date_year": year,
                    "date_month": month,
                    "date_day": day,
                    "headline": headline,
                },
            )
        connection.execute(
            text(
                """
                UPDATE timeline_events
                SET body_markdown = COALESCE(body_markdown, ''),
                    extra_json = COALESCE(extra_json, '{}'),
                    attachments_json = COALESCE(attachments_json, '[]'),
                    related_event_ids_json = COALESCE(related_event_ids_json, '[]'),
                    created_at = COALESCE(created_at, updated_at, CURRENT_TIMESTAMP),
                    favorite = COALESCE(favorite, 0),
                    favorite_at = CASE
                        WHEN COALESCE(favorite, 0) = 1 THEN COALESCE(favorite_at, updated_at, created_at, CURRENT_TIMESTAMP)
                        ELSE NULL
                    END
                """
            )
        )
        if "topics" in inspector.get_table_names():
            connection.execute(text("UPDATE topics SET columns_json = COALESCE(columns_json, '[]')"))


def drop_legacy_auth_artifacts():
    """Auth was removed (single-user / local-first). Drop the now-orphaned `users`
    table and the `created_by`/`uploaded_by` FK columns so existing DBs match the
    auth-free models. SQLite refuses to ALTER-DROP a column named in a foreign key,
    so those two tables are rebuilt from the clean ORM definition."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    # Rebuild the FK-bearing tables first, then drop `users` last, so a mid-way
    # failure never leaves `users` gone while the orphan columns remain.
    if "timeline_events" in tables and "created_by" in {c["name"] for c in inspector.get_columns("timeline_events")}:
        rebuild_table_from_model(TimelineEvent.__table__)
    if "images" in tables and "uploaded_by" in {c["name"] for c in inspector.get_columns("images")}:
        rebuild_table_from_model(ImageAsset.__table__)

    if "users" in tables:
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE users"))


def rebuild_table_from_model(table):
    """Rebuild a SQLite table in place from its (clean) ORM definition: rename the
    old table, recreate it without the dropped columns, copy rows, drop the old one,
    recreate indexes. `legacy_alter_table=ON` keeps other tables' foreign keys
    pointing at the original name during the rename; the PRAGMAs run outside the
    transaction as SQLite requires."""
    name = table.name
    columns = ", ".join(f'"{column.name}"' for column in table.columns)
    create_table_sql = str(CreateTable(table).compile(dialect=engine.dialect)).strip()
    create_index_sql = [str(CreateIndex(index).compile(dialect=engine.dialect)).strip() for index in table.indexes]

    connection = sqlite3.connect(str(DB_FILE))
    connection.isolation_level = None
    try:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("PRAGMA legacy_alter_table=ON")
        connection.execute("BEGIN")
        connection.execute(f'ALTER TABLE "{name}" RENAME TO "_rebuild_{name}"')
        connection.execute(create_table_sql)
        connection.execute(f'INSERT INTO "{name}" ({columns}) SELECT {columns} FROM "_rebuild_{name}"')
        connection.execute(f'DROP TABLE "_rebuild_{name}"')
        for statement in create_index_sql:
            connection.execute(statement)
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.execute("PRAGMA legacy_alter_table=OFF")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.close()


def _safe_list(value):
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _safe_dict(value):
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def ensure_seed_columns(topic: Topic, tag_options: list[dict]) -> list[dict]:
    """Guarantee the topic has the default type/tags properties, and fold the
    migrated tag options into the tags property (never clobbering existing ones)."""
    columns = normalize_topic_columns(_safe_list(topic.columns_json))
    by_key = {column["key"]: column for column in columns}
    for seed in DEFAULT_TOPIC_COLUMNS:
        if seed["key"] not in by_key:
            seeded = {**seed, "options": list(seed.get("options") or [])}
            columns.append(seeded)
            by_key[seed["key"]] = seeded

    tags_column = by_key.get("tags")
    if tags_column is not None and tags_column.get("type") == "multiselect":
        merged = {option["id"]: option for option in (tags_column.get("options") or [])}
        for option in tag_options:
            merged.setdefault(option["id"], option)
        tags_column["options"] = list(merged.values())
    return normalize_topic_columns(columns)


def migrate_to_property_model():
    """One-time, idempotent migration to the unified property model. Historical
    tag values (tags_json + EventItem.tag) become a multiselect `tags` property
    whose options live on the topic, with each event's values in extra_json. The
    `type` property stays empty — it was a derived view, never real data, so we
    do not fabricate it. Idempotency signal: the tags_json column; once dropped,
    this is a no-op."""
    inspector = inspect(engine)
    if "timeline_events" not in inspector.get_table_names():
        return
    if "tags_json" not in {column["name"] for column in inspector.get_columns("timeline_events")}:
        return  # already migrated

    session = SessionLocal()
    try:
        raw_tags = {
            row[0]: _safe_list(row[1])
            for row in session.execute(text("SELECT id, tags_json FROM timeline_events")).all()
        }
        for topic in session.query(Topic).all():
            events = session.query(TimelineEvent).filter(TimelineEvent.topic_id == topic.id).all()
            per_event_tags: dict[int, list[str]] = {}
            topic_tag_values: list[str] = []
            for event in events:
                values: list[str] = []
                sources = [str(value).strip() for value in raw_tags.get(event.id, [])]
                sources += [str(item.tag).strip() for item in event.items]
                for value in sources:
                    if value and value not in values:
                        values.append(value)
                per_event_tags[event.id] = values
                for value in values:
                    if value not in topic_tag_values:
                        topic_tag_values.append(value)

            topic.columns_json = json.dumps(
                ensure_seed_columns(topic, build_tag_options(topic_tag_values)), ensure_ascii=False
            )
            for event in events:
                extra = _safe_dict(event.extra_json)
                extra["tags"] = per_event_tags.get(event.id, [])
                event.extra_json = json.dumps(extra, ensure_ascii=False)
        session.commit()
    finally:
        session.close()

    # Tag values now live in extra_json; drop the orphaned column to match the
    # clean model (SQLite can't ALTER-DROP, so rebuild from the ORM definition).
    rebuild_table_from_model(TimelineEvent.__table__)


def migrate_legacy_files(db: Session):
    if db.query(Topic).count() > 0:
        seed_config_if_missing(db)
        if ensure_topic_bookshelf_assignments(db):
            db.commit()
        return

    seed_config_if_missing(db)

    topic_files = sorted(
        path for path in DATA_DIR.glob("*.json") if path.name not in {"config.json", "events.json"}
    )
    for path in topic_files:
        import_topic_file(db, path)
    if ensure_topic_bookshelf_assignments(db):
        db.commit()


def seed_config_if_missing(db: Session):
    if db.query(AppConfigEntry).count() > 0:
        return
    payload = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            payload.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    for key, value in payload.items():
        db.add(AppConfigEntry(key=key, value=encode_config_value(value)))
    db.commit()


def import_topic_file(db: Session, path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        title = path.stem
        subtitle = ""
        events = data
    else:
        title = data.get("title", path.stem)
        subtitle = data.get("subtitle", "")
        events = data.get("events", [])

    topic = Topic(
        name=sanitize_topic_name(path.stem) or path.stem,
        title=str(title or "").strip(),
        subtitle=str(subtitle or "").strip(),
        columns_json=json.dumps(DEFAULT_TOPIC_COLUMNS, ensure_ascii=False),
    )
    db.add(topic)
    db.flush()

    all_tag_values: list[str] = []
    for node in events:
        image_name = (node.get("image") or "").strip() if isinstance(node, dict) else ""
        image = None
        if image_name:
            image = db.query(ImageAsset).filter(ImageAsset.filename == image_name).first()
            if image is None:
                image = ImageAsset(filename=image_name, original_name=image_name, mime_type=None, is_orphan=False)
                db.add(image)
                db.flush()
            image.is_orphan = False

        sort_key = int(round(float(node.get("sortKey", 0))))
        date_year, date_month, date_day = date_key_to_parts(sort_key)
        headline = extract_headline_from_legacy_label(str(node.get("year", "")).strip())
        event_tags = [
            tag
            for tag in dict.fromkeys(
                str(item.get("tag", "")).strip()
                for item in node.get("events", [])
                if str(item.get("tag", "")).strip()
            )
        ]
        for tag in event_tags:
            if tag not in all_tag_values:
                all_tag_values.append(tag)

        event = TimelineEvent(
            topic_id=topic.id,
            year=str(node.get("year", "")).strip(),
            sort_key=float(sort_key),
            date_key=sort_key,
            date_year=date_year,
            date_month=date_month,
            date_day=date_day,
            headline=headline,
            era=str(node.get("era", "")).strip(),
            body_markdown="\n\n".join(str(item.get("text", "")).strip() for item in node.get("events", []) if str(item.get("text", "")).strip()),
            extra_json=json.dumps({"tags": event_tags}, ensure_ascii=False),
            attachments_json="[]",
            related_event_ids_json="[]",
            image=image,
        )
        db.add(event)
        db.flush()
        for index, item in enumerate(node.get("events", [])):
            db.add(
                EventItem(
                    event_id=event.id,
                    tag=str(item.get("tag", "")).strip() or "note",
                    text=str(item.get("text", "")).strip(),
                    sort_order=index,
                )
            )

    topic.columns_json = json.dumps(ensure_seed_columns(topic, build_tag_options(all_tag_values)), ensure_ascii=False)
    db.commit()
