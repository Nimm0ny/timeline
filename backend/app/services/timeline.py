import hashlib
import io
import json
import mimetypes
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import and_, case, func, or_, select, text, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, joinedload, selectinload

from backend.app.core.config import CONFIG_FILE, DEFAULT_CONFIG, IMAGES_DIR, MEDIA_DEFAULT_CONFIG, THEME_DIR, encode_config_value
from backend.app.models.entities import (
    AppConfigEntry,
    Bookshelf,
    NoteItem,
    ImageAsset,
    Note,
    Topic,
    TopicEraStat,
    TopicStat,
)
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

UNDATED_LABEL = "未定时间"
# Display styles for "entry" notes (axis 1); unlocked per data capability.
DISPLAY_STYLES = {"timeline", "table", "board", "gallery", "list", "outline"}
DEFAULT_DISPLAY_STYLE = "timeline"
# Container type (axis 0, "数字图书馆"): each type presets an ORDERED view set (first =
# default view). This is the container-level view gate replacing the data-capability
# gate on the FE.
CONTAINER_TYPES = {"notebook", "book", "album"}
DEFAULT_CONTAINER_TYPE = "notebook"
CONTAINER_TYPE_VIEWS = {
    "notebook": ["timeline", "list", "outline", "table", "board"],
    "book": ["outline", "table", "list", "timeline", "gallery"],
    "album": ["gallery", "board"],
}
# Center-column sort/grouping persisted per notebook.
GROUP_BY_DIMENSIONS = {"era", "year", "month"}
DEFAULT_GROUP_BY = "era"
DEFAULT_SORT_LEVELS = [{"field": "time", "dir": 1}]

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
SEARCH_INDEX_TABLE = "notes_fts"
DEFAULT_BOOKSHELF_NAME = "default"
DEFAULT_BOOKSHELF_TITLE = "编年"
QSTHEORY_BOOKSHELF_NAME = "qstheory"
QSTHEORY_BOOKSHELF_TITLE = "求是"
QSTHEORY_TOPIC_PREFIXES = ("求是网-", "求是杂志-")


def default_topic_columns_json() -> str:
    return json.dumps(DEFAULT_TOPIC_COLUMNS, ensure_ascii=False)


def normalize_display_style(value: str | None) -> str:
    candidate = str(value or "").strip()
    return candidate if candidate in DISPLAY_STYLES else DEFAULT_DISPLAY_STYLE


def normalize_container_type(value: str | None) -> str:
    candidate = str(value or "").strip()
    return candidate if candidate in CONTAINER_TYPES else DEFAULT_CONTAINER_TYPE


def container_type_views(container_type: str | None) -> list[str]:
    """Ordered view set a container of this type offers; first entry is the default."""
    return list(CONTAINER_TYPE_VIEWS[normalize_container_type(container_type)])


def container_default_view(container_type: str | None) -> str:
    return container_type_views(container_type)[0]


def normalize_group_by(value: str | None) -> str:
    candidate = str(value or "").strip()
    return candidate if candidate in GROUP_BY_DIMENSIONS else DEFAULT_GROUP_BY


