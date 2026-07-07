#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.core.config import IMAGES_DIR
from backend.app.db.session import SessionLocal
from backend.app.models.entities import Bookshelf, ImageAsset, TimelineEvent, Topic, TopicEraStat, TopicStat
from backend.app.services.date_utils import build_display_label, make_date_key
from backend.app.services.timeline import rebuild_topic_read_models

TOPIC_PREFIX = "zzPerfTimelineQA"
SHELF_NAME = "zz_perf_timeline_loading"
SHELF_TITLE = "性能专项 QA"
VIEWS = ["timeline", "table", "list", "gallery", "board", "outline"]
PLACEHOLDER_FILENAME = "zz-perf-placeholder.svg"
PLACEHOLDER_MIME = "image/svg+xml"
TYPE_OPTIONS = [
    {"id": "war", "label": "战争", "color": "var(--t-war)"},
    {"id": "politics", "label": "政治", "color": "var(--t-politics)"},
    {"id": "reform", "label": "改革", "color": "var(--t-reform)"},
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or clean dedicated loading-performance QA topics.")
    parser.add_argument("--count", type=int, default=5000, help="Events per generated topic (default: 5000)")
    parser.add_argument("--cleanup", action="store_true", help="Delete the generated QA topics and shelf")
    parser.add_argument("--base-url", default="http://127.0.0.1:8798", help="Base frontend URL printed in results")
    return parser.parse_args()


def utcnow():
    return datetime.now(timezone.utc)


def ensure_placeholder_asset(db) -> int:
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    asset = db.query(ImageAsset).filter(ImageAsset.filename == PLACEHOLDER_FILENAME).first()
    if asset:
        placeholder_path = IMAGES_DIR / PLACEHOLDER_FILENAME
        if not placeholder_path.exists():
            placeholder_path.write_text(
                "<svg xmlns='http://www.w3.org/2000/svg' width='640' height='480' viewBox='0 0 640 480'>"
                "<rect width='640' height='480' fill='#ece8df'/>"
                "<path d='M0 340 L170 210 L300 300 L430 150 L640 360 V480 H0 Z' fill='#d2cbc0'/>"
                "<circle cx='120' cy='110' r='34' fill='#f3efe8'/>"
                "<text x='320' y='250' text-anchor='middle' fill='#6f6a62' font-size='26' font-family='Segoe UI, Arial, sans-serif'>"
                "Chronicle QA"
                "</text></svg>",
                encoding="utf-8",
            )
        return asset.id
    placeholder_path = IMAGES_DIR / PLACEHOLDER_FILENAME
    placeholder_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' width='640' height='480' viewBox='0 0 640 480'>"
        "<rect width='640' height='480' fill='#ece8df'/>"
        "<path d='M0 340 L170 210 L300 300 L430 150 L640 360 V480 H0 Z' fill='#d2cbc0'/>"
        "<circle cx='120' cy='110' r='34' fill='#f3efe8'/>"
        "<text x='320' y='250' text-anchor='middle' fill='#6f6a62' font-size='26' font-family='Segoe UI, Arial, sans-serif'>"
        "Chronicle QA"
        "</text></svg>",
        encoding="utf-8",
    )
    now = utcnow()
    asset = ImageAsset(
        filename=PLACEHOLDER_FILENAME,
        original_name=PLACEHOLDER_FILENAME,
        mime_type=PLACEHOLDER_MIME,
        is_orphan=False,
        created_at=now,
    )
    db.add(asset)
    db.flush()
    return asset.id


def ensure_shelf(db) -> Bookshelf:
    shelf = db.query(Bookshelf).filter(Bookshelf.name == SHELF_NAME).first()
    if shelf:
        return shelf
    shelf = Bookshelf(name=SHELF_NAME, title=SHELF_TITLE)
    db.add(shelf)
    db.flush()
    return shelf


