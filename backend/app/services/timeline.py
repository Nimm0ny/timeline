import json
import mimetypes
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException, UploadFile
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from backend.app.core.config import CONFIG_FILE, DEFAULT_CONFIG, IMAGES_DIR, THEME_DIR
from backend.app.models.entities import AppConfigEntry, EventItem, ImageAsset, TimelineEvent, Topic, User
from backend.app.services.date_utils import (
    build_display_label,
    date_key_to_iso,
    date_key_to_parts,
    extract_headline_from_legacy_label,
    make_date_key,
    parse_date_key,
    validate_date_parts,
)

SUPPORTED_ZOOM_LEVELS = ["year", "month", "day"]
EVENT_STATE_KEYS = {"favorite", "deletedAt"}


def sanitize_topic_name(name: str) -> str:
    return "".join(c for c in name.strip() if c.isalnum() or c in "_-\u4e00-\u9fff")


def topic_to_dict(topic: Topic) -> dict:
    return {
        "id": topic.id,
        "name": topic.name,
        "title": topic.title or "",
        "subtitle": topic.subtitle or "",
        "updatedAt": topic.updated_at.isoformat() if topic.updated_at else None,
    }


def parse_query_date_key(value: str | None, *, is_end: bool = False) -> int | None:
    try:
        return parse_date_key(value, is_end=is_end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def normalize_date_key(value: float | int | str | None) -> int:
    if value is None:
        raise HTTPException(status_code=400, detail="Missing date key")
    try:
        return int(round(float(value)))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid date key") from exc


def serialize_datetime(value) -> str | None:
    return value.isoformat() if value else None


def parse_optional_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.lower() == "now":
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid deletedAt datetime") from exc


def apply_event_state(event: TimelineEvent, payload: dict):
    if "favorite" in payload:
        event.favorite = bool(payload.get("favorite"))
    if "deletedAt" in payload:
        event.deleted_at = parse_optional_datetime(payload.get("deletedAt"))


def parse_cursor_token(value: str | None) -> tuple[int, int | None] | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if ":" not in raw:
        return parse_query_date_key(raw), None
    left, right = raw.split(":", 1)
    cursor_key = parse_query_date_key(left)
    try:
        cursor_id = int(right)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid cursor id") from exc
    return cursor_key, cursor_id


def event_display_label(event: TimelineEvent) -> str:
    if event.date_key is None:
        return event.year
    return build_display_label(
        event.date_year or 0,
        event.date_month or 1,
        event.date_day or 1,
        event.headline or "",
    )


def serialize_items(event: TimelineEvent) -> list[dict]:
    return [{"tag": item.tag, "text": item.text} for item in sorted(event.items, key=lambda value: value.sort_order)]


def deserialize_json_list(value: str | None, *, fallback: list | None = None) -> list:
    if value is None:
        return fallback[:] if fallback is not None else []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return fallback[:] if fallback is not None else []
    return parsed if isinstance(parsed, list) else (fallback[:] if fallback is not None else [])


def default_body_markdown(items: list[dict]) -> str:
    lines = []
    for item in items:
        text = str(item.get("text", "")).strip()
        if text:
            lines.append(text)
    return "\n\n".join(lines)


def normalize_tags(payload: dict, items: list[dict]) -> list[str]:
    raw = payload.get("tags")
    if isinstance(raw, list):
        tags = [str(tag).strip() for tag in raw if str(tag).strip()]
        return list(dict.fromkeys(tags))
    return list(dict.fromkeys(item["tag"] for item in items if item["tag"]))


def normalize_attachments(payload: dict) -> list[dict]:
    raw = payload.get("attachments") or []
    if not isinstance(raw, list):
        raise HTTPException(status_code=400, detail="Attachments must be an array")

    attachments = []
    for item in raw:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="Each attachment must be an object")
        filename = str(item.get("filename", "")).strip()
        name = str(item.get("name", "")).strip()
        mime_type = str(item.get("mimeType", "")).strip() or None
        if not filename or not name:
            raise HTTPException(status_code=400, detail="Attachment requires filename and name")
        attachments.append(
            {
                "id": item.get("id"),
                "name": name,
                "filename": filename,
                "mimeType": mime_type,
            }
        )
    return attachments