def normalize_sort_levels(value) -> list[dict]:
    """Coerce a persisted/incoming sort into a clean ordered level list, mirroring
    the front-end normalizeSortLevels: each field appears once, dir is +1/-1, and
    there is always at least one level. Field names are NOT whitelisted here —
    custom column keys are dynamic; the front end clamps fields per view.

    One intentional divergence from the FE normalizer: an empty field is dropped
    here (stricter) rather than coerced to "time". It's inert in practice — the FE
    editor never emits empty fields and pre-normalizes before PUT — so a value with
    an empty field never round-trips."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            value = None
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return [dict(level) for level in DEFAULT_SORT_LEVELS]
    seen: set[str] = set()
    levels: list[dict] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field") or "").strip()
        if not field or field in seen:
            continue
        seen.add(field)
        try:
            direction = -1 if float(item.get("dir")) < 0 else 1
        except (TypeError, ValueError):
            direction = 1
        levels.append({"field": field, "dir": direction})
    return levels or [dict(level) for level in DEFAULT_SORT_LEVELS]


def undated_display_label() -> str:
    return UNDATED_LABEL


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
        "noteCount": int(event_count or 0),
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
    if signals.get("noteCount"):
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


def sanitize_bookshelf_name(name: str) -> str:
    return sanitize_topic_name(name)


def classify_topic_bookshelf(name: str | None, title: str | None) -> tuple[str, str]:
    for value in (str(name or "").strip(), str(title or "").strip()):
        if any(value.startswith(prefix) for prefix in QSTHEORY_TOPIC_PREFIXES):
            return QSTHEORY_BOOKSHELF_NAME, QSTHEORY_BOOKSHELF_TITLE
    return DEFAULT_BOOKSHELF_NAME, DEFAULT_BOOKSHELF_TITLE


def bookshelf_to_dict(bookshelf: Bookshelf, *, topic_count: int = 0, event_count: int = 0) -> dict:
    return {
        "id": bookshelf.id,
        "name": bookshelf.name,
        "title": bookshelf.title or bookshelf.name or "",
        "createdAt": serialize_datetime(bookshelf.created_at),
        "updatedAt": serialize_datetime(bookshelf.updated_at),
        "topicCount": int(topic_count or 0),
        "noteCount": int(event_count or 0),
    }


def topic_bookshelf_fields(topic: Topic) -> dict:
    bookshelf = topic.bookshelf
    return {
        "bookshelfId": int(topic.bookshelf_id) if topic.bookshelf_id is not None else (bookshelf.id if bookshelf else None),
        "bookshelfName": bookshelf.name if bookshelf else None,
        "bookshelfTitle": (bookshelf.title or bookshelf.name) if bookshelf else None,
    }


def ensure_bookshelf(db: Session, name: str, title: str) -> Bookshelf:
    bookshelf = db.query(Bookshelf).filter(Bookshelf.name == name).first()
    if bookshelf is not None:
        return bookshelf
    bookshelf = Bookshelf(name=name, title=title or name)
    db.add(bookshelf)
    db.flush()
    return bookshelf


def ensure_default_bookshelf(db: Session) -> Bookshelf:
    return ensure_bookshelf(db, DEFAULT_BOOKSHELF_NAME, DEFAULT_BOOKSHELF_TITLE)


def ensure_qstheory_bookshelf(db: Session) -> Bookshelf:
    return ensure_bookshelf(db, QSTHEORY_BOOKSHELF_NAME, QSTHEORY_BOOKSHELF_TITLE)


def ensure_topic_bookshelf_assignments(db: Session) -> int:
    changed = 0
    if db.query(Bookshelf.id).filter(Bookshelf.name == DEFAULT_BOOKSHELF_NAME).first() is None:
        ensure_default_bookshelf(db)
        changed += 1

    topics = db.query(Topic).filter(Topic.bookshelf_id.is_(None)).order_by(Topic.id.asc()).all()
    if not topics:
        return changed

    default_bookshelf = ensure_default_bookshelf(db)
    qstheory_bookshelf = None
    assigned = 0
    for topic in topics:
        bookshelf_name, _ = classify_topic_bookshelf(topic.name, topic.title)
        if bookshelf_name == QSTHEORY_BOOKSHELF_NAME:
            if qstheory_bookshelf is None:
                if db.query(Bookshelf.id).filter(Bookshelf.name == QSTHEORY_BOOKSHELF_NAME).first() is None:
                    changed += 1
                qstheory_bookshelf = ensure_qstheory_bookshelf(db)
            topic.bookshelf = qstheory_bookshelf
        else:
            topic.bookshelf = default_bookshelf
        assigned += 1
    return changed + assigned


def normalize_bookshelf_id(value, *, allow_none: bool = False) -> int | None:
    if value is None:
        if allow_none:
            return None
        raise HTTPException(status_code=400, detail="bookshelfId is required")
    try:
        bookshelf_id = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid bookshelfId") from exc
    if bookshelf_id <= 0:
        raise HTTPException(status_code=400, detail="Invalid bookshelfId")
    return bookshelf_id


def get_bookshelf_or_404(db: Session, bookshelf_id: int) -> Bookshelf:
    bookshelf = db.get(Bookshelf, bookshelf_id)
    if bookshelf is None:
        raise HTTPException(status_code=404, detail="Bookshelf not found")
    return bookshelf


def resolve_topic_bookshelf(db: Session, bookshelf_id=None) -> Bookshelf:
    if bookshelf_id is None:
        return ensure_default_bookshelf(db)
    normalized = normalize_bookshelf_id(bookshelf_id)
    bookshelf = db.get(Bookshelf, normalized)
    if bookshelf is None:
        raise HTTPException(status_code=400, detail="Bookshelf not found")
    return bookshelf


def topic_to_dict(topic: Topic) -> dict:
    container_type = normalize_container_type(topic.container_type)
    return {
        "id": topic.id,
        "name": topic.name,
        "title": topic.title or "",
        "subtitle": topic.subtitle or "",
        **topic_bookshelf_fields(topic),
        "columns": deserialize_json_list(topic.columns_json),
        "displayStyle": normalize_display_style(topic.display_style),
        "containerType": container_type,
        "views": container_type_views(container_type),
        "defaultView": container_default_view(container_type),
        "sort": normalize_sort_levels(topic.sort_json),
        "groupBy": normalize_group_by(topic.group_by),
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


def apply_note_state(event: Note, payload: dict):
    if "favorite" in payload:
        next_favorite = bool(payload.get("favorite"))
        if next_favorite and not event.favorite:
            event.favorite_at = datetime.now(timezone.utc)
        if not next_favorite:
            event.favorite_at = None
        event.favorite = next_favorite
    if "deletedAt" in payload:
        event.deleted_at = parse_optional_datetime(payload.get("deletedAt"))


def parse_cursor_key(part: str) -> int | None:
    """A cursor's date-key component is the raw ``date_key`` integer the server minted
    into ``next_cursor`` (year*10000 + month*100 + day) — NOT a human YYYYMMDD string.
    Parse it as an int so it round-trips for every year; routing it through
    ``parse_query_date_key`` 400s on 7-digit keys (year < 1000) and negative keys (BCE),
    and silently mis-parses 6-digit keys (year < 100)."""
    if part.lower() == "null":
        return None
    try:
        return int(part)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid cursor key") from exc


def parse_cursor_token(value: str | None) -> tuple[int | None, int | None] | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if ":" not in raw:
        return (None, None) if raw.lower() == "null" else (parse_cursor_key(raw), None)
    left, right = raw.split(":", 1)
    cursor_key = parse_cursor_key(left)
    try:
        cursor_id = int(right)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid cursor id") from exc
    return cursor_key, cursor_id


def note_display_label(event: Note) -> str:
    if event.date_key is None:
        return event.year or undated_display_label()
    return build_display_label(
        event.date_year or 0,
        event.date_month or 1,
        event.date_day or 1,
        event.headline or "",
    )


def serialize_items(event: Note) -> list[dict]:
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


def note_to_dict(event: Note) -> dict:
    headline = (event.headline or "").strip() or extract_headline_from_legacy_label(event.year or "")
    date_payload = note_date_payload(date_key=event.date_key, sort_key=event.sort_key, headline=headline)
    image_filename = event.image.filename if event.image else None
    thumb_filename = event.image.thumb_filename if event.image else None
    items = serialize_items(event)
    attachments = [build_attachment_payload(item) for item in deserialize_json_list(event.attachments_json)]
    return {
        "id": event.id,
        "topicId": event.topic_id,
        "nodeType": "note",
        **date_payload,
        "sortKey": event.sort_key,
        "headline": headline,
        "legacyYear": event.year,
        "era": event.era,
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
        "extra": deserialize_json_dict(event.extra_json),
        "attachments": attachments,
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


def markdown_preview_text(event: Note, *, max_length: int = 120) -> str:
    preview_text = str(event.preview_text or "").strip() or derive_note_text_fields_for_note(event)[0]
    return preview_text[:max_length].rstrip()


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


def derive_note_text_fields(
    *,
    body_markdown: str,
    items: list[dict],
    extra: dict,
    attachments: list[dict],
    topic: Topic | None,
) -> tuple[str, str]:
    plain_body = markdown_plain_text(body_markdown or default_body_markdown(items))

    preview_text = plain_body[:120].rstrip()
    search_parts = [
        plain_body,
        *[str(item.get("text", "")) for item in items if isinstance(item, dict)],
        extra_search_text(extra, topic),
        *[
            f"{attachment.get('name', '')} {attachment.get('filename', '')}"
            for attachment in attachments
            if isinstance(attachment, dict)
        ],
    ]
    search_text = re.sub(r"\s+", " ", " ".join(str(part or "") for part in search_parts)).strip()
    return preview_text, search_text


def derive_note_text_fields_for_note(
    event: Note,
    *,
    data: dict | None = None,
    topic: Topic | None = None,
) -> tuple[str, str]:
    if data is None:
        items = serialize_items(event)
        attachments = deserialize_json_list(event.attachments_json)
        extra = deserialize_json_dict(event.extra_json)
        body_markdown = event.body_markdown or default_body_markdown(items)
        topic = topic or event.topic
    else:
        items = data.get("items") or []
        attachments = data.get("attachments") or []
        extra = data.get("extra") or {}
        body_markdown = data.get("bodyMarkdown") or default_body_markdown(items)
    return derive_note_text_fields(
        body_markdown=str(body_markdown or ""),
        items=items,
        extra=extra if isinstance(extra, dict) else {},
        attachments=attachments if isinstance(attachments, list) else [],
        topic=topic,
    )


def build_search_payload(event: Note, data: dict | None = None, topic: Topic | None = None) -> dict:
    if data is None:
        items = serialize_items(event)
        extra = deserialize_json_dict(event.extra_json)
        headline = (event.headline or "").strip() or extract_headline_from_legacy_label(event.year or "")
        body_markdown = event.body_markdown or default_body_markdown(items)
        era = event.era
        topic = topic or event.topic
    else:
        items = data.get("items") or []
        extra = data.get("extra") or {}
        headline = str(data.get("headline") or "").strip() or extract_headline_from_legacy_label(data.get("legacyYear") or "")
        body_markdown = data.get("bodyMarkdown") or default_body_markdown(items)
        era = data.get("era")

    return {
        "note_id": event.id,
        "topic_id": event.topic_id,
        "headline": headline,
        "body": " ".join(
            part
            for part in [
                markdown_plain_text(str(body_markdown or "")),
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
              note_id UNINDEXED,
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


def remove_search_index_row(db: Session, note_id: int) -> None:
    ensure_search_schema(db)
    db.execute(text(f"DELETE FROM {SEARCH_INDEX_TABLE} WHERE note_id = :note_id"), {"note_id": int(note_id)})


def remove_search_index_topic(db: Session, topic_id: int) -> None:
    ensure_search_schema(db)
    db.execute(text(f"DELETE FROM {SEARCH_INDEX_TABLE} WHERE topic_id = :topic_id"), {"topic_id": int(topic_id)})


def insert_search_index_row(db: Session, payload: dict) -> None:
    db.execute(
        text(
            f"""
            INSERT INTO {SEARCH_INDEX_TABLE} (note_id, topic_id, headline, body, era, extra)
            VALUES (:note_id, :topic_id, :headline, :body, :era, :extra)
            """
        ),
        payload,
    )


def upsert_search_index_row(db: Session, event: Note, data: dict | None = None, topic: Topic | None = None) -> None:
    remove_search_index_row(db, event.id)
    if event.deleted_at:
        return
    insert_search_index_row(db, build_search_payload(event, data, topic))


def rebuild_search_index(db: Session) -> None:
    ensure_search_schema(db)
    db.execute(text(f"DELETE FROM {SEARCH_INDEX_TABLE}"))
    rows = (
        db.query(Note)
        .options(selectinload(Note.items), joinedload(Note.topic))
        .filter(Note.deleted_at.is_(None))
        .order_by(Note.topic_id.asc(), *note_order_clauses())
        .all()
    )
    for event in rows:
        insert_search_index_row(db, build_search_payload(event))


def search_index_needs_rebuild(db: Session) -> bool:
    ensure_search_schema(db)
    row = db.execute(text(f"SELECT COUNT(*) AS count FROM {SEARCH_INDEX_TABLE}")).mappings().first()
    indexed_count = int(row["count"] if row else 0)
    live_count = db.query(func.count(Note.id)).filter(Note.deleted_at.is_(None)).scalar() or 0
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


def search_notes(db: Session, query: str | None, limit: int = SEARCH_LIMIT_DEFAULT) -> list[dict]:
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
            JOIN notes e ON e.id = {SEARCH_INDEX_TABLE}.note_id
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
        date_key = resolve_note_date_key(row["date_key"], row["sort_key"])
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


def resolve_note_date_key(date_key: int | None, sort_key) -> int | None:
    if date_key is not None:
        return int(date_key)
    if sort_key in {None, "", 0, 0.0, "0"}:
        return None
    try:
        normalized = normalize_date_key(sort_key)
    except HTTPException:
        return None
    return normalized if normalized > 0 else None


def note_date_payload(*, date_key: int | None, sort_key, headline: str) -> dict:
    resolved = resolve_note_date_key(date_key, sort_key)
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


def note_index_search_text(event: Note, attachments: list[dict]) -> str:
    search_text = str(event.search_text or "").strip()
    if search_text:
        return search_text
    items = serialize_items(event)
    extra = deserialize_json_dict(event.extra_json)
    return derive_note_text_fields(
        body_markdown=event.body_markdown or default_body_markdown(items),
        items=items,
        extra=extra,
        attachments=attachments,
        topic=event.topic,
    )[1]


def note_to_list_dict(event: Note) -> dict:
    headline = (event.headline or "").strip() or extract_headline_from_legacy_label(event.year or "")
    date_payload = note_date_payload(date_key=event.date_key, sort_key=event.sort_key, headline=headline)
    image_filename = event.image.filename if event.image else None
    thumb_filename = event.image.thumb_filename if event.image else None
    attachments = deserialize_json_list(event.attachments_json)
    preview_text = str(event.preview_text or "").strip()
    search_text = str(event.search_text or "").strip()
    return {
        "id": event.id,
        "topicId": event.topic_id,
        "nodeType": "note",
        **date_payload,
        "sortKey": event.sort_key,
        "headline": headline,
        "legacyYear": event.year,
        "era": event.era,
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
    # Authoritative columns written on every create/update,
        # so the paginated list path reads them directly and never lazy-loads items/topic.
        "preview": preview_text,
        "searchText": search_text,
        "attachmentCount": len(attachments),
    }


def note_to_index_dict(event: Note) -> dict:
    headline = (event.headline or "").strip() or extract_headline_from_legacy_label(event.year or "")
    attachments = deserialize_json_list(event.attachments_json)
    date_payload = note_date_payload(date_key=event.date_key, sort_key=event.sort_key, headline=headline)
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
        "preview": str(event.preview_text or "").strip() or markdown_preview_text(event),
        "searchText": str(event.search_text or "").strip() or note_index_search_text(event, attachments),
        "attachmentCount": len(attachments),
    }


def serialize_note_rows(db: Session, rows: list[Note]) -> list[dict]:
    return [note_to_dict(event) for event in rows]


def live_topic_min_date_subquery():
    return (
        select(Note.date_key)
        .where(
            Note.topic_id == Topic.id,
            Note.deleted_at.is_(None),
            Note.date_key.is_not(None),
        )
        .order_by(Note.date_key.asc())
        .limit(1)
        .correlate(Topic)
        .scalar_subquery()
    )


def live_topic_max_date_subquery():
    return (
        select(Note.date_key)
        .where(
            Note.topic_id == Topic.id,
            Note.deleted_at.is_(None),
            Note.date_key.is_not(None),
        )
        .order_by(Note.date_key.desc())
        .limit(1)
        .correlate(Topic)
        .scalar_subquery()
    )


def get_or_create_topic_stat(db: Session, topic_id: int) -> TopicStat:
    stat = db.get(TopicStat, topic_id)
    if stat is not None:
        return stat
    stat = TopicStat(topic_id=topic_id)
    db.add(stat)
    db.flush()
    return stat


def rebuild_topic_stats_for_topic(db: Session, topic_id: int) -> TopicStat:
    db.flush()
    row = (
        db.query(
            func.coalesce(func.sum(case((Note.deleted_at.is_(None), 1), else_=0)), 0),
            func.coalesce(func.sum(case((Note.deleted_at.is_not(None), 1), else_=0)), 0),
            func.coalesce(
                func.sum(case((and_(Note.deleted_at.is_(None), Note.favorite.is_(True)), 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(case((and_(Note.deleted_at.is_(None), Note.image_id.is_not(None)), 1), else_=0)),
                0,
            ),
        )
        .filter(Note.topic_id == topic_id)
        .one()
    )
    stat = get_or_create_topic_stat(db, topic_id)
    stat.live_event_count = int(row[0] or 0)
    stat.deleted_event_count = int(row[1] or 0)
    stat.favorite_count = int(row[2] or 0)
    stat.image_count = int(row[3] or 0)
    stat.updated_at = datetime.now(timezone.utc)
    return stat


def rebuild_topic_era_stats_for_topic(db: Session, topic_id: int) -> None:
    db.flush()
    # synchronize_session="fetch" evicts the deleted rows from the identity map so a
    # re-add of the same (topic_id, era) PK in this session doesn't collide (matters
    # when rebuild runs twice in one session, e.g. batch/admin rebuilds).
    db.query(TopicEraStat).filter(TopicEraStat.topic_id == topic_id).delete(synchronize_session="fetch")
    # Group by the SAME normalized value we store, so distinct raw eras that
    # normalize equal (e.g. "" and a typed "未分组", or whitespace
    # variants) collapse into one row instead of colliding on the (topic_id, era)
    # primary key. The ordering matches the client-side collection sort.
    era_value = case(
        (func.trim(func.coalesce(Note.era, "")) == "", "未分组"),
        else_=func.trim(Note.era),
    )
    rows = (
        db.query(
            era_value.label("era"),
            func.count(Note.id).label("live_event_count"),
            func.min(Note.date_key).label("min_date_key"),
        )
        .filter(Note.topic_id == topic_id, Note.deleted_at.is_(None))
        .group_by(era_value)
        .all()
    )
    now = datetime.now(timezone.utc)
    for era, live_event_count, min_date_key in rows:
        db.add(
            TopicEraStat(
                topic_id=topic_id,
                era=era,
                live_event_count=int(live_event_count or 0),
                min_date_key=int(min_date_key) if min_date_key is not None else None,
                updated_at=now,
            )
        )


def rebuild_topic_read_models(db: Session, topic_ids: list[int] | None = None) -> None:
    db.flush()
    target_ids = topic_ids
    if target_ids is None:
        target_ids = [int(topic_id) for (topic_id,) in db.query(Topic.id).order_by(Topic.id.asc()).all()]
    for topic_id in target_ids:
        rebuild_topic_stats_for_topic(db, topic_id)
        rebuild_topic_era_stats_for_topic(db, topic_id)


def ensure_topic_read_models(db: Session) -> None:
    topic_count = db.query(func.count(Topic.id)).scalar() or 0
    stat_count = db.query(func.count(TopicStat.topic_id)).scalar() or 0
    live_event_count = (
        db.query(func.count(Note.id)).filter(Note.deleted_at.is_(None)).scalar() or 0
    )
    era_count = db.query(func.count(TopicEraStat.topic_id)).scalar() or 0
    if topic_count != stat_count or (live_event_count > 0 and era_count == 0):
        rebuild_topic_read_models(db)


def rebuild_topic_text_fields_and_search(db: Session, topic: Topic) -> None:
    rows = (
        db.query(Note)
        .options(selectinload(Note.items))
        .filter(Note.topic_id == topic.id)
        .all()
    )
    for event in rows:
        preview_text, search_text = derive_note_text_fields_for_note(event, topic=topic)
        event.preview_text = preview_text
        event.search_text = search_text
        upsert_search_index_row(db, event, topic=topic)
    if rows:
        db.flush()


def topic_list_item(topic: Topic, stat: TopicStat | None, min_date_key, max_date_key) -> dict:
    live_event_count = int(stat.live_event_count if stat is not None else 0)
    image_count = int(stat.image_count if stat is not None else 0)
    return {
        **topic_to_dict(topic),
        "noteCount": live_event_count,
        "minDateKey": int(min_date_key) if min_date_key is not None else None,
        "maxDateKey": int(max_date_key) if max_date_key is not None else None,
        "minDate": date_key_to_iso(int(min_date_key)) if min_date_key is not None else None,
        "maxDate": date_key_to_iso(int(max_date_key)) if max_date_key is not None else None,
        **topic_capabilities_block(
            topic,
            event_count=live_event_count,
            has_dated=max_date_key is not None,
            has_image=image_count > 0,
        ),
    }


def get_topic_or_404(db: Session, topic_id: int) -> Topic:
    topic = db.query(Topic).options(joinedload(Topic.bookshelf)).filter(Topic.id == topic_id).first()
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    return topic


def get_note_or_404(db: Session, note_id: int) -> Note:
    event = (
        db.query(Note)
        .options(selectinload(Note.items), joinedload(Note.image), joinedload(Note.topic))
        .filter(Note.id == note_id)
        .first()
    )
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


def build_topic_bounds(db: Session, topic_id: int) -> dict:
    stat = db.get(TopicStat, topic_id)
    min_date_key = (
        db.query(Note.date_key)
        .filter(
            Note.topic_id == topic_id,
            Note.deleted_at.is_(None),
            Note.date_key.is_not(None),
        )
        .order_by(Note.date_key.asc())
        .limit(1)
        .scalar()
    )
    max_date_key = (
        db.query(Note.date_key)
        .filter(
            Note.topic_id == topic_id,
            Note.deleted_at.is_(None),
            Note.date_key.is_not(None),
        )
        .order_by(Note.date_key.desc())
        .limit(1)
        .scalar()
    )
    return {
        "noteCount": int(stat.live_event_count if stat is not None else 0),
        "minDateKey": int(min_date_key) if min_date_key is not None else None,
        "maxDateKey": int(max_date_key) if max_date_key is not None else None,
        "minDate": date_key_to_iso(min_date_key) if min_date_key is not None else None,
        "maxDate": date_key_to_iso(max_date_key) if max_date_key is not None else None,
        "hasImage": int(stat.image_count if stat is not None else 0) > 0,
        "supportedZoomLevels": SUPPORTED_ZOOM_LEVELS,
    }


def note_order_clauses(direction: int = 1):
    """Feed ordering. `direction` (+1 asc / -1 desc) flips only the *dated* region:
    undated events always sink to the bottom (the `date_key IS NULL` bucket stays
    `.asc()` regardless of direction — a note with no date is not "the newest"), and
    `id` stays ascending as a stable tiebreak. Default +1 keeps every existing
    no-arg caller (index/search/related/list) byte-for-byte unchanged."""
    date_clause = Note.date_key.desc() if direction < 0 else Note.date_key.asc()
    return (
        case((Note.date_key.is_(None), 1), else_=0).asc(),
        date_clause,
        Note.id.asc(),
    )


def list_topics(db: Session) -> list[dict]:
    min_date_key = live_topic_min_date_subquery()
    max_date_key = live_topic_max_date_subquery()
    rows = (
        db.query(
            Topic,
            TopicStat,
            min_date_key.label("min_date_key"),
            max_date_key.label("max_date_key"),
        )
        .options(joinedload(Topic.bookshelf))
        .outerjoin(TopicStat, TopicStat.topic_id == Topic.id)
        .order_by(Topic.id.asc())
        .all()
    )
    return [topic_list_item(topic, stat, row_min_date_key, row_max_date_key) for topic, stat, row_min_date_key, row_max_date_key in rows]


def list_bookshelves(db: Session) -> list[dict]:
    rows = (
        db.query(
            Bookshelf,
            func.count(func.distinct(Topic.id)).label("topic_count"),
            func.coalesce(func.sum(TopicStat.live_event_count), 0).label("event_count"),
        )
        .outerjoin(Topic, Topic.bookshelf_id == Bookshelf.id)
        .outerjoin(TopicStat, TopicStat.topic_id == Topic.id)
        .group_by(Bookshelf.id)
        .order_by(Bookshelf.id.asc())
        .all()
    )
    return [
        bookshelf_to_dict(
            bookshelf,
            topic_count=int(topic_count or 0),
            event_count=int(event_count or 0),
        )
        for bookshelf, topic_count, event_count in rows
    ]


def list_bookshelf_tree(db: Session) -> list[dict]:
    shelves = [{**bookshelf, "topics": []} for bookshelf in list_bookshelves(db)]
    by_name = {shelf["name"]: shelf for shelf in shelves}
    topics = list_topics(db)
    era_rows = (
        db.query(TopicEraStat)
        .order_by(
            TopicEraStat.topic_id.asc(),
            case((TopicEraStat.min_date_key.is_(None), 1), else_=0).asc(),
            TopicEraStat.min_date_key.asc(),
            TopicEraStat.era.asc(),
        )
        .all()
    )
    eras_by_topic: dict[int, list[dict]] = {}
    for row in era_rows:
        eras_by_topic.setdefault(int(row.topic_id), []).append(
            {"era": row.era, "count": int(row.live_event_count or 0)}
        )
    for topic in topics:
        shelf_name = str(topic.get("bookshelfName") or "").strip() or DEFAULT_BOOKSHELF_NAME
        shelf = by_name.get(shelf_name)
        if shelf is None:
            shelf = {
                "id": topic.get("bookshelfId"),
                "name": shelf_name,
                "title": topic.get("bookshelfTitle") or shelf_name,
                "createdAt": None,
                "updatedAt": None,
                "topicCount": 0,
                "noteCount": 0,
                "topics": [],
            }
            shelves.append(shelf)
            by_name[shelf_name] = shelf
        shelf["topics"].append({"topic": topic, "eras": eras_by_topic.get(int(topic["id"]), [])})
    return shelves


def create_bookshelf(db: Session, payload: dict) -> dict:
    safe = sanitize_bookshelf_name(str(payload.get("name", "")).strip())
    if not safe:
        raise HTTPException(status_code=400, detail="Invalid bookshelf name")
    if safe in {DEFAULT_BOOKSHELF_NAME, QSTHEORY_BOOKSHELF_NAME}:
        raise HTTPException(status_code=400, detail="Bookshelf name is reserved")
    exists = db.query(Bookshelf).filter(Bookshelf.name == safe).first()
    if exists:
        raise HTTPException(status_code=409, detail="Bookshelf already exists")
    title = str(payload.get("title") or safe).strip() or safe
    bookshelf = Bookshelf(name=safe, title=title)
    db.add(bookshelf)
    db.commit()
    db.refresh(bookshelf)
    return bookshelf_to_dict(bookshelf)


def update_bookshelf(db: Session, bookshelf_id: int, payload: dict) -> dict:
    bookshelf = get_bookshelf_or_404(db, bookshelf_id)
    if "name" in payload:
        safe = sanitize_bookshelf_name(str(payload.get("name", "")).strip())
        if not safe:
            raise HTTPException(status_code=400, detail="Invalid bookshelf name")
        if safe != bookshelf.name:
            raise HTTPException(status_code=400, detail="Bookshelf name is immutable")
    if "title" in payload:
        title = str(payload.get("title") or "").strip()
        bookshelf.title = title or bookshelf.title or bookshelf.name
    db.commit()
    db.refresh(bookshelf)
    return bookshelf_to_dict(bookshelf)


def delete_bookshelf(db: Session, bookshelf_id: int) -> dict:
    bookshelf = get_bookshelf_or_404(db, bookshelf_id)
    topic_count = db.query(func.count(Topic.id)).filter(Topic.bookshelf_id == bookshelf.id).scalar() or 0
    if int(topic_count or 0) > 0:
        raise HTTPException(status_code=409, detail="Bookshelf is not empty")
    db.delete(bookshelf)
    db.commit()
    return {"ok": True}


def create_topic(db: Session, name: str, bookshelf_id=None) -> dict:
    safe = sanitize_topic_name(name)
    if not safe:
        raise HTTPException(status_code=400, detail="Invalid topic name")
    exists = db.query(Topic).filter(Topic.name == safe).first()
    if exists:
        raise HTTPException(status_code=409, detail="Topic already exists")
    if bookshelf_id is None:
        bookshelf_name, _ = classify_topic_bookshelf(safe, safe)
        bookshelf = ensure_qstheory_bookshelf(db) if bookshelf_name == QSTHEORY_BOOKSHELF_NAME else ensure_default_bookshelf(db)
    else:
        bookshelf = resolve_topic_bookshelf(db, bookshelf_id)
    topic = Topic(
        name=safe,
        title=safe,
        subtitle="",
        bookshelf=bookshelf,
        columns_json=default_topic_columns_json(),
    )
    db.add(topic)
    db.flush()
    rebuild_topic_read_models(db, [topic.id])
    db.commit()
    db.refresh(topic)
    return {
        **topic_to_dict(topic),
        **topic_capabilities_block(topic, event_count=0, has_dated=False, has_image=False),
    }


def delete_topic(db: Session, topic_id: int):
    topic = get_topic_or_404(db, topic_id)
    events = (
        db.query(Note)
        .options(joinedload(Note.image))
        .filter(Note.topic_id == topic_id)
        .all()
    )
    image_ids = {event.image_id for event in events if event.image_id}
    remove_search_index_topic(db, topic_id)
    db.query(TopicEraStat).filter(TopicEraStat.topic_id == topic_id).delete(synchronize_session=False)
    db.query(TopicStat).filter(TopicStat.topic_id == topic_id).delete(synchronize_session=False)
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
            event_count=bounds["noteCount"],
            has_dated=bounds["maxDateKey"] is not None,
            has_image=bounds["hasImage"],
        ),
    }


def update_topic_meta(db: Session, topic_id: int, payload: dict) -> dict:
    topic = get_topic_or_404(db, topic_id)
    columns_changed = False
    if "title" in payload:
        topic.title = str(payload["title"] or "").strip()
    if "subtitle" in payload:
        topic.subtitle = str(payload["subtitle"] or "").strip()
    if "bookshelfId" in payload:
        topic.bookshelf = resolve_topic_bookshelf(db, normalize_bookshelf_id(payload.get("bookshelfId")))
    if "displayStyle" in payload:
        topic.display_style = normalize_display_style(payload.get("displayStyle"))
    if "containerType" in payload:
        topic.container_type = normalize_container_type(payload.get("containerType"))
        # Changing the container type re-gates the view set, so clamp the active view
        # into the new set (fall to the type's default). Only on an explicit type
        # change — existing notebooks keep any of the 6 views until they pick a type.
        views = container_type_views(topic.container_type)
        if normalize_display_style(topic.display_style) not in views:
            topic.display_style = views[0]
    if "sort" in payload:
        topic.sort_json = json.dumps(normalize_sort_levels(payload.get("sort")), ensure_ascii=False)
    if "groupBy" in payload:
        topic.group_by = normalize_group_by(payload.get("groupBy"))
    if "columns" in payload:
        topic.columns_json = json.dumps(normalize_topic_columns(payload.get("columns")), ensure_ascii=False)
        columns_changed = True
    if columns_changed:
        rebuild_topic_text_fields_and_search(db, topic)
    db.commit()
    db.refresh(topic)
    return get_topic_meta(db, topic_id)


def build_note_query(db: Session, topic_id: int):
    return (
        db.query(Note)
        .options(selectinload(Note.items), joinedload(Note.image))
        .filter(Note.topic_id == topic_id)
    )


def build_note_list_query(db: Session, topic_id: int):
    return (
        db.query(Note)
        .options(joinedload(Note.image))
        .filter(Note.topic_id == topic_id)
    )


def list_topic_notes(db: Session, topic_id: int) -> list[dict]:
    get_topic_or_404(db, topic_id)
    events = build_note_query(db, topic_id).order_by(*note_order_clauses()).all()
    return serialize_note_rows(db, events)


def get_note_detail(db: Session, note_id: int) -> dict:
    return serialize_note_rows(db, [get_note_or_404(db, note_id)])[0]


def build_timeline_index(db: Session) -> dict:
    rows = (
        db.query(Note)
        .options(selectinload(Note.items), joinedload(Note.image))
        .order_by(Note.topic_id.asc(), *note_order_clauses())
        .all()
    )
    return {
        "topics": list_topics(db),
        "notes": [note_to_index_dict(event) for event in rows],
    }


def query_topic_notes(
    db: Session,
    topic_id: int,
    *,
    from_key: int | None = None,
    to_key: int | None = None,
    cursor: tuple[int | None, int | None] | None = None,
    limit: int | None = 100,
    direction: int = 1,
) -> dict:
    get_topic_or_404(db, topic_id)
    direction = -1 if direction < 0 else 1
    bounds = build_topic_bounds(db, topic_id)
    safe_limit = max(1, min(int(limit or 100), 500))
    query = build_note_list_query(db, topic_id)

    if from_key is not None:
        query = query.filter(Note.date_key >= from_key)
    if to_key is not None:
        query = query.filter(Note.date_key <= to_key)
    if cursor is not None:
        cursor_key, cursor_id = cursor
        # Direction only flips the *dated* walk (older-ward when descending). The
        # undated tail (date_key IS NULL, id-ascending) always trails all dated rows
        # regardless of direction, so its cursor logic is identical both ways. Only
        # build the dated comparison when there IS a dated key: a "null:<id>" tail
        # cursor has cursor_key=None, and `date_key < None` raises at query-build time.
        dated_after = None
        if cursor_key is not None:
            dated_after = (
                Note.date_key < cursor_key if direction < 0 else Note.date_key > cursor_key
            )
        if cursor_id is None:
            if cursor_key is not None:
                query = query.filter(or_(dated_after, Note.date_key.is_(None)))
        else:
            if cursor_key is None:
                query = query.filter(and_(Note.date_key.is_(None), Note.id > cursor_id))
            else:
                query = query.filter(
                    or_(
                        dated_after,
                        Note.date_key.is_(None),
                        and_(Note.date_key == cursor_key, Note.id > cursor_id),
                    )
                )

    query = query.order_by(*note_order_clauses(direction))
    query = query.limit(safe_limit + 1)

    rows = query.all()
    has_more = False
    next_cursor = None

    if len(rows) > safe_limit:
        has_more = True
        rows = rows[:safe_limit]

    if rows and has_more:
        last_row = rows[-1]
        next_cursor = f"{last_row.date_key if last_row.date_key is not None else 'null'}:{last_row.id}"

    return {
        "items": [note_to_list_dict(event) for event in rows],
        "bounds": bounds,
        "range": {
            "from": from_key,
            "to": to_key,
            "cursor": cursor[0] if cursor else None,
            "limit": safe_limit,
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
        "noteCount": event_count,
        "era": f"{event_count} notes",
        "image": None,
        "items": [
            {
                "tag": "summary",
                "text": f"{event_count} events between {date_key_to_iso(range_start_key)} and {date_key_to_iso(range_end_key)}",
            }
        ],
    }


def summarize_topic_notes(
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
        bucket_expr = Note.date_year
    elif group_by == "month":
        bucket_expr = Note.date_year * 100 + Note.date_month
    else:
        raise HTTPException(status_code=400, detail="groupBy must be 'year' or 'month'")

    query = db.query(
        bucket_expr.label("bucket_key"),
        func.count(Note.id).label("event_count"),
        func.min(Note.date_key).label("range_start_key"),
        func.max(Note.date_key).label("range_end_key"),
    ).filter(
        Note.topic_id == topic_id,
        Note.deleted_at.is_(None),
        Note.date_key.is_not(None),
    )

    if from_key is not None:
        query = query.filter(Note.date_key >= from_key)
    if to_key is not None:
        query = query.filter(Note.date_key <= to_key)

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


# Body is the canonical content (body_markdown). NoteItem is the legacy body
# store; its `tag` is no longer a property source, just a non-null filler.
DEFAULT_ITEM_TAG = "note"


def derive_items_from_markdown(body_markdown: str) -> list[dict]:
    chunks = [segment.strip() for segment in str(body_markdown or "").split("\n\n") if segment.strip()]
    if not chunks:
        return []
    return [{"tag": DEFAULT_ITEM_TAG, "text": chunk} for chunk in chunks]


def normalize_note_items(payload: dict, body_markdown: str | None = None) -> list[dict]:
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


def normalize_note_payload(payload: dict, *, topic: Topic | None = None) -> dict:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload must be an object")

    image = payload.get("image")
    era = str(payload.get("era", "")).strip()
    # A note is "dated" only when a date part actually carries a value — a present-but-null
    # key counts as undated, matching the front end (a blank date field → undated note).
    has_date_parts = any(payload.get(key) is not None for key in {"dateYear", "dateMonth", "dateDay"})
    uses_structured_contract = bool({"headline", "dateYear", "dateMonth", "dateDay"} & set(payload.keys()))
    if not era and has_date_parts:
        raise HTTPException(status_code=400, detail="Era is required")
    body_markdown = str(payload.get("bodyMarkdown", "")).strip()
    items = normalize_note_items(payload, body_markdown)
    attachments = normalize_attachments(payload)
    extra = normalize_extra(payload, topic)
    state = {}
    if "favorite" in payload:
        state["favorite"] = bool(payload.get("favorite"))
    if "deletedAt" in payload:
        state["deletedAt"] = parse_optional_datetime(payload.get("deletedAt"))

    headline = str(payload.get("headline", "")).strip()
    # A note without date parts stays in the undated tail of time-ordered views.
    if uses_structured_contract and has_date_parts:
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
            "bodyMarkdown": body_markdown or default_body_markdown(items),
            "extra": extra,
            "attachments": attachments,
            "items": items,
            "image": image,
            **state,
        }

    if uses_structured_contract:
        # No date parts means the note stays in the undated tail of time-ordered views.
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
            "bodyMarkdown": body_markdown or default_body_markdown(items),
            "extra": extra,
            "attachments": attachments,
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
        "extra": extra,
        "attachments": attachments,
        "items": items,
        "image": image,
        **state,
    }


def write_note_model(event: Note, data: dict, image: ImageAsset | None, *, topic: Topic | None = None):
    preview_text, search_text = derive_note_text_fields_for_note(event, data=data, topic=topic or event.topic)
    event.year = data["legacyYear"]
    event.sort_key = data["sortKey"]
    event.date_key = data["dateKey"]
    event.date_year = data["dateYear"]
    event.date_month = data["dateMonth"]
    event.date_day = data["dateDay"]
    event.headline = data["headline"]
    event.era = data["era"]
    event.body_markdown = data["bodyMarkdown"]
    event.preview_text = preview_text
    event.search_text = search_text
    event.extra_json = json.dumps(data["extra"], ensure_ascii=False)
    event.attachments_json = json.dumps(data["attachments"], ensure_ascii=False)
    event.image = image
    next_favorite = bool(data.get("favorite", event.favorite))
    if next_favorite and not event.favorite:
        event.favorite_at = event.favorite_at or datetime.now(timezone.utc)
    if not next_favorite:
        event.favorite_at = None
    event.favorite = next_favorite
    if "deletedAt" in data:
        event.deleted_at = data["deletedAt"]


def create_note(db: Session, topic_id: int, payload: dict) -> dict:
    topic = get_topic_or_404(db, topic_id)
    data = normalize_note_payload(payload, topic=topic)
    image = resolve_image(db, data["image"])
    event = Note(topic_id=topic.id)
    write_note_model(event, data, image, topic=topic)
    db.add(event)
    db.flush()
    for index, item in enumerate(data["items"]):
        db.add(NoteItem(note_id=event.id, tag=item["tag"], text=item["text"], sort_order=index))
    upsert_search_index_row(db, event, data, topic)
    rebuild_topic_read_models(db, [topic.id])
    db.commit()
    db.refresh(event)
    return serialize_note_rows(db, [get_note_or_404(db, event.id)])[0]


def _require_note_version(event: Note, expected_updated_at: str | None) -> None:
    if expected_updated_at is None:
        raise HTTPException(
            status_code=428,
            detail={
                "code": "precondition_required",
                "message": "笔记写入需要读取时的 updatedAt 版本。",
                "nextAction": "读取笔记详情，并将 updatedAt 原样放入 If-Match 请求头。",
                "details": {"resourceType": "note", "resourceId": event.id},
            },
        )
    current_version = serialize_datetime(event.updated_at)
    if expected_updated_at != current_version:
        _raise_note_version_conflict(event, expected_updated_at)


def _raise_note_version_conflict(event: Note, expected_updated_at: str) -> None:
    raise HTTPException(
        status_code=409,
        detail={
            "code": "version_conflict",
            "message": "笔记已在读取后发生变化，本次写入未应用。",
            "nextAction": "重新读取笔记并协调差异；不要重放旧正文。",
            "details": {
                "resourceType": "note",
                "resourceId": event.id,
                "expectedVersion": expected_updated_at,
                "currentVersion": serialize_datetime(event.updated_at),
            },
        },
    )


def _reserve_note_version(db: Session, event: Note, expected_updated_at: str) -> None:
    _require_note_version(event, expected_updated_at)
    current = event.updated_at
    current_utc = current.replace(tzinfo=timezone.utc) if current.tzinfo is None else current.astimezone(timezone.utc)
    next_version = datetime.now(timezone.utc)
    if next_version <= current_utc:
        next_version = current_utc + timedelta(microseconds=1)
    try:
        result = db.execute(
            update(Note)
            .where(Note.id == event.id, Note.updated_at == current)
            .values(updated_at=next_version)
            .execution_options(synchronize_session=False)
        )
    except OperationalError as exc:
        db.rollback()
        if "locked" not in str(exc).lower() and "busy" not in str(exc).lower():
            raise
        current_event = get_note_or_404(db, event.id)
        _raise_note_version_conflict(current_event, expected_updated_at)
    if result.rowcount != 1:
        db.rollback()
        current_event = get_note_or_404(db, event.id)
        _raise_note_version_conflict(current_event, expected_updated_at)
    event.updated_at = next_version


def _note_matches_write(event: Note, payload: dict) -> bool:
    if payload and set(payload).issubset(EVENT_STATE_KEYS):
        if event.deleted_at and not (set(payload) == {"deletedAt"} and payload.get("deletedAt") is None):
            return False
        favorite = bool(payload.get("favorite", event.favorite))
        deleted_at = (
            parse_optional_datetime(payload.get("deletedAt"))
            if "deletedAt" in payload
            else event.deleted_at
        )
        return favorite == bool(event.favorite) and serialize_datetime(deleted_at) == serialize_datetime(event.deleted_at)

    data = normalize_note_payload(payload, topic=event.topic)
    data["extra"] = merge_orphan_extra(
        deserialize_json_dict(event.extra_json), data["extra"], event.topic
    )
    current_image = event.image.filename if event.image else None
    expected_deleted_at = data.get("deletedAt", event.deleted_at)
    expected_favorite = bool(data.get("favorite", event.favorite))
    current = {
        "dateYear": event.date_year,
        "dateMonth": event.date_month,
        "dateDay": event.date_day,
        "headline": event.headline or "",
        "legacyYear": event.year,
        "era": event.era,
        "bodyMarkdown": event.body_markdown or "",
        "extra": deserialize_json_dict(event.extra_json),
        "attachments": deserialize_json_list(event.attachments_json),
        "items": serialize_items(event),
        "image": current_image,
    }
    expected = {
        "dateYear": data["dateYear"],
        "dateMonth": data["dateMonth"],
        "dateDay": data["dateDay"],
        "headline": data["headline"],
        "legacyYear": data["legacyYear"],
        "era": data["era"],
        "bodyMarkdown": data["bodyMarkdown"],
        "extra": data["extra"],
        "attachments": data["attachments"],
        "items": data["items"],
        "image": data["image"],
    }
    same_content = all(
        json.dumps(current[key], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        == json.dumps(expected[key], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for key in current
    )
    return (
        same_content
        and expected_favorite == bool(event.favorite)
        and serialize_datetime(expected_deleted_at) == serialize_datetime(event.deleted_at)
    )


def update_note(
    db: Session,
    note_id: int,
    payload: dict,
    *,
    expected_updated_at: str | None = None,
    require_version: bool = False,
) -> dict:
    event = get_note_or_404(db, note_id)
    if require_version and expected_updated_at is None:
        _require_note_version(event, None)
    if expected_updated_at is not None:
        current_version = serialize_datetime(event.updated_at)
        if expected_updated_at != current_version:
            if event.deleted_at and not (
                set(payload or {}) == {"deletedAt"} and (payload or {}).get("deletedAt") is None
            ):
                _require_note_version(event, expected_updated_at)
            if isinstance(payload, dict) and _note_matches_write(event, payload):
                return serialize_note_rows(db, [event])[0]
            _require_note_version(event, expected_updated_at)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload must be an object")
    if not payload:
        raise HTTPException(status_code=400, detail="At least one note field is required")

    if payload and set(payload.keys()).issubset(EVENT_STATE_KEYS):
        if event.deleted_at and not (set(payload.keys()) == {"deletedAt"} and payload.get("deletedAt") is None):
            raise HTTPException(status_code=409, detail="Deleted events can only be restored")
        if "deletedAt" in payload:
            payload = {**payload, "deletedAt": parse_optional_datetime(payload.get("deletedAt"))}
        if expected_updated_at is not None:
            _reserve_note_version(db, event, expected_updated_at)
        apply_note_state(event, payload)
        upsert_search_index_row(db, event, topic=event.topic)
        rebuild_topic_read_models(db, [event.topic_id])
        db.commit()
        return serialize_note_rows(db, [get_note_or_404(db, event.id)])[0]

    if event.deleted_at:
        raise HTTPException(status_code=409, detail="Deleted events cannot be edited")

    old_image_id = event.image_id
    data = normalize_note_payload(payload, topic=event.topic)
    data["extra"] = merge_orphan_extra(deserialize_json_dict(event.extra_json), data["extra"], event.topic)
    image = resolve_image(db, data["image"])
    if expected_updated_at is not None:
        _reserve_note_version(db, event, expected_updated_at)
    write_note_model(event, data, image, topic=event.topic)
    for item in list(event.items):
        db.delete(item)
    db.flush()
    for index, item in enumerate(data["items"]):
        db.add(NoteItem(note_id=event.id, tag=item["tag"], text=item["text"], sort_order=index))
    upsert_search_index_row(db, event, data, event.topic)
    rebuild_topic_read_models(db, [event.topic_id])
    db.commit()
    if old_image_id and old_image_id != event.image_id:
        cleanup_orphan_images(db, {old_image_id})
    return serialize_note_rows(db, [get_note_or_404(db, event.id)])[0]


def delete_note(
    db: Session,
    note_id: int,
    *,
    permanent: bool = False,
    expected_updated_at: str | None = None,
    require_version: bool = False,
):
    event = get_note_or_404(db, note_id)
    if require_version and expected_updated_at is None:
        _require_note_version(event, None)
    if expected_updated_at is not None:
        _reserve_note_version(db, event, expected_updated_at)
    old_image_id = event.image_id
    if not permanent:
        event.deleted_at = datetime.now(timezone.utc)
        remove_search_index_row(db, event.id)
        rebuild_topic_read_models(db, [event.topic_id])
        db.commit()
        return {
            "ok": True,
            "deletedAt": serialize_datetime(event.deleted_at),
            "updatedAt": serialize_datetime(event.updated_at),
        }

    remove_search_index_row(db, event.id)
    db.delete(event)
    rebuild_topic_read_models(db, [event.topic_id])
    db.commit()
    cleanup_orphan_images(db, {old_image_id} if old_image_id else set())
    return {"ok": True}


def lift_import_date_parts(item):
    """Reshape one exported event so its date round-trips through import.

    The export nests the date under `dateParts` (see note_date_payload) and emits no
    top-level dateYear/dateMonth/dateDay — the exact keys normalize_note_payload keys
    on. Lift them back before normalizing so a dated note re-imports dated instead of
    silently becoming undated (dateKey=None). A payload that already carries top-level
    date keys, or whose dateParts is all-null (a genuinely undated note), is left as-is.
    """
    if not isinstance(item, dict) or any(key in item for key in ("dateYear", "dateMonth", "dateDay")):
        return item
    parts = item.get("dateParts")
    if not isinstance(parts, dict):
        return item
    year, month, day = parts.get("year"), parts.get("month"), parts.get("day")
    if year is None and month is None and day is None:
        return item
    return {**item, "dateYear": year, "dateMonth": month, "dateDay": day}


def import_topic_data(db: Session, topic_id: int, parsed: object) -> dict:
    topic = get_topic_or_404(db, topic_id)
    if isinstance(parsed, dict):
        title = parsed.get("title", "")
        subtitle = parsed.get("subtitle", "")
        columns = parsed.get("columns", [])
        raw_events = parsed.get("notes", parsed.get("events", []))  # W6-3: read new "notes"; fall back to legacy "events" export files
    elif isinstance(parsed, list):
        title = topic.title
        subtitle = topic.subtitle
        columns = deserialize_json_list(topic.columns_json)
        raw_events = parsed
    else:
        raise ValueError("JSON must be an array or object with notes")

    topic.columns_json = json.dumps(normalize_topic_columns(columns), ensure_ascii=False)
    normalized_events = [normalize_note_payload(lift_import_date_parts(item), topic=topic) for item in raw_events]

    existing_events = db.query(Note).filter(Note.topic_id == topic.id).all()
    old_image_ids = {event.image_id for event in existing_events if event.image_id}
    remove_search_index_topic(db, topic.id)
    for event in existing_events:
        db.delete(event)
    db.flush()

    topic.title = str(title or "").strip()
    topic.subtitle = str(subtitle or "").strip()
    for node in normalized_events:
        image = resolve_image(db, node["image"])
        event = Note(topic_id=topic.id)
        write_note_model(event, node, image, topic=topic)
        db.add(event)
        db.flush()
        for index, item in enumerate(node["items"]):
            db.add(NoteItem(note_id=event.id, tag=item["tag"], text=item["text"], sort_order=index))
        upsert_search_index_row(db, event, node, topic)
    rebuild_topic_read_models(db, [topic.id])
    db.commit()
    cleanup_orphan_images(db, old_image_ids)
    return {"ok": True, "count": len(normalized_events)}


def export_topic_data(db: Session, topic_id: int, *, from_key: int | None = None, to_key: int | None = None):
    topic = get_topic_or_404(db, topic_id)
    query = build_note_query(db, topic_id)
    if from_key is not None:
        query = query.filter(Note.date_key >= from_key)
    if to_key is not None:
        query = query.filter(Note.date_key <= to_key)
    rows = query.order_by(*note_order_clauses()).all()
    content = {
        "schemaVersion": 2,
        "title": topic.title or "",
        "subtitle": topic.subtitle or "",
        "columns": deserialize_json_list(topic.columns_json),
        "notes": serialize_note_rows(db, rows),
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
        still_used = db.query(Note.id).filter(Note.image_id == image.id).first()
        if not still_used:
            attachment_reference = (
                db.query(Note.id)
                .filter(Note.attachments_json.like(f'%"{image.filename}"%'))
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
    linked = db.query(Note.id).filter(Note.image_id == image.id).first()
    if linked is None:
        linked = (
            db.query(Note.id)
            .filter(Note.attachments_json.like(f'%"{image.filename}"%'))
            .first()
        )
    if linked:
        raise HTTPException(status_code=409, detail="Image is still in use")
    unlink_asset_files(image)
    db.delete(image)
    db.commit()
    return {"ok": True}