def cleanup_topics(db) -> None:
    topics = db.query(Topic).filter(Topic.name.like(f"{TOPIC_PREFIX}%")).all()
    topic_ids = [topic.id for topic in topics]
    if topic_ids:
        db.query(TimelineEvent).filter(TimelineEvent.topic_id.in_(topic_ids)).delete(synchronize_session=False)
        db.query(TopicEraStat).filter(TopicEraStat.topic_id.in_(topic_ids)).delete(synchronize_session=False)
        db.query(TopicStat).filter(TopicStat.topic_id.in_(topic_ids)).delete(synchronize_session=False)
        db.query(Topic).filter(Topic.id.in_(topic_ids)).delete(synchronize_session=False)
    db.flush()
    shelf = db.query(Bookshelf).filter(Bookshelf.name == SHELF_NAME).first()
    if shelf and not shelf.topics:
        db.delete(shelf)
    asset = db.query(ImageAsset).filter(ImageAsset.filename == PLACEHOLDER_FILENAME).first()
    if asset:
        referenced = db.query(TimelineEvent.id).filter(TimelineEvent.image_id == asset.id).first()
        if not referenced:
            db.delete(asset)
            placeholder_path = IMAGES_DIR / PLACEHOLDER_FILENAME
            if placeholder_path.exists():
                placeholder_path.unlink()
    db.flush()


def topic_columns_json() -> str:
    return json.dumps(
        [
            {
                "key": "type",
                "label": "类型",
                "type": "select",
                "width": 96,
                "order": 0,
                "visible": True,
                "options": TYPE_OPTIONS,
            }
        ],
        ensure_ascii=False,
    )


def build_topic_rows(shelf_id: int) -> list[dict]:
    now = utcnow()
    columns_json = topic_columns_json()
    rows = []
    for view in VIEWS:
        rows.append(
            {
                "name": f"{TOPIC_PREFIX}-{view}",
                "title": f"{TOPIC_PREFIX} · {view}",
                "subtitle": "Loading Performance QA",
                "bookshelf_id": shelf_id,
                "columns_json": columns_json,
                "display_style": view,
                "sort_json": "[]",
                "group_by": "era",
                "created_at": now,
                "updated_at": now,
            }
        )
    return rows


def build_event_rows(topic_id: int, count: int, image_id: int) -> list[dict]:
    now = utcnow()
    rows = []
    for offset in range(count):
        year = 1800 + offset // 336
        month = (offset // 28) % 12 + 1
        day = offset % 28 + 1
        date_key = make_date_key(year, month, day)
        era = f"Era {(offset // max(1, count // 5)) + 1}"
        headline = f"Perf Event {offset + 1}"
        body = f"Performance body {offset + 1} in {era}. Search token {offset + 1}."
        rows.append(
            {
                "topic_id": topic_id,
                "year": build_display_label(year, month, day, headline),
                "sort_key": float(date_key),
                "date_key": date_key,
                "date_year": year,
                "date_month": month,
                "date_day": day,
                "headline": headline,
                "era": era,
                "note_type": "entry",
                "body_markdown": body,
                "preview_text": body[:120],
                "search_text": body,
                "body_json": None,
                "extra_json": json.dumps({"type": TYPE_OPTIONS[offset % len(TYPE_OPTIONS)]["id"]}, ensure_ascii=False),
                "attachments_json": "[]",
                "related_event_ids_json": "[]",
                "image_id": image_id if offset % 5 == 0 else None,
                "created_at": now,
                "updated_at": now,
                "favorite": False,
                "favorite_at": None,
                "deleted_at": None,
            }
        )
    return rows


def create_topics(db, count: int, base_url: str) -> list[str]:
    cleanup_topics(db)
    shelf = ensure_shelf(db)
    image_id = ensure_placeholder_asset(db)
    topics = []
    for row in build_topic_rows(shelf.id):
        topic = Topic(**row)
        db.add(topic)
        db.flush()
        topics.append(topic)

    event_rows = []
    for topic in topics:
        event_rows.extend(build_event_rows(topic.id, count, image_id))
    db.execute(TimelineEvent.__table__.insert(), event_rows)
    db.flush()
    rebuild_topic_read_models(db, [topic.id for topic in topics])
    db.commit()
    return [f"{base_url}/?topic={topic.id}&mode=view" for topic in topics]


def main() -> int:
    args = parse_args()
    with SessionLocal() as db:
        if args.cleanup:
            cleanup_topics(db)
            db.commit()
            print(f"Removed {TOPIC_PREFIX} topics and shelf {SHELF_NAME} when present.")
            return 0

        urls = create_topics(db, args.count, args.base_url.rstrip("/"))
        print("Loading performance QA topics ready:")
        for view, url in zip(VIEWS, urls, strict=True):
            print(f"- {view}: {url}")
        print(f"- cleanup: python tools/bench_timeline_loading.py --cleanup")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