def normalize_related_event_ids(payload: dict) -> list[int]:
    raw = payload.get("relatedEventIds") or []
    if not isinstance(raw, list):
        raise HTTPException(status_code=400, detail="Related events must be an array")
    ids = []
    for value in raw:
        try:
            event_id = int(value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Related event ids must be integers") from exc
        if event_id > 0:
            ids.append(event_id)
    return list(dict.fromkeys(ids))


def build_attachment_payload(attachment: dict) -> dict:
    filename = attachment["filename"]
    mime_type = attachment.get("mimeType")
    image_url = f"/images/{filename}" if (mime_type or "").startswith("image/") else None
    return {
        "id": attachment.get("id"),
        "name": attachment["name"],
        "filename": filename,
        "mimeType": mime_type,
        "url": f"/images/{filename}",
        "imageUrl": image_url,
    }


def event_to_dict(event: TimelineEvent, related_lookup: dict[int, dict] | None = None) -> dict:
    date_key = event.date_key or normalize_date_key(event.sort_key)
    date_year, date_month, date_day = date_key_to_parts(date_key)
    headline = (event.headline or "").strip() or extract_headline_from_legacy_label(event.year or "")
    image_filename = event.image.filename if event.image else None
    items = serialize_items(event)
    tags = deserialize_json_list(event.tags_json, fallback=[item["tag"] for item in items if item["tag"]])
    attachments = [build_attachment_payload(item) for item in deserialize_json_list(event.attachments_json)]
    related_ids = [int(value) for value in deserialize_json_list(event.related_event_ids_json) if str(value).strip().isdigit()]
    return {
        "id": event.id,
        "nodeType": "event",
        "dateKey": date_key,
        "sortKey": event.sort_key,
        "isoDate": date_key_to_iso(date_key),
        "dateParts": {
            "year": date_year,
            "month": date_month,
            "day": date_day,
        },
        "headline": headline,
        "displayLabel": build_display_label(date_year, date_month, date_day, headline),
        "legacyYear": event.year,
        "era": event.era,
        "image": image_filename,
        "imageUrl": f"/images/{image_filename}" if image_filename else None,
        "bodyMarkdown": event.body_markdown or default_body_markdown(items),
        "tags": tags,
        "attachments": attachments,
        "relatedEventIds": related_ids,
        "relatedEvents": [related_lookup[event_id] for event_id in related_ids if related_lookup and event_id in related_lookup],
        "createdAt": serialize_datetime(event.created_at),
        "updatedAt": serialize_datetime(event.updated_at),
        "favorite": bool(event.favorite),
        "deletedAt": serialize_datetime(event.deleted_at),
        "items": items,
    }


def event_to_legacy_dict(event: TimelineEvent) -> dict:
    payload = event_to_dict(event)
    return {
        "id": payload["id"],
        "year": payload["displayLabel"],
        "sortKey": payload["dateKey"],
        "era": payload["era"],
        "image": payload["image"],
        "events": payload["items"],
    }


def build_related_lookup(db: Session, event_rows: list[TimelineEvent]) -> dict[int, dict]:
    related_ids = set()
    for event in event_rows:
        for value in deserialize_json_list(event.related_event_ids_json):
            try:
                related_ids.add(int(value))
            except (TypeError, ValueError):
                continue

    if not related_ids:
        return {}

    related_rows = (
        db.query(TimelineEvent)
        .filter(TimelineEvent.id.in_(related_ids))
        .order_by(TimelineEvent.date_key.asc(), TimelineEvent.id.asc())
        .all()
    )
    lookup = {}
    for row in related_rows:
        date_key = row.date_key or normalize_date_key(row.sort_key)
        year, month, day = date_key_to_parts(date_key)
        headline = (row.headline or "").strip() or extract_headline_from_legacy_label(row.year or "")
        lookup[row.id] = {
            "id": row.id,
            "headline": headline,
            "displayLabel": build_display_label(year, month, day, headline),
        }
    return lookup


def serialize_event_rows(db: Session, rows: list[TimelineEvent], *, legacy: bool = False) -> list[dict]:
    if legacy:
        return [event_to_legacy_dict(event) for event in rows]
    related_lookup = build_related_lookup(db, rows)
    return [event_to_dict(event, related_lookup) for event in rows]


def get_topic_or_404(db: Session, topic_id: int) -> Topic:
    topic = db.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    return topic


def get_event_or_404(db: Session, event_id: int) -> TimelineEvent:
    event = (
        db.query(TimelineEvent)
        .options(selectinload(TimelineEvent.items), joinedload(TimelineEvent.image))
        .filter(TimelineEvent.id == event_id)
        .first()
    )
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


def build_topic_bounds(db: Session, topic_id: int) -> dict:
    row = (
        db.query(
            func.count(TimelineEvent.id),
            func.min(TimelineEvent.date_key),
            func.max(TimelineEvent.date_key),
        )
        .filter(TimelineEvent.topic_id == topic_id)
        .one()
    )
    event_count = int(row[0] or 0)
    min_date_key = int(row[1]) if row[1] is not None else None
    max_date_key = int(row[2]) if row[2] is not None else None
    return {
        "eventCount": event_count,
        "minDateKey": min_date_key,
        "maxDateKey": max_date_key,
        "minDate": date_key_to_iso(min_date_key) if min_date_key is not None else None,
        "maxDate": date_key_to_iso(max_date_key) if max_date_key is not None else None,
        "supportedZoomLevels": SUPPORTED_ZOOM_LEVELS,
    }


def list_topics(db: Session) -> list[dict]:
    rows = (
        db.query(
            Topic,
            func.count(TimelineEvent.id).label("event_count"),
            func.min(TimelineEvent.date_key).label("min_date_key"),
            func.max(TimelineEvent.date_key).label("max_date_key"),
        )
        .outerjoin(TimelineEvent, TimelineEvent.topic_id == Topic.id)
        .group_by(Topic.id)
        .order_by(Topic.id.asc())
        .all()
    )
    items = []
    for topic, event_count, min_date_key, max_date_key in rows:
        items.append(
            {
                **topic_to_dict(topic),
                "eventCount": int(event_count or 0),
                "minDateKey": int(min_date_key) if min_date_key is not None else None,
                "maxDateKey": int(max_date_key) if max_date_key is not None else None,
                "minDate": date_key_to_iso(int(min_date_key)) if min_date_key is not None else None,
                "maxDate": date_key_to_iso(int(max_date_key)) if max_date_key is not None else None,
            }
        )
    return items


def create_topic(db: Session, name: str) -> dict:
    safe = sanitize_topic_name(name)
    if not safe:
        raise HTTPException(status_code=400, detail="Invalid topic name")
    exists = db.query(Topic).filter(Topic.name == safe).first()
    if exists:
        raise HTTPException(status_code=409, detail="Topic already exists")
    topic = Topic(name=safe, title=safe, subtitle="")
    db.add(topic)
    db.commit()
    db.refresh(topic)
    return topic_to_dict(topic)


def delete_topic(db: Session, topic_id: int):
    topic = get_topic_or_404(db, topic_id)
    events = (
        db.query(TimelineEvent)
        .options(joinedload(TimelineEvent.image))
        .filter(TimelineEvent.topic_id == topic_id)
        .all()
    )
    image_ids = {event.image_id for event in events if event.image_id}
    db.delete(topic)
    db.commit()
    cleanup_orphan_images(db, image_ids)
    return {"ok": True}


def get_topic_meta(db: Session, topic_id: int) -> dict:
    topic = get_topic_or_404(db, topic_id)
    return {**topic_to_dict(topic), **build_topic_bounds(db, topic_id)}


def update_topic_meta(db: Session, topic_id: int, payload: dict) -> dict:
    topic = get_topic_or_404(db, topic_id)
    if "title" in payload:
        topic.title = str(payload["title"] or "").strip()
    if "subtitle" in payload:
        topic.subtitle = str(payload["subtitle"] or "").strip()
    db.commit()
    db.refresh(topic)
    return get_topic_meta(db, topic_id)


def build_event_query(db: Session, topic_id: int):
    return (
        db.query(TimelineEvent)
        .options(selectinload(TimelineEvent.items), joinedload(TimelineEvent.image))
        .filter(TimelineEvent.topic_id == topic_id)
    )


def list_topic_events(db: Session, topic_id: int, *, legacy: bool = False) -> list[dict]:
    get_topic_or_404(db, topic_id)
    events = build_event_query(db, topic_id).order_by(TimelineEvent.date_key.asc(), TimelineEvent.id.asc()).all()
    return serialize_event_rows(db, events, legacy=legacy)


def query_topic_events(
    db: Session,
    topic_id: int,
    *,
    from_key: int | None = None,
    to_key: int | None = None,
    cursor: tuple[int, int | None] | None = None,
    limit: int | None = None,
    legacy: bool = False,
) -> dict:
    get_topic_or_404(db, topic_id)
    bounds = build_topic_bounds(db, topic_id)
    query = build_event_query(db, topic_id)

    if from_key is not None:
        query = query.filter(TimelineEvent.date_key >= from_key)
    if to_key is not None:
        query = query.filter(TimelineEvent.date_key <= to_key)
    if cursor is not None:
        cursor_key, cursor_id = cursor
        if cursor_id is None:
            query = query.filter(TimelineEvent.date_key > cursor_key)
        else:
            query = query.filter(
                or_(
                    TimelineEvent.date_key > cursor_key,
                    and_(TimelineEvent.date_key == cursor_key, TimelineEvent.id > cursor_id),
                )
            )

    query = query.order_by(TimelineEvent.date_key.asc(), TimelineEvent.id.asc())
    if limit is not None:
        query = query.limit(limit + 1)

    rows = query.all()
    has_more = False
    next_cursor = None

    if limit is not None and len(rows) > limit:
        has_more = True
        rows = rows[:limit]

    if rows and has_more:
        last_row = rows[-1]
        next_cursor = f"{last_row.date_key}:{last_row.id}"

    return {
        "items": serialize_event_rows(db, rows, legacy=legacy),
        "bounds": bounds,
        "range": {
            "from": from_key,
            "to": to_key,
            "cursor": cursor[0] if cursor else None,
            "limit": limit,
        },
        "hasMore": has_more,
        "nextCursor": next_cursor,
    }


def format_bucket_label(group_by: str, bucket_key: int) -> str:
    if group_by == "year":
        return str(bucket_key)
    year = bucket_key // 100
    month = bucket_key - year * 100
    sign = "-" if year < 0 else ""
    return f"{sign}{abs(year):04d}-{month:02d}"


def summary_node_from_row(group_by: str, row) -> dict:
    bucket_key = int(row.bucket_key)
    range_start_key = int(row.range_start_key)
    range_end_key = int(row.range_end_key)
    event_count = int(row.event_count or 0)
    label = format_bucket_label(group_by, bucket_key)
    return {
        "id": f"{group_by}:{bucket_key}",
        "nodeType": "summary",
        "groupBy": group_by,
        "bucketKey": bucket_key,
        "displayLabel": label,
        "headline": label,
        "sortKey": range_start_key,
        "dateKey": range_start_key,
        "rangeStartKey": range_start_key,
        "rangeEndKey": range_end_key,
        "rangeStartDate": date_key_to_iso(range_start_key),
        "rangeEndDate": date_key_to_iso(range_end_key),
        "eventCount": event_count,
        "era": f"{event_count} events",
        "image": None,
        "items": [
            {
                "tag": "summary",
                "text": f"{event_count} events between {date_key_to_iso(range_start_key)} and {date_key_to_iso(range_end_key)}",
            }
        ],
    }


def summarize_topic_events(
    db: Session,
    topic_id: int,
    *,
    group_by: str,
    from_key: int | None = None,
    to_key: int | None = None,
) -> dict:
    get_topic_or_404(db, topic_id)
    bounds = build_topic_bounds(db, topic_id)

    if group_by == "year":
        bucket_expr = TimelineEvent.date_year
    elif group_by == "month":
        bucket_expr = TimelineEvent.date_year * 100 + TimelineEvent.date_month
    else:
        raise HTTPException(status_code=400, detail="groupBy must be 'year' or 'month'")

    query = db.query(
        bucket_expr.label("bucket_key"),
        func.count(TimelineEvent.id).label("event_count"),
        func.min(TimelineEvent.date_key).label("range_start_key"),
        func.max(TimelineEvent.date_key).label("range_end_key"),
    ).filter(TimelineEvent.topic_id == topic_id)

    if from_key is not None:
        query = query.filter(TimelineEvent.date_key >= from_key)
    if to_key is not None:
        query = query.filter(TimelineEvent.date_key <= to_key)

    rows = query.group_by(bucket_expr).order_by(bucket_expr.asc()).all()
    return {
        "items": [summary_node_from_row(group_by, row) for row in rows],
        "bounds": bounds,
        "groupBy": group_by,
        "range": {
            "from": from_key,
            "to": to_key,
        },
    }


def resolve_image(db: Session, image_name: str | None) -> ImageAsset | None:
    if image_name is None:
        return None
    filename = str(image_name).strip()
    if not filename:
        return None
    image = db.query(ImageAsset).filter(ImageAsset.filename == filename).first()
    if image is None:
        raise HTTPException(status_code=400, detail=f"Image not found: {filename}")
    image.is_orphan = False
    return image


def derive_items_from_markdown(body_markdown: str, default_tag: str) -> list[dict]:
    chunks = [segment.strip() for segment in str(body_markdown or "").split("\n\n") if segment.strip()]
    if not chunks:
        return []
    return [{"tag": default_tag, "text": chunk} for chunk in chunks]


def normalize_event_items(payload: dict, body_markdown: str | None = None, tags: list[str] | None = None) -> list[dict]:
    raw_items = payload.get("items")
    if raw_items is None:
        raw_items = payload.get("events")
    raw_items = raw_items or []
    if not isinstance(raw_items, list):
        raise HTTPException(status_code=400, detail="Event items must be an array")

    if len(raw_items) == 0:
        fallback_tag = (tags or ["politics"])[0]
        derived = derive_items_from_markdown(body_markdown or "", fallback_tag)
        if derived:
          return derived
        raise HTTPException(status_code=400, detail="Event items are required")

    items = []
    for item in raw_items:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="Each event item must be an object")
        tag = str(item.get("tag", "")).strip()
        text = str(item.get("text", "")).strip()
        if not tag or not text:
            raise HTTPException(status_code=400, detail="Each event item requires tag and text")
        items.append({"tag": tag, "text": text})
    return items


