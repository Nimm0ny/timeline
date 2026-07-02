import hashlib
import html
import io
import json
import mimetypes
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import and_, case, func, or_, text
from sqlalchemy.orm import Session, joinedload, selectinload

from backend.app.core.config import CONFIG_FILE, DEFAULT_CONFIG, IMAGES_DIR, MEDIA_DEFAULT_CONFIG, THEME_DIR, encode_config_value
from backend.app.models.entities import AppConfigEntry, EventItem, ImageAsset, TimelineEvent, Topic
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
COLUMN_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
# Unified property model: every column is a property. Only the two structural
# columns (date + headline) are reserved; type/tags are ordinary, deletable
# properties seeded by default (see DEFAULT_TOPIC_COLUMNS).
RESERVED_COLUMN_KEYS = {"title", "time"}
COLUMN_TYPES = {"text", "number", "date", "checkbox", "url", "email", "phone", "select", "multiselect"}
OPTION_COLUMN_TYPES = {"select", "multiselect"}
CHECKBOX_TRUE = {"true", "1", "yes", "on"}

# Note kinds (axis 2). "entry" = markdown body + display-style views; "mindmap" =
# node tree stored in body_json. See docs/note-types-and-views-design.md.
NOTE_TYPES = {"entry", "mindmap"}
DEFAULT_NOTE_TYPE = "entry"
UNDATED_LABEL = "未定时间"
# Upper bound on a structured body (mindmap tree) so a single note can't store an
# unbounded blob. 5 MB is generous for a text tree (tens of thousands of nodes) yet
# bounded even when nodes carry inline base64 images.
MAX_BODY_JSON_BYTES = 5_000_000
# Display styles for "entry" notes (axis 1); unlocked per data capability.
DISPLAY_STYLES = {"timeline", "table", "board", "gallery", "list", "outline"}
DEFAULT_DISPLAY_STYLE = "timeline"

# Seeded into every new notebook; both are deletable like any other property.
DEFAULT_TOPIC_COLUMNS = [
    {"key": "type", "label": "类型", "type": "select", "width": 96, "order": 0, "visible": True, "options": []},
    {"key": "tags", "label": "标签", "type": "multiselect", "width": 150, "order": 1, "visible": True, "options": []},
]
SUPPORTED_MEDIA_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".pdf", ".md", ".txt", ".docx"}
PILLOW_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ORIGINAL_IMAGE_EXTENSIONS = {".gif", ".svg"}
SEARCH_LIMIT_DEFAULT = 20
SEARCH_LIMIT_MAX = 50
SEARCH_TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)
SEARCH_INDEX_TABLE = "timeline_events_fts"


def default_topic_columns_json() -> str:
    return json.dumps(DEFAULT_TOPIC_COLUMNS, ensure_ascii=False)


def normalize_display_style(value: str | None) -> str:
    candidate = str(value or "").strip()
    return candidate if candidate in DISPLAY_STYLES else DEFAULT_DISPLAY_STYLE


def normalize_note_type(value: str | None) -> str:
    candidate = str(value or "").strip()
    return candidate if candidate in NOTE_TYPES else DEFAULT_NOTE_TYPE


def undated_display_label() -> str:
    return UNDATED_LABEL


def normalize_html_text(value) -> str:
    raw = html.unescape(str(value or ""))
    raw = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


def mindmap_root_data(value):
    if not isinstance(value, dict):
        return None
    root = value.get("root") if isinstance(value.get("root"), dict) else value
    data = root.get("data") if isinstance(root, dict) else None
    if not isinstance(root, dict) or not isinstance(data, dict):
        return None
    return root


def collect_mindmap_text(value) -> str:
    root = mindmap_root_data(value)
    if not root:
        return ""
    parts: list[str] = []

    def visit(node):
        if not isinstance(node, dict):
            return
        data = node.get("data") if isinstance(node.get("data"), dict) else {}
        parts.extend(
            text
            for text in [
                normalize_html_text(data.get("text")),
                normalize_html_text(data.get("note")),
                " ".join(str(item or "").strip() for item in (data.get("tag") or []) if str(item or "").strip()),
                normalize_html_text(data.get("hyperlink")),
            ]
            if text
        )
        for child in node.get("children") or []:
            visit(child)

    visit(root)
    return " ".join(parts)


def topic_capability_signals(columns: list | None, *, event_count: int, has_dated: bool, has_image: bool) -> dict:
    """Lightweight capability signals derived from already-loaded topic data —
    no per-event scan. `columns` comes from columns_json; the event aggregates
    (count/has_dated/has_image) ride the single bounds query. Mirrored on the FE
    so the view switcher derives available views with zero extra round-trip."""
    has_select_column = any(
        isinstance(column, dict) and column.get("type") in OPTION_COLUMN_TYPES
        for column in (columns or [])
    )
    return {
        "eventCount": int(event_count or 0),
        "hasDated": bool(has_dated),
        "hasImage": bool(has_image),
        "hasSelectColumn": has_select_column,
    }


def topic_capabilities(display_style: str | None, signals: dict) -> list[str]:
    """Pure: ready signals -> enabled display styles (FE/BE SSOT). `list` and
    `table` are always available, plus the notebook's own display_style (so a
    brand-new empty notebook still renders); the rest unlock per data capability."""
    enabled = {"list", "table", normalize_display_style(display_style)}
    if signals.get("hasDated"):
        enabled.add("timeline")
    if signals.get("eventCount"):
        enabled.add("outline")
    if signals.get("hasSelectColumn"):
        enabled.add("board")
    if signals.get("hasImage"):
        enabled.add("gallery")
    return sorted(enabled)


def topic_capabilities_block(topic: "Topic", *, event_count: int, has_dated: bool, has_image: bool) -> dict:
    """Build the displayStyle + capabilities payload appended to topic DTOs."""
    signals = topic_capability_signals(
        deserialize_json_list(topic.columns_json),
        event_count=event_count,
        has_dated=has_dated,
        has_image=has_image,
    )
    return {
        "capabilitySignals": signals,
        "capabilities": topic_capabilities(topic.display_style, signals),
    }


def sanitize_topic_name(name: str) -> str:
    return "".join(c for c in name.strip() if c.isalnum() or c in "_-\u4e00-\u9fff")


