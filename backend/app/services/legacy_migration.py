import json
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from backend.app.core.config import CONFIG_FILE, DATA_DIR, DEFAULT_CONFIG
from backend.app.db.session import Base, engine
from backend.app.models.entities import AppConfigEntry, EventItem, ImageAsset, TimelineEvent, Topic
from backend.app.services.auth import ensure_default_admin
from backend.app.services.date_utils import (
    date_key_to_parts,
    extract_headline_from_legacy_label,
    make_date_key,
)
from backend.app.services.timeline import sanitize_topic_name


def init_database():
    Base.metadata.create_all(bind=engine)
    ensure_timeline_event_schema()


def ensure_timeline_event_schema():
    inspector = inspect(engine)
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
    if "tags_json" not in existing:
        statements.append("ALTER TABLE timeline_events ADD COLUMN tags_json TEXT DEFAULT '[]'")
    if "attachments_json" not in existing:
        statements.append("ALTER TABLE timeline_events ADD COLUMN attachments_json TEXT DEFAULT '[]'")
    if "related_event_ids_json" not in existing:
        statements.append("ALTER TABLE timeline_events ADD COLUMN related_event_ids_json TEXT DEFAULT '[]'")
    if "created_at" not in existing:
        statements.append("ALTER TABLE timeline_events ADD COLUMN created_at DATETIME")
    if "favorite" not in existing:
        statements.append("ALTER TABLE timeline_events ADD COLUMN favorite BOOLEAN DEFAULT 0 NOT NULL")
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
                    tags_json = COALESCE(tags_json, '[]'),
                    attachments_json = COALESCE(attachments_json, '[]'),
                    related_event_ids_json = COALESCE(related_event_ids_json, '[]'),
                    created_at = COALESCE(created_at, updated_at, CURRENT_TIMESTAMP),
                    favorite = COALESCE(favorite, 0)
                """
            )
        )


def migrate_legacy_files(db: Session):
    ensure_default_admin(db)

    if db.query(Topic).count() > 0:
        seed_config_if_missing(db)
        return

    seed_config_if_missing(db)

    topic_files = sorted(
        path for path in DATA_DIR.glob("*.json") if path.name not in {"config.json", "events.json"}
    )
    for path in topic_files:
        import_topic_file(db, path)


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
        db.add(AppConfigEntry(key=key, value=str(value)))
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
    )
    db.add(topic)
    db.flush()

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
            tags_json=json.dumps(
                [
                    tag
                    for tag in dict.fromkeys(
                        str(item.get("tag", "")).strip()
                        for item in node.get("events", [])
                        if str(item.get("tag", "")).strip()
                    )
                ],
                ensure_ascii=False,
            ),
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
                    tag=str(item.get("tag", "")).strip(),
                    text=str(item.get("text", "")).strip(),
                    sort_order=index,
                )
            )
    db.commit()