def normalize_event_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload must be an object")

    image = payload.get("image")
    era = str(payload.get("era", "")).strip()
    if not era:
        raise HTTPException(status_code=400, detail="Era is required")
    body_markdown = str(payload.get("bodyMarkdown", "")).strip()
    tags = normalize_tags(payload, normalize_event_items(payload, body_markdown, []))
    items = normalize_event_items(payload, body_markdown, tags)
    attachments = normalize_attachments(payload)
    related_event_ids = normalize_related_event_ids(payload)
    state = {}
    if "favorite" in payload:
        state["favorite"] = bool(payload.get("favorite"))
    if "deletedAt" in payload:
        state["deletedAt"] = parse_optional_datetime(payload.get("deletedAt"))

    if {"dateYear", "dateMonth", "dateDay", "headline"} & set(payload.keys()):
        try:
            year = int(payload.get("dateYear"))
            month = int(payload.get("dateMonth"))
            day = int(payload.get("dateDay"))
            validate_date_parts(year, month, day)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        headline = str(payload.get("headline", "")).strip()
        if not headline:
            raise HTTPException(status_code=400, detail="Headline is required")
        date_key = make_date_key(year, month, day)
        legacy_year = build_display_label(year, month, day, headline)
        return {
            "dateYear": year,
            "dateMonth": month,
            "dateDay": day,
            "dateKey": date_key,
            "sortKey": float(date_key),
            "headline": headline,
            "legacyYear": legacy_year,
            "era": era,
            "bodyMarkdown": body_markdown or default_body_markdown(items),
            "tags": tags,
            "attachments": attachments,
            "relatedEventIds": related_event_ids,
            "items": items,
            "image": image,
            **state,
        }

    legacy_year = str(payload.get("year", "")).strip()
    try:
        date_key = normalize_date_key(payload.get("sortKey"))
    except HTTPException as exc:
        raise HTTPException(status_code=400, detail="Legacy payload requires sortKey") from exc
    year, month, day = date_key_to_parts(date_key)
    headline = extract_headline_from_legacy_label(legacy_year)
    return {
        "dateYear": year,
        "dateMonth": month,
        "dateDay": day,
        "dateKey": date_key,
        "sortKey": float(date_key),
        "headline": headline,
        "legacyYear": legacy_year or build_display_label(year, month, day, headline),
        "era": era,
        "bodyMarkdown": body_markdown or default_body_markdown(items),
        "tags": tags,
        "attachments": attachments,
        "relatedEventIds": related_event_ids,
        "items": items,
        "image": image,
        **state,
    }