def topic_to_dict(topic: Topic) -> dict:
    return {
        "id": topic.id,
        "name": topic.name,
        "title": topic.title or "",
        "subtitle": topic.subtitle or "",
        "columns": deserialize_json_list(topic.columns_json),
        "displayStyle": normalize_display_style(topic.display_style),
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
        next_favorite = bool(payload.get("favorite"))
        if next_favorite and not event.favorite:
            event.favorite_at = datetime.now(timezone.utc)
        if not next_favorite:
            event.favorite_at = None
        event.favorite = next_favorite
    if "deletedAt" in payload:
        event.deleted_at = parse_optional_datetime(payload.get("deletedAt"))


def parse_cursor_token(value: str | None) -> tuple[int | None, int | None] | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if ":" not in raw:
        return (None, None) if raw.lower() == "null" else (parse_query_date_key(raw), None)
    left, right = raw.split(":", 1)
    cursor_key = None if left.lower() == "null" else parse_query_date_key(left)
    try:
        cursor_id = int(right)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid cursor id") from exc
    return cursor_key, cursor_id


def event_display_label(event: TimelineEvent) -> str:
    if event.date_key is None:
        return event.year or undated_display_label()
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


def deserialize_json_dict(value: str | None, *, fallback: dict | None = None) -> dict:
    if value is None:
        return dict(fallback or {})
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return dict(fallback or {})
    return parsed if isinstance(parsed, dict) else dict(fallback or {})


def deserialize_body_json(value: str | None):
    """Parse a note's structured body (mindmap tree); None when absent/invalid."""
    if value is None:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def normalize_body_json(value, note_type: str):
    """Entry notes have no structured body (they use body_markdown). Other note
    types keep an object/array tree; anything else is a 400."""
    if note_type == DEFAULT_NOTE_TYPE:
        return None
    if value is None:
        return None
    if not isinstance(value, (dict, list)):
        raise HTTPException(status_code=400, detail="bodyJson must be an object or array")
    if len(json.dumps(value, ensure_ascii=False).encode("utf-8")) > MAX_BODY_JSON_BYTES:
        raise HTTPException(status_code=413, detail="bodyJson is too large")
    return value


def default_body_markdown(items: list[dict]) -> str:
    lines = []
    for item in items:
        text = str(item.get("text", "")).strip()
        if text:
            lines.append(text)
    return "\n\n".join(lines)


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
        normalized = {
            "id": item.get("id"),
            "name": name,
            "filename": filename,
            "mimeType": mime_type,
        }
        for source_key, target_key in (
            ("thumbFilename", "thumbFilename"),
            ("originalFilename", "originalFilename"),
        ):
            value = str(item.get(source_key, "")).strip()
            if value:
                normalized[target_key] = value
        for key in ("width", "height", "bytes"):
            try:
                value = int(item.get(key))
            except (TypeError, ValueError):
                value = None
            if value is not None and value >= 0:
                normalized[key] = value
        attachments.append(normalized)
    return attachments


def normalize_options(raw_options, column_type: str) -> list[dict]:
    """Options are only meaningful for select/multiselect. Each option carries a
    stable `id` (referenced by event values), a display `label`, and a `color`."""
    if column_type not in OPTION_COLUMN_TYPES:
        return []
    if not isinstance(raw_options, list):
        return []
    options = []
    seen = set()
    for item in raw_options:
        if not isinstance(item, dict):
            continue
        oid = str(item.get("id", "")).strip()
        if not oid or oid in seen:
            continue
        label = str(item.get("label", "")).strip() or oid
        color = str(item.get("color", "")).strip()
        seen.add(oid)
        options.append({"id": oid[:48], "label": label[:24], "color": color[:32]})
    return options


def normalize_topic_columns(raw_columns) -> list[dict]:
    if raw_columns is None:
        return []
    if not isinstance(raw_columns, list):
        raise HTTPException(status_code=400, detail="Columns must be an array")

    columns = []
    seen = set()
    for index, item in enumerate(raw_columns):
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="Each column must be an object")
        key = str(item.get("key", "")).strip()
        label = str(item.get("label", "")).strip()
        column_type = str(item.get("type", "text")).strip() or "text"
        column_type = column_type if column_type in COLUMN_TYPES else "text"
        width = int(item.get("width", 96) or 96)
        order = int(item.get("order", index) or index)
        visible = item.get("visible", True) is not False

        if not COLUMN_KEY_PATTERN.fullmatch(key):
            raise HTTPException(status_code=400, detail=f"Invalid column key: {key}")
        if key in RESERVED_COLUMN_KEYS:
            raise HTTPException(status_code=400, detail=f"Column key is reserved: {key}")
        if key in seen:
            raise HTTPException(status_code=400, detail=f"Duplicated column key: {key}")
        if not label:
            raise HTTPException(status_code=400, detail="Column label is required")

        seen.add(key)
        columns.append(
            {
                "key": key,
                "label": label[:24],
                "type": column_type,
                "width": max(72, min(width, 220)),
                "order": order,
                "visible": visible,
                "options": normalize_options(item.get("options"), column_type),
            }
        )
    return sorted(columns, key=lambda column: (column["order"], column["label"]))


def topic_columns_index(topic: "Topic | None") -> dict[str, dict]:
    if topic is None:
        return {}
    index = {}
    for column in deserialize_json_list(topic.columns_json):
        if isinstance(column, dict) and str(column.get("key", "")).strip():
            index[str(column["key"]).strip()] = column
    return index


def allowed_extra_keys(topic: Topic | None) -> set[str]:
    if topic is None:
        return set()
    return {
        str(column.get("key", "")).strip()
        for column in deserialize_json_list(topic.columns_json)
        if isinstance(column, dict)
    }


def normalize_extra(payload: dict, topic: Topic | None) -> dict:
    """Filter event property values by the topic's property definitions. Free
    fields coerce to str; select keeps a single valid option id (else ""); multi
    keeps the subset of valid option ids, de-duplicated in order. Unknown keys
    and unknown option ids are dropped (no fabricated data)."""
    raw = payload.get("extra") or {}
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="Extra must be an object")

    columns = topic_columns_index(topic)
    normalized = {}
    for key, value in raw.items():
        name = str(key or "").strip()
        column = columns.get(name)
        if column is None:
            continue
        column_type = str(column.get("type", "text"))
        if column_type in OPTION_COLUMN_TYPES:
            valid = {str(option.get("id", "")) for option in (column.get("options") or []) if isinstance(option, dict)}
            if column_type == "multiselect":
                raw_ids = value if isinstance(value, list) else ([value] if value not in (None, "") else [])
                picked = [str(item) for item in raw_ids if str(item) in valid]
                normalized[name] = list(dict.fromkeys(picked))
            else:  # select
                single = str(value or "")
                normalized[name] = single if single in valid else ""
        elif column_type == "checkbox":
            truthy = value is True or str(value).strip().lower() in CHECKBOX_TRUE
            normalized[name] = "true" if truthy else "false"
        else:  # text / number / date / url / email / phone — free string value
            normalized[name] = "" if value is None else str(value)
    return normalized