def write_event_model(event: TimelineEvent, data: dict, image: ImageAsset | None):
    event.year = data["legacyYear"]
    event.sort_key = data["sortKey"]
    event.date_key = data["dateKey"]
    event.date_year = data["dateYear"]
    event.date_month = data["dateMonth"]
    event.date_day = data["dateDay"]
    event.headline = data["headline"]
    event.era = data["era"]
    event.body_markdown = data["bodyMarkdown"]
    event.tags_json = json.dumps(data["tags"], ensure_ascii=False)
    event.attachments_json = json.dumps(data["attachments"], ensure_ascii=False)
    event.related_event_ids_json = json.dumps(data["relatedEventIds"], ensure_ascii=False)
    event.image = image
    event.favorite = bool(data.get("favorite", event.favorite))
    if "deletedAt" in data:
        event.deleted_at = data["deletedAt"]


def create_event(db: Session, topic_id: int, payload: dict, user: User | None, *, legacy: bool = False) -> dict:
    topic = get_topic_or_404(db, topic_id)
    data = normalize_event_payload(payload)
    image = resolve_image(db, data["image"])
    event = TimelineEvent(
        topic_id=topic.id,
        created_by=user.id if user else None,
    )
    write_event_model(event, data, image)
    db.add(event)
    db.flush()
    for index, item in enumerate(data["items"]):
        db.add(EventItem(event_id=event.id, tag=item["tag"], text=item["text"], sort_order=index))
    db.commit()
    db.refresh(event)
    return serialize_event_rows(db, [get_event_or_404(db, event.id)], legacy=legacy)[0]


def update_event(db: Session, event_id: int, payload: dict, *, legacy: bool = False) -> dict:
    event = get_event_or_404(db, event_id)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload must be an object")

    if payload and set(payload.keys()).issubset(EVENT_STATE_KEYS):
        if event.deleted_at and not (set(payload.keys()) == {"deletedAt"} and payload.get("deletedAt") is None):
            raise HTTPException(status_code=409, detail="Deleted events can only be restored")
        apply_event_state(event, payload)
        db.commit()
        return serialize_event_rows(db, [get_event_or_404(db, event.id)], legacy=legacy)[0]

    if event.deleted_at:
        raise HTTPException(status_code=409, detail="Deleted events cannot be edited")

    old_image_id = event.image_id
    data = normalize_event_payload(payload)
    image = resolve_image(db, data["image"])
    write_event_model(event, data, image)
    for item in list(event.items):
        db.delete(item)
    db.flush()
    for index, item in enumerate(data["items"]):
        db.add(EventItem(event_id=event.id, tag=item["tag"], text=item["text"], sort_order=index))
    db.commit()
    if old_image_id and old_image_id != event.image_id:
        cleanup_orphan_images(db, {old_image_id})
    return serialize_event_rows(db, [get_event_or_404(db, event.id)], legacy=legacy)[0]