def merge_orphan_extra(existing_extra: dict, next_extra: dict, topic: Topic | None) -> dict:
    """Preserve values whose property has since been deleted (orphan soft-keep),
    keeping their original scalar/list shape, then overlay the fresh values."""
    allowed = allowed_extra_keys(topic)
    preserved = {
        key: value
        for key, value in (existing_extra or {}).items()
        if key not in allowed
    }
    return {**preserved, **next_extra}


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
    thumb_filename = attachment.get("thumbFilename")
    original_filename = attachment.get("originalFilename")
    url = f"/images/{filename}"
    image_url = f"/images/{filename}" if (mime_type or "").startswith("image/") else None
    payload = {
        "id": attachment.get("id"),
        "name": attachment["name"],
        "filename": filename,
        "thumbFilename": thumb_filename,
        "originalFilename": original_filename,
        "mimeType": mime_type,
        "width": attachment.get("width"),
        "height": attachment.get("height"),
        "bytes": attachment.get("bytes"),
        "url": url,
        "thumbUrl": f"/images/{thumb_filename}" if thumb_filename else image_url,
        "originalUrl": f"/images/{original_filename}" if original_filename else None,
        "imageUrl": image_url,
    }
    return payload


def event_to_dict(event: TimelineEvent, related_lookup: dict[int, dict] | None = None) -> dict:
    headline = (event.headline or "").strip() or extract_headline_from_legacy_label(event.year or "")
    date_payload = event_date_payload(date_key=event.date_key, sort_key=event.sort_key, headline=headline)
    image_filename = event.image.filename if event.image else None
    thumb_filename = event.image.thumb_filename if event.image else None
    items = serialize_items(event)
    attachments = [build_attachment_payload(item) for item in deserialize_json_list(event.attachments_json)]
    related_ids = [int(value) for value in deserialize_json_list(event.related_event_ids_json) if str(value).strip().isdigit()]
    return {
        "id": event.id,
        "topicId": event.topic_id,
        "nodeType": "event",
        **date_payload,
        "sortKey": event.sort_key,
        "headline": headline,
        "legacyYear": event.year,
        "era": event.era,
        "noteType": normalize_note_type(event.note_type),
        "image": image_filename,
        "imageUrl": f"/images/{image_filename}" if image_filename else None,
        # Thumb (with full-image fallback) so the gallery card keeps its real thumb
        # after an edit round-trips through detailToIndexEvent, not the full-res image.
        "thumbUrl": (
            f"/images/{thumb_filename}"
            if thumb_filename
            else (f"/images/{image_filename}" if image_filename else None)
        ),
        "bodyMarkdown": event.body_markdown or default_body_markdown(items),
        "bodyJson": deserialize_body_json(event.body_json),
        "extra": deserialize_json_dict(event.extra_json),
        "attachments": attachments,
        "relatedEventIds": related_ids,
        "relatedEvents": [related_lookup[event_id] for event_id in related_ids if related_lookup and event_id in related_lookup],
        "createdAt": serialize_datetime(event.created_at),
        "updatedAt": serialize_datetime(event.updated_at),
        "favorite": bool(event.favorite),
        "favoriteAt": serialize_datetime(event.favorite_at),
        "deletedAt": serialize_datetime(event.deleted_at),
        "items": items,
    }