def delete_event(db: Session, event_id: int, *, permanent: bool = False):
    event = get_event_or_404(db, event_id)
    old_image_id = event.image_id
    if not permanent:
        event.deleted_at = datetime.now(timezone.utc)
        db.commit()
        return {"ok": True, "deletedAt": serialize_datetime(event.deleted_at)}

    db.delete(event)
    db.commit()
    cleanup_orphan_images(db, {old_image_id} if old_image_id else set())
    return {"ok": True}


def import_topic_data(db: Session, topic_id: int, parsed: object) -> dict:
    topic = get_topic_or_404(db, topic_id)
    if isinstance(parsed, dict):
        title = parsed.get("title", "")
        subtitle = parsed.get("subtitle", "")
        raw_events = parsed.get("events", [])
    elif isinstance(parsed, list):
        title = topic.title
        subtitle = topic.subtitle
        raw_events = parsed
    else:
        raise ValueError("JSON must be an array or object with events")

    normalized_events = [normalize_event_payload(item) for item in raw_events]

    existing_events = db.query(TimelineEvent).filter(TimelineEvent.topic_id == topic.id).all()
    old_image_ids = {event.image_id for event in existing_events if event.image_id}
    for event in existing_events:
        db.delete(event)
    db.flush()

    topic.title = str(title or "").strip()
    topic.subtitle = str(subtitle or "").strip()
    for node in normalized_events:
        image = resolve_image(db, node["image"])
        event = TimelineEvent(topic_id=topic.id)
        write_event_model(event, node, image)
        db.add(event)
        db.flush()
        for index, item in enumerate(node["items"]):
            db.add(EventItem(event_id=event.id, tag=item["tag"], text=item["text"], sort_order=index))
    db.commit()
    cleanup_orphan_images(db, old_image_ids)
    return {"ok": True, "count": len(normalized_events)}


def export_topic_data(db: Session, topic_id: int, *, from_key: int | None = None, to_key: int | None = None):
    topic = get_topic_or_404(db, topic_id)
    query = build_event_query(db, topic_id)
    if from_key is not None:
        query = query.filter(TimelineEvent.date_key >= from_key)
    if to_key is not None:
        query = query.filter(TimelineEvent.date_key <= to_key)
    rows = query.order_by(TimelineEvent.date_key.asc(), TimelineEvent.id.asc()).all()
    content = {
        "schemaVersion": 2,
        "title": topic.title or "",
        "subtitle": topic.subtitle or "",
        "events": serialize_event_rows(db, rows),
    }
    safe_ascii_name = "timeline-export.json"
    utf8_name = quote(f"{topic.name}.json")
    headers = {
        "Content-Disposition": f"attachment; filename=\"{safe_ascii_name}\"; filename*=UTF-8''{utf8_name}"
    }
    return content, headers


def list_themes() -> list[str]:
    THEME_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(file.stem for file in THEME_DIR.glob("*.css"))


def get_theme_vars(name: str) -> dict:
    css_file = THEME_DIR / f"{name}.css"
    if not css_file.exists():
        raise HTTPException(status_code=404, detail="Theme not found")
    content = css_file.read_text(encoding="utf-8")
    variables = {}
    match = re.search(r":root\s*\{([^}]+)\}", content, re.DOTALL)
    if match:
        for line in match.group(1).strip().split("\n"):
            found = re.match(r"\s*--([\w-]+)\s*:\s*(.+?)\s*;", line.strip())
            if found:
                variables[found.group(1)] = found.group(2)
    return variables