def markdown_plain_text(source: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", source)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[#>*_`~\-\[\]()]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def markdown_preview_text(event: TimelineEvent, *, max_length: int = 120) -> str:
    items = serialize_items(event)
    if normalize_note_type(event.note_type) != DEFAULT_NOTE_TYPE:
        text = collect_mindmap_text(deserialize_body_json(event.body_json))
    else:
        source = event.body_markdown or default_body_markdown(items)
        text = markdown_plain_text(source)
    return text[:max_length].rstrip()


def flatten_search_values(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [part for item in value for part in flatten_search_values(item)]
    if isinstance(value, dict):
        return [part for item in value.values() for part in flatten_search_values(item)]
    return [str(value)]


def extra_search_text(extra: dict, topic: Topic | None) -> str:
    parts = flatten_search_values(extra)
    if topic is None:
        return " ".join(parts)

    for column in deserialize_json_list(topic.columns_json):
        if not isinstance(column, dict):
            continue
        key = str(column.get("key", "")).strip()
        if not key or key not in extra or column.get("type") not in OPTION_COLUMN_TYPES:
            continue
        option_labels = {
            str(option.get("id", "")): str(option.get("label", "")).strip()
            for option in (column.get("options") or [])
            if isinstance(option, dict)
        }
        values = extra.get(key) if isinstance(extra.get(key), list) else [extra.get(key)]
        parts.extend(label for value in values if (label := option_labels.get(str(value))) and label != str(value))
    return " ".join(parts)


def build_search_payload(event: TimelineEvent, data: dict | None = None, topic: Topic | None = None) -> dict:
    if data is None:
        items = serialize_items(event)
        extra = deserialize_json_dict(event.extra_json)
        headline = (event.headline or "").strip() or extract_headline_from_legacy_label(event.year or "")
        note_type = normalize_note_type(event.note_type)
        body_markdown = event.body_markdown or default_body_markdown(items)
        body_json = deserialize_body_json(event.body_json)
        era = event.era
        topic = topic or event.topic
    else:
        items = data.get("items") or []
        extra = data.get("extra") or {}
        headline = str(data.get("headline") or "").strip() or extract_headline_from_legacy_label(data.get("legacyYear") or "")
        note_type = normalize_note_type(data.get("noteType"))
        body_markdown = data.get("bodyMarkdown") or default_body_markdown(items)
        body_json = data.get("bodyJson")
        era = data.get("era")

    return {
        "event_id": event.id,
        "topic_id": event.topic_id,
        "headline": headline,
        "body": " ".join(
            part
            for part in [
                collect_mindmap_text(body_json) if note_type != DEFAULT_NOTE_TYPE else markdown_plain_text(str(body_markdown or "")),
                *[str(item.get("text", "")) for item in items if isinstance(item, dict)],
            ]
            if part
        ),
        "era": str(era or ""),
        "extra": extra_search_text(extra, topic),
    }


def ensure_search_schema(db: Session) -> None:
    db.execute(
        text(
            f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS {SEARCH_INDEX_TABLE}
            USING fts5(
              event_id UNINDEXED,
              topic_id UNINDEXED,
              headline,
              body,
              era,
              extra,
              tokenize = 'unicode61'
            )
            """
        )
    )


def remove_search_index_row(db: Session, event_id: int) -> None:
    ensure_search_schema(db)
    db.execute(text(f"DELETE FROM {SEARCH_INDEX_TABLE} WHERE event_id = :event_id"), {"event_id": int(event_id)})


def remove_search_index_topic(db: Session, topic_id: int) -> None:
    ensure_search_schema(db)
    db.execute(text(f"DELETE FROM {SEARCH_INDEX_TABLE} WHERE topic_id = :topic_id"), {"topic_id": int(topic_id)})


def insert_search_index_row(db: Session, payload: dict) -> None:
    db.execute(
        text(
            f"""
            INSERT INTO {SEARCH_INDEX_TABLE} (event_id, topic_id, headline, body, era, extra)
            VALUES (:event_id, :topic_id, :headline, :body, :era, :extra)
            """
        ),
        payload,
    )


def upsert_search_index_row(db: Session, event: TimelineEvent, data: dict | None = None, topic: Topic | None = None) -> None:
    remove_search_index_row(db, event.id)
    if event.deleted_at:
        return
    insert_search_index_row(db, build_search_payload(event, data, topic))


def rebuild_search_index(db: Session) -> None:
    ensure_search_schema(db)
    db.execute(text(f"DELETE FROM {SEARCH_INDEX_TABLE}"))
    rows = (
        db.query(TimelineEvent)
        .options(selectinload(TimelineEvent.items), joinedload(TimelineEvent.topic))
        .filter(TimelineEvent.deleted_at.is_(None))
        .order_by(TimelineEvent.topic_id.asc(), *timeline_event_order_clauses())
        .all()
    )
    for event in rows:
        insert_search_index_row(db, build_search_payload(event))


def search_index_needs_rebuild(db: Session) -> bool:
    ensure_search_schema(db)
    row = db.execute(text(f"SELECT COUNT(*) AS count FROM {SEARCH_INDEX_TABLE}")).mappings().first()
    indexed_count = int(row["count"] if row else 0)
    live_count = db.query(func.count(TimelineEvent.id)).filter(TimelineEvent.deleted_at.is_(None)).scalar() or 0
    return live_count > 0 and indexed_count < live_count


def build_fts_query(query: str | None) -> str:
    terms = SEARCH_TOKEN_PATTERN.findall(str(query or "").lower())[:8]
    return " ".join(f"{term}*" for term in terms if term)


def normalize_search_snippet(*parts: str | None) -> str:
    for part in parts:
        text_value = re.sub(r"\s+", " ", str(part or "")).strip()
        if text_value:
            return text_value[:180].rstrip()
    return ""


def search_events(db: Session, query: str | None, limit: int = SEARCH_LIMIT_DEFAULT) -> list[dict]:
    match_query = build_fts_query(query)
    if not match_query:
        return []

    safe_limit = max(1, min(int(limit or SEARCH_LIMIT_DEFAULT), SEARCH_LIMIT_MAX))
    if search_index_needs_rebuild(db):
        rebuild_search_index(db)
        db.commit()

    rows = db.execute(
        text(
            f"""
            SELECT
              e.id,
              e.topic_id AS topic_id,
              e.date_key AS date_key,
              e.sort_key AS sort_key,
              e.headline AS headline,
              e.year AS legacy_year,
              e.body_markdown AS body_markdown,
              snippet({SEARCH_INDEX_TABLE}, 2, '', '', '...', 12) AS headline_snippet,
              snippet({SEARCH_INDEX_TABLE}, 3, '', '', '...', 18) AS body_snippet,
              snippet({SEARCH_INDEX_TABLE}, 4, '', '', '...', 12) AS era_snippet,
              snippet({SEARCH_INDEX_TABLE}, 5, '', '', '...', 12) AS extra_snippet,
              bm25({SEARCH_INDEX_TABLE}) AS rank
            FROM {SEARCH_INDEX_TABLE}
            JOIN timeline_events e ON e.id = {SEARCH_INDEX_TABLE}.event_id
            WHERE {SEARCH_INDEX_TABLE} MATCH :query
              AND e.deleted_at IS NULL
            ORDER BY rank ASC, CASE WHEN e.date_key IS NULL THEN 1 ELSE 0 END ASC, e.date_key ASC, e.id ASC
            LIMIT :limit
            """
        ),
        {"query": match_query, "limit": safe_limit},
    ).mappings()

    results = []
    for row in rows:
        date_key = resolve_event_date_key(row["date_key"], row["sort_key"])
        headline = (row["headline"] or "").strip() or extract_headline_from_legacy_label(row["legacy_year"] or "")
        results.append(
            {
                "id": row["id"],
                "topicId": row["topic_id"],
                "headline": headline,
                "snippet": normalize_search_snippet(
                    row["body_snippet"],
                    row["headline_snippet"],
                    row["era_snippet"],
                    row["extra_snippet"],
                    markdown_plain_text(row["body_markdown"] or ""),
                    headline,
                ),
                "dateKey": date_key if date_key and date_key > 0 else None,
                "isoDate": date_key_to_iso(date_key) if date_key and date_key > 0 else None,
                "rank": row["rank"],
            }
        )
    return results


def resolve_event_date_key(date_key: int | None, sort_key) -> int | None:
    if date_key is not None:
        return int(date_key)
    if sort_key in {None, "", 0, 0.0, "0"}:
        return None
    try:
        normalized = normalize_date_key(sort_key)
    except HTTPException:
        return None
    return normalized if normalized > 0 else None


def event_date_payload(*, date_key: int | None, sort_key, headline: str) -> dict:
    resolved = resolve_event_date_key(date_key, sort_key)
    if resolved is None:
        return {
            "hasDate": False,
            "dateKey": None,
            "isoDate": None,
            "dateParts": {"year": None, "month": None, "day": None},
            "displayLabel": undated_display_label(),
        }
    date_year, date_month, date_day = date_key_to_parts(resolved)
    return {
        "hasDate": True,
        "dateKey": resolved,
        "isoDate": date_key_to_iso(resolved),
        "dateParts": {
            "year": date_year,
            "month": date_month,
            "day": date_day,
        },
        "displayLabel": build_display_label(date_year, date_month, date_day, headline),
    }


def event_index_search_text(event: TimelineEvent, attachments: list[dict]) -> str:
    items = serialize_items(event)
    extra = deserialize_json_dict(event.extra_json)
    parts = [
        event.headline,
        event.year,
        event.era,
        collect_mindmap_text(deserialize_body_json(event.body_json))
        if normalize_note_type(event.note_type) != DEFAULT_NOTE_TYPE
        else markdown_plain_text(event.body_markdown or default_body_markdown(items)),
        *[item["text"] for item in items],
        *flatten_search_values(extra),
        *[f"{attachment.get('name', '')} {attachment.get('filename', '')}" for attachment in attachments],
    ]
    return re.sub(r"\s+", " ", " ".join(str(part or "") for part in parts)).strip()


def event_to_index_dict(event: TimelineEvent) -> dict:
    headline = (event.headline or "").strip() or extract_headline_from_legacy_label(event.year or "")
    attachments = deserialize_json_list(event.attachments_json)
    date_payload = event_date_payload(date_key=event.date_key, sort_key=event.sort_key, headline=headline)
    # The gallery view renders the event's primary image; the index list is the
    # only payload it sees, so carry the image URLs here (thumb preferred for the
    # grid). The build_timeline_index query joinedloads `image`, so this is a join,
    # not an N+1. Both are null for imageless events.
    image_filename = event.image.filename if event.image else None
    thumb_filename = event.image.thumb_filename if event.image else None
    return {
        "id": event.id,
        "topicId": event.topic_id,
        **date_payload,
        "headline": headline,
        "era": event.era,
        "noteType": normalize_note_type(event.note_type),
        "image": image_filename,
        "imageUrl": f"/images/{image_filename}" if image_filename else None,
        "thumbUrl": (
            f"/images/{thumb_filename}"
            if thumb_filename
            else (f"/images/{image_filename}" if image_filename else None)
        ),
        "extra": deserialize_json_dict(event.extra_json),
        "favorite": bool(event.favorite),
        "favoriteAt": serialize_datetime(event.favorite_at),
        "deletedAt": serialize_datetime(event.deleted_at),
        "createdAt": serialize_datetime(event.created_at),
        "updatedAt": serialize_datetime(event.updated_at),
        "preview": markdown_preview_text(event),
        "searchText": event_index_search_text(event, attachments),
        "attachmentCount": len(attachments),
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
        .order_by(*timeline_event_order_clauses())
        .all()
    )
    lookup = {}
    for row in related_rows:
        headline = (row.headline or "").strip() or extract_headline_from_legacy_label(row.year or "")
        date_payload = event_date_payload(date_key=row.date_key, sort_key=row.sort_key, headline=headline)
        lookup[row.id] = {
            "id": row.id,
            "headline": headline,
            "displayLabel": date_payload["displayLabel"],
        }
    return lookup


def serialize_event_rows(db: Session, rows: list[TimelineEvent]) -> list[dict]:
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
        .options(selectinload(TimelineEvent.items), joinedload(TimelineEvent.image), joinedload(TimelineEvent.topic))
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
            func.count(TimelineEvent.image_id),
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
        "hasImage": int(row[3] or 0) > 0,
        "supportedZoomLevels": SUPPORTED_ZOOM_LEVELS,
    }


def timeline_event_order_clauses():
    return (
        case((TimelineEvent.date_key.is_(None), 1), else_=0).asc(),
        TimelineEvent.date_key.asc(),
        TimelineEvent.id.asc(),
    )


def list_topics(db: Session) -> list[dict]:
    rows = (
        db.query(
            Topic,
            func.count(TimelineEvent.id).label("event_count"),
            func.min(TimelineEvent.date_key).label("min_date_key"),
            func.max(TimelineEvent.date_key).label("max_date_key"),
            func.count(TimelineEvent.image_id).label("image_count"),
        )
        .outerjoin(TimelineEvent, TimelineEvent.topic_id == Topic.id)
        .group_by(Topic.id)
        .order_by(Topic.id.asc())
        .all()
    )
    items = []
    for topic, event_count, min_date_key, max_date_key, image_count in rows:
        items.append(
            {
                **topic_to_dict(topic),
                "eventCount": int(event_count or 0),
                "minDateKey": int(min_date_key) if min_date_key is not None else None,
                "maxDateKey": int(max_date_key) if max_date_key is not None else None,
                "minDate": date_key_to_iso(int(min_date_key)) if min_date_key is not None else None,
                "maxDate": date_key_to_iso(int(max_date_key)) if max_date_key is not None else None,
                **topic_capabilities_block(
                    topic,
                    event_count=int(event_count or 0),
                    has_dated=max_date_key is not None,
                    has_image=int(image_count or 0) > 0,
                ),
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
    topic = Topic(name=safe, title=safe, subtitle="", columns_json=default_topic_columns_json())
    db.add(topic)
    db.commit()
    db.refresh(topic)
    return {
        **topic_to_dict(topic),
        **topic_capabilities_block(topic, event_count=0, has_dated=False, has_image=False),
    }


def delete_topic(db: Session, topic_id: int):
    topic = get_topic_or_404(db, topic_id)
    events = (
        db.query(TimelineEvent)
        .options(joinedload(TimelineEvent.image))
        .filter(TimelineEvent.topic_id == topic_id)
        .all()
    )
    image_ids = {event.image_id for event in events if event.image_id}
    remove_search_index_topic(db, topic_id)
    db.delete(topic)
    db.commit()
    cleanup_orphan_images(db, image_ids)
    return {"ok": True}


def get_topic_meta(db: Session, topic_id: int) -> dict:
    topic = get_topic_or_404(db, topic_id)
    bounds = build_topic_bounds(db, topic_id)
    return {
        **topic_to_dict(topic),
        **bounds,
        **topic_capabilities_block(
            topic,
            event_count=bounds["eventCount"],
            has_dated=bounds["maxDateKey"] is not None,
            has_image=bounds["hasImage"],
        ),
    }


def update_topic_meta(db: Session, topic_id: int, payload: dict) -> dict:
    topic = get_topic_or_404(db, topic_id)
    if "title" in payload:
        topic.title = str(payload["title"] or "").strip()
    if "subtitle" in payload:
        topic.subtitle = str(payload["subtitle"] or "").strip()
    if "displayStyle" in payload:
        topic.display_style = normalize_display_style(payload.get("displayStyle"))
    if "columns" in payload:
        topic.columns_json = json.dumps(normalize_topic_columns(payload.get("columns")), ensure_ascii=False)
    db.commit()
    db.refresh(topic)
    return get_topic_meta(db, topic_id)


def build_event_query(db: Session, topic_id: int):
    return (
        db.query(TimelineEvent)
        .options(selectinload(TimelineEvent.items), joinedload(TimelineEvent.image))
        .filter(TimelineEvent.topic_id == topic_id)
    )


def list_topic_events(db: Session, topic_id: int) -> list[dict]:
    get_topic_or_404(db, topic_id)
    events = build_event_query(db, topic_id).order_by(*timeline_event_order_clauses()).all()
    return serialize_event_rows(db, events)


def get_event_detail(db: Session, event_id: int) -> dict:
    return serialize_event_rows(db, [get_event_or_404(db, event_id)])[0]


def build_timeline_index(db: Session) -> dict:
    rows = (
        db.query(TimelineEvent)
        .options(selectinload(TimelineEvent.items), joinedload(TimelineEvent.image))
        .order_by(TimelineEvent.topic_id.asc(), *timeline_event_order_clauses())
        .all()
    )
    return {
        "topics": list_topics(db),
        "events": [event_to_index_dict(event) for event in rows],
    }


def query_topic_events(
    db: Session,
    topic_id: int,
    *,
    from_key: int | None = None,
    to_key: int | None = None,
    cursor: tuple[int | None, int | None] | None = None,
    limit: int | None = None,
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
            query = query.filter(TimelineEvent.date_key > cursor_key) if cursor_key is not None else query
        else:
            if cursor_key is None:
                query = query.filter(and_(TimelineEvent.date_key.is_(None), TimelineEvent.id > cursor_id))
            else:
                query = query.filter(
                    or_(
                        TimelineEvent.date_key > cursor_key,
                        TimelineEvent.date_key.is_(None),
                        and_(TimelineEvent.date_key == cursor_key, TimelineEvent.id > cursor_id),
                    )
                )

    query = query.order_by(*timeline_event_order_clauses())
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
        next_cursor = f"{last_row.date_key if last_row.date_key is not None else 'null'}:{last_row.id}"

    return {
        "items": serialize_event_rows(db, rows),
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


# Body is the canonical content (body_markdown). EventItem is the legacy body
# store; its `tag` is no longer a property source, just a non-null filler.
DEFAULT_ITEM_TAG = "note"


def derive_items_from_markdown(body_markdown: str) -> list[dict]:
    chunks = [segment.strip() for segment in str(body_markdown or "").split("\n\n") if segment.strip()]
    if not chunks:
        return []
    return [{"tag": DEFAULT_ITEM_TAG, "text": chunk} for chunk in chunks]


def normalize_event_items(payload: dict, body_markdown: str | None = None, *, note_type: str | None = None) -> list[dict]:
    raw_items = payload.get("items")
    if raw_items is None:
        raw_items = payload.get("events")
    raw_items = raw_items or []
    if not isinstance(raw_items, list):
        raise HTTPException(status_code=400, detail="Event items must be an array")

    if len(raw_items) == 0:
        derived = derive_items_from_markdown(body_markdown or "")
        if derived:
            return derived
        # A mindmap's content lives in body_json (the tree), not markdown items —
        # so an empty item list is valid for it. Entry notes still require body.
        if note_type and note_type != DEFAULT_NOTE_TYPE:
            return []
        raise HTTPException(status_code=400, detail="Event items are required")

    items = []
    for item in raw_items:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="Each event item must be an object")
        tag = str(item.get("tag", "")).strip() or DEFAULT_ITEM_TAG
        text = str(item.get("text", "")).strip()
        if not text:
            raise HTTPException(status_code=400, detail="Each event item requires text")
        items.append({"tag": tag, "text": text})
    return items


def normalize_event_payload(payload: dict, *, topic: Topic | None = None) -> dict:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload must be an object")

    image = payload.get("image")
    note_type = normalize_note_type(payload.get("noteType"))
    body_json = normalize_body_json(payload.get("bodyJson"), note_type)
    era = str(payload.get("era", "")).strip()
    # Era is the timeline's grouping spine for entries; a mindmap is authored on its
    # own canvas and may be undated/un-grouped, so it may omit era (falls into the
    # "未分组" bucket if it surfaces in an entry view).
    if not era and note_type == DEFAULT_NOTE_TYPE:
        raise HTTPException(status_code=400, detail="Era is required")
    body_markdown = str(payload.get("bodyMarkdown", "")).strip()
    items = normalize_event_items(payload, body_markdown, note_type=note_type)
    attachments = normalize_attachments(payload)
    related_event_ids = normalize_related_event_ids(payload)
    extra = normalize_extra(payload, topic)
    state = {}
    if "favorite" in payload:
        state["favorite"] = bool(payload.get("favorite"))
    if "deletedAt" in payload:
        state["deletedAt"] = parse_optional_datetime(payload.get("deletedAt"))

    has_date_parts = any(key in payload for key in {"dateYear", "dateMonth", "dateDay"})
    uses_structured_contract = bool({"headline", "dateYear", "dateMonth", "dateDay"} & set(payload.keys()))
    headline = str(payload.get("headline", "")).strip()
    if uses_structured_contract and (note_type == DEFAULT_NOTE_TYPE or has_date_parts):
        try:
            year = int(payload.get("dateYear"))
            month = int(payload.get("dateMonth"))
            day = int(payload.get("dateDay"))
            validate_date_parts(year, month, day)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
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
            "noteType": note_type,
            "bodyJson": body_json,
            "bodyMarkdown": body_markdown or default_body_markdown(items),
            "extra": extra,
            "attachments": attachments,
            "relatedEventIds": related_event_ids,
            "items": items,
            "image": image,
            **state,
        }

    if uses_structured_contract and note_type != DEFAULT_NOTE_TYPE:
        if not headline:
            raise HTTPException(status_code=400, detail="Headline is required")
        return {
            "dateYear": None,
            "dateMonth": None,
            "dateDay": None,
            "dateKey": None,
            "sortKey": 0.0,
            "headline": headline,
            "legacyYear": undated_display_label(),
            "era": era,
            "noteType": note_type,
            "bodyJson": body_json,
            "bodyMarkdown": body_markdown or default_body_markdown(items),
            "extra": extra,
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
        "noteType": note_type,
        "bodyJson": body_json,
        "bodyMarkdown": body_markdown or default_body_markdown(items),
        "extra": extra,
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
    event.note_type = data["noteType"]
    event.body_markdown = data["bodyMarkdown"]
    event.body_json = json.dumps(data["bodyJson"], ensure_ascii=False) if data.get("bodyJson") is not None else None
    event.extra_json = json.dumps(data["extra"], ensure_ascii=False)
    event.attachments_json = json.dumps(data["attachments"], ensure_ascii=False)
    event.related_event_ids_json = json.dumps(data["relatedEventIds"], ensure_ascii=False)
    event.image = image
    next_favorite = bool(data.get("favorite", event.favorite))
    if next_favorite and not event.favorite:
        event.favorite_at = event.favorite_at or datetime.now(timezone.utc)
    if not next_favorite:
        event.favorite_at = None
    event.favorite = next_favorite
    if "deletedAt" in data:
        event.deleted_at = data["deletedAt"]


def create_event(db: Session, topic_id: int, payload: dict) -> dict:
    topic = get_topic_or_404(db, topic_id)
    data = normalize_event_payload(payload, topic=topic)
    image = resolve_image(db, data["image"])
    event = TimelineEvent(topic_id=topic.id)
    write_event_model(event, data, image)
    db.add(event)
    db.flush()
    for index, item in enumerate(data["items"]):
        db.add(EventItem(event_id=event.id, tag=item["tag"], text=item["text"], sort_order=index))
    upsert_search_index_row(db, event, data, topic)
    db.commit()
    db.refresh(event)
    return serialize_event_rows(db, [get_event_or_404(db, event.id)])[0]


def update_event(db: Session, event_id: int, payload: dict) -> dict:
    event = get_event_or_404(db, event_id)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload must be an object")

    if payload and set(payload.keys()).issubset(EVENT_STATE_KEYS):
        if event.deleted_at and not (set(payload.keys()) == {"deletedAt"} and payload.get("deletedAt") is None):
            raise HTTPException(status_code=409, detail="Deleted events can only be restored")
        apply_event_state(event, payload)
        upsert_search_index_row(db, event, topic=event.topic)
        db.commit()
        return serialize_event_rows(db, [get_event_or_404(db, event.id)])[0]

    if event.deleted_at:
        raise HTTPException(status_code=409, detail="Deleted events cannot be edited")

    old_image_id = event.image_id
    data = normalize_event_payload(payload, topic=event.topic)
    data["extra"] = merge_orphan_extra(deserialize_json_dict(event.extra_json), data["extra"], event.topic)
    image = resolve_image(db, data["image"])
    write_event_model(event, data, image)
    for item in list(event.items):
        db.delete(item)
    db.flush()
    for index, item in enumerate(data["items"]):
        db.add(EventItem(event_id=event.id, tag=item["tag"], text=item["text"], sort_order=index))
    upsert_search_index_row(db, event, data, event.topic)
    db.commit()
    if old_image_id and old_image_id != event.image_id:
        cleanup_orphan_images(db, {old_image_id})
    return serialize_event_rows(db, [get_event_or_404(db, event.id)])[0]


def delete_event(db: Session, event_id: int, *, permanent: bool = False):
    event = get_event_or_404(db, event_id)
    old_image_id = event.image_id
    if not permanent:
        event.deleted_at = datetime.now(timezone.utc)
        remove_search_index_row(db, event.id)
        db.commit()
        return {"ok": True, "deletedAt": serialize_datetime(event.deleted_at)}

    remove_search_index_row(db, event.id)
    db.delete(event)
    db.commit()
    cleanup_orphan_images(db, {old_image_id} if old_image_id else set())
    return {"ok": True}


def import_topic_data(db: Session, topic_id: int, parsed: object) -> dict:
    topic = get_topic_or_404(db, topic_id)
    if isinstance(parsed, dict):
        title = parsed.get("title", "")
        subtitle = parsed.get("subtitle", "")
        columns = parsed.get("columns", [])
        raw_events = parsed.get("events", [])
    elif isinstance(parsed, list):
        title = topic.title
        subtitle = topic.subtitle
        columns = deserialize_json_list(topic.columns_json)
        raw_events = parsed
    else:
        raise ValueError("JSON must be an array or object with events")

    topic.columns_json = json.dumps(normalize_topic_columns(columns), ensure_ascii=False)
    normalized_events = [normalize_event_payload(item, topic=topic) for item in raw_events]

    existing_events = db.query(TimelineEvent).filter(TimelineEvent.topic_id == topic.id).all()
    old_image_ids = {event.image_id for event in existing_events if event.image_id}
    remove_search_index_topic(db, topic.id)
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
        upsert_search_index_row(db, event, node, topic)
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
    rows = query.order_by(*timeline_event_order_clauses()).all()
    content = {
        "schemaVersion": 2,
        "title": topic.title or "",
        "subtitle": topic.subtitle or "",
        "columns": deserialize_json_list(topic.columns_json),
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


def _to_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return default


def _bounded_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        next_value = int(value)
    except (TypeError, ValueError):
        return default
    return min(maximum, max(minimum, next_value))


def normalize_media_config(value) -> dict:
    source = value if isinstance(value, dict) else {}
    defaults = dict(MEDIA_DEFAULT_CONFIG)
    return {
        "compress": _to_bool(source.get("compress"), defaults["compress"]),
        "keepOriginal": _to_bool(source.get("keepOriginal"), defaults["keepOriginal"]),
        "quality": _bounded_int(source.get("quality"), defaults["quality"], 1, 100),
        "maxEdge": _bounded_int(source.get("maxEdge"), defaults["maxEdge"], 320, 8192),
        "thumbEdge": _bounded_int(source.get("thumbEdge"), defaults["thumbEdge"], 96, 2048),
    }


def decode_config_value(key: str, raw_value: str):
    default = DEFAULT_CONFIG.get(key)
    if isinstance(default, (dict, list, bool, int, float)) or default is None:
        try:
            parsed = json.loads(raw_value)
        except (json.JSONDecodeError, TypeError):
            parsed = default
        return normalize_media_config(parsed) if key == "media" else parsed
    return raw_value


def get_app_config(db: Session) -> dict:
    config = dict(DEFAULT_CONFIG)
    config["media"] = normalize_media_config(config.get("media"))
    entries = db.query(AppConfigEntry).all()
    for entry in entries:
        config[entry.key] = decode_config_value(entry.key, entry.value)
    if not entries and CONFIG_FILE.exists():
        try:
            file_data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            config.update(file_data)
        except json.JSONDecodeError:
            pass
    config["media"] = normalize_media_config(config.get("media"))
    return config


def update_app_config(db: Session, payload: dict) -> dict:
    current = get_app_config(db)
    merged = {**current, **payload}
    if "media" in payload:
        media_source = payload.get("media")
        if isinstance(media_source, dict):
            merged["media"] = normalize_media_config({**current.get("media", {}), **media_source})
        else:
            merged["media"] = normalize_media_config(media_source)
    for key, value in merged.items():
        entry = db.get(AppConfigEntry, key)
        if entry is None:
            entry = AppConfigEntry(key=key, value=encode_config_value(value))
            db.add(entry)
        else:
            entry.value = encode_config_value(value)
    db.commit()
    return get_app_config(db)


async def store_uploaded_image(db: Session, file: UploadFile):
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in SUPPORTED_MEDIA_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported media format")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    content_hash = hashlib.sha256(content).hexdigest()[:16]
    existing = db.query(ImageAsset).filter(ImageAsset.content_hash == content_hash).first()
    if existing is not None:
        return image_asset_to_upload_payload(existing)

    media_config = normalize_media_config(get_app_config(db).get("media"))
    original_mime = file.content_type or mimetypes.guess_type(file.filename or "")[0]
    processed = process_media_upload(content, ext, content_hash, original_mime, media_config)

    image = ImageAsset(
        filename=processed["filename"],
        content_hash=content_hash,
        thumb_filename=processed.get("thumbFilename"),
        original_filename=processed.get("originalFilename"),
        original_name=file.filename,
        mime_type=processed.get("mimeType"),
        width=processed.get("width"),
        height=processed.get("height"),
        bytes=processed.get("bytes"),
        is_orphan=True,
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    return image_asset_to_upload_payload(image)


def image_asset_to_upload_payload(image: ImageAsset) -> dict:
    image_url = f"/images/{image.filename}" if (image.mime_type or "").startswith("image/") else None
    return {
        "id": image.id,
        "filename": image.filename,
        "thumbFilename": image.thumb_filename,
        "originalFilename": image.original_filename,
        "originalName": image.original_name,
        "mimeType": image.mime_type,
        "width": image.width,
        "height": image.height,
        "bytes": image.bytes,
        "url": f"/images/{image.filename}",
        "thumbUrl": f"/images/{image.thumb_filename}" if image.thumb_filename else image_url,
        "originalUrl": f"/images/{image.original_filename}" if image.original_filename else None,
        "imageUrl": image_url,
    }


def process_media_upload(content: bytes, ext: str, content_hash: str, mime_type: str | None, media_config: dict) -> dict:
    if ext in PILLOW_IMAGE_EXTENSIONS and media_config["compress"]:
        return process_transcoded_image(content, ext, content_hash, media_config)
    if ext in PILLOW_IMAGE_EXTENSIONS:
        return process_original_image_with_thumb(content, ext, content_hash, mime_type, media_config)
    return process_original_file(content, ext, content_hash, mime_type)


def process_transcoded_image(content: bytes, ext: str, content_hash: str, media_config: dict) -> dict:
    image = decode_upload_image(content)
    work_image = resize_long_edge(image, media_config["maxEdge"])
    work_bytes = encode_webp(work_image, media_config["quality"])
    filename = f"{content_hash}.webp"
    thumb_filename = f"{content_hash}.thumb.webp"
    (IMAGES_DIR / filename).write_bytes(work_bytes)
    (IMAGES_DIR / thumb_filename).write_bytes(encode_webp(resize_long_edge(work_image, media_config["thumbEdge"]), media_config["quality"]))

    original_filename = None
    if media_config["keepOriginal"]:
        original_filename = f"{content_hash}.orig{ext}"
        (IMAGES_DIR / original_filename).write_bytes(content)

    return {
        "filename": filename,
        "thumbFilename": thumb_filename,
        "originalFilename": original_filename,
        "mimeType": "image/webp",
        "width": work_image.width,
        "height": work_image.height,
        "bytes": len(work_bytes),
    }


def process_original_image_with_thumb(content: bytes, ext: str, content_hash: str, mime_type: str | None, media_config: dict) -> dict:
    image = decode_upload_image(content)
    filename = f"{content_hash}{ext}"
    (IMAGES_DIR / filename).write_bytes(content)
    thumb_filename = f"{content_hash}.thumb.webp"
    (IMAGES_DIR / thumb_filename).write_bytes(encode_webp(resize_long_edge(image, media_config["thumbEdge"]), media_config["quality"]))
    return {
        "filename": filename,
        "thumbFilename": thumb_filename,
        "mimeType": mime_type or mimetypes.guess_type(filename)[0],
        "width": image.width,
        "height": image.height,
        "bytes": len(content),
    }


def process_original_file(content: bytes, ext: str, content_hash: str, mime_type: str | None) -> dict:
    suffix = ext if ext in ORIGINAL_IMAGE_EXTENSIONS else ext
    filename = f"{content_hash}{suffix}"
    (IMAGES_DIR / filename).write_bytes(content)
    return {
        "filename": filename,
        "mimeType": mime_type or mimetypes.guess_type(filename)[0],
        "bytes": len(content),
    }


def decode_upload_image(content: bytes) -> Image.Image:
    try:
        with Image.open(io.BytesIO(content)) as image:
            image = ImageOps.exif_transpose(image)
            image.load()
            if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
                return image.convert("RGBA")
            return image.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid image file") from exc


def resize_long_edge(image: Image.Image, max_edge: int) -> Image.Image:
    longest = max(image.width, image.height)
    if longest <= max_edge:
        return image.copy()
    ratio = max_edge / longest
    size = (max(1, round(image.width * ratio)), max(1, round(image.height * ratio)))
    return image.resize(size, Image.Resampling.LANCZOS)


def encode_webp(image: Image.Image, quality: int) -> bytes:
    target = io.BytesIO()
    image.save(target, format="WEBP", quality=quality, method=6)
    return target.getvalue()


def filenames_for_asset(image: ImageAsset) -> set[str]:
    return {name for name in (image.filename, image.thumb_filename, image.original_filename) if name}


def unlink_asset_files(image: ImageAsset):
    for filename in filenames_for_asset(image):
        path = IMAGES_DIR / filename
        if path.exists():
            path.unlink()


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
        unlink_asset_files(image)
        db.delete(image)
    db.commit()


def delete_image_by_filename(db: Session, filename: str):
    image = (
        db.query(ImageAsset)
        .filter(
            or_(
                ImageAsset.filename == filename,
                ImageAsset.thumb_filename == filename,
                ImageAsset.original_filename == filename,
            )
        )
        .first()
    )
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
    unlink_asset_files(image)
    db.delete(image)
    db.commit()
    return {"ok": True}