def update_theme_vars(name: str, variables: dict):
    css_file = THEME_DIR / f"{name}.css"
    if not css_file.exists():
        raise HTTPException(status_code=404, detail="Theme not found")
    content = css_file.read_text(encoding="utf-8")
    lines = [":root {"]
    for key, value in variables.items():
        lines.append(f"  --{key}: {value};")
    lines.append("}")
    new_root = "\n".join(lines)
    rest = re.sub(r":root\s*\{[^}]+\}", "", content, count=1, flags=re.DOTALL).strip()
    new_content = new_root if not rest else f"{new_root}\n\n{rest}"
    css_file.write_text(new_content + "\n", encoding="utf-8")
    return {"ok": True}


def get_app_config(db: Session) -> dict:
    config = dict(DEFAULT_CONFIG)
    entries = db.query(AppConfigEntry).all()
    for entry in entries:
        config[entry.key] = entry.value
    if not entries and CONFIG_FILE.exists():
        try:
            file_data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            config.update(file_data)
        except json.JSONDecodeError:
            pass
    return config


def update_app_config(db: Session, payload: dict) -> dict:
    merged = {**get_app_config(db), **payload}
    for key, value in merged.items():
        entry = db.get(AppConfigEntry, key)
        if entry is None:
            entry = AppConfigEntry(key=key, value=str(value))
            db.add(entry)
        else:
            entry.value = str(value)
    db.commit()
    return get_app_config(db)


async def store_uploaded_image(db: Session, file: UploadFile, uploaded_by: int | None):
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".pdf", ".md", ".txt", ".docx"):
        raise HTTPException(status_code=400, detail="Unsupported media format")
    filename = f"{uuid.uuid4().hex[:10]}{ext}"
    content = await file.read()
    path = IMAGES_DIR / filename
    path.write_bytes(content)

    image = ImageAsset(
        filename=filename,
        original_name=file.filename,
        mime_type=file.content_type or mimetypes.guess_type(file.filename or "")[0],
        uploaded_by=uploaded_by,
        is_orphan=True,
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    image_url = f"/images/{image.filename}" if (image.mime_type or "").startswith("image/") else None
    return {
        "id": image.id,
        "filename": image.filename,
        "originalName": image.original_name,
        "mimeType": image.mime_type,
        "url": f"/images/{image.filename}",
        "imageUrl": image_url,
    }


def cleanup_orphan_images(db: Session, image_ids: set[int]):
    if not image_ids:
        return
    for image_id in image_ids:
        image = db.get(ImageAsset, image_id)
        if image is None:
            continue
        still_used = db.query(TimelineEvent.id).filter(TimelineEvent.image_id == image.id).first()
        if not still_used:
            attachment_reference = (
                db.query(TimelineEvent.id)
                .filter(TimelineEvent.attachments_json.like(f'%"{image.filename}"%'))
                .first()
            )
            still_used = attachment_reference
        if still_used:
            image.is_orphan = False
            continue
        image.is_orphan = True
        image_path = IMAGES_DIR / image.filename
        if image_path.exists():
            image_path.unlink()
        db.delete(image)
    db.commit()


def delete_image_by_filename(db: Session, filename: str):
    image = db.query(ImageAsset).filter(ImageAsset.filename == filename).first()
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    linked = db.query(TimelineEvent.id).filter(TimelineEvent.image_id == image.id).first()
    if linked is None:
        linked = (
            db.query(TimelineEvent.id)
            .filter(TimelineEvent.attachments_json.like(f'%"{image.filename}"%'))
            .first()
        )
    if linked:
        raise HTTPException(status_code=409, detail="Image is still in use")
    image_path = IMAGES_DIR / image.filename
    if image_path.exists():
        image_path.unlink()
    db.delete(image)
    db.commit()
    return {"ok": True}
