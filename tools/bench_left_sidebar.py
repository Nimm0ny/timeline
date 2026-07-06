#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gc
import json
import sqlite3
import statistics
import sys
import tempfile
import time
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.session import Base
from backend.app.services.timeline import backfill_event_text_fields, list_bookshelf_tree, rebuild_topic_read_models


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark legacy vs read-model left-sidebar data paths.")
    parser.add_argument("--shelves", type=int, default=4, help="Number of bookshelves")
    parser.add_argument("--topics-per-shelf", type=int, default=50, help="Topics per bookshelf")
    parser.add_argument("--events-per-topic", type=int, default=500, help="Events per topic")
    parser.add_argument("--eras-per-topic", type=int, default=8, help="Distinct eras per topic")
    parser.add_argument("--runs", type=int, default=5, help="Benchmark runs per scenario")
    return parser.parse_args()


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def chunked(iterable, size: int):
    batch = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def create_database(db_path: Path) -> tuple:
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return engine, SessionLocal


def seed_database(db_path: Path, *, shelves: int, topics_per_shelf: int, events_per_topic: int, eras_per_topic: int) -> dict:
    engine, SessionLocal = create_database(db_path)
    now = utcnow_iso()
    try:
        with sqlite3.connect(db_path) as conn:
            bookshelf_rows = []
            topic_rows = []
            event_rows = []
            shelf_id = 1
            topic_id = 1
            event_id = 1
            for shelf_index in range(shelves):
                bookshelf_rows.append((shelf_id, f"shelf_{shelf_id}", f"Bookshelf {shelf_id}", now, now))
                for topic_index in range(topics_per_shelf):
                    topic_rows.append(
                        (
                            topic_id,
                            f"topic_{topic_id}",
                            f"Topic {topic_id}",
                            "",
                            shelf_id,
                            "[]",
                            "timeline",
                            "[]",
                            "era",
                            now,
                            now,
                        )
                    )
                    for event_index in range(events_per_topic):
                        month = (event_index // 28) % 12 + 1
                        day = event_index % 28 + 1
                        year = 1800 + (topic_id % 100) + event_index // 336
                        date_key = year * 10000 + month * 100 + day
                        era_bucket = max(1, events_per_topic // eras_per_topic)
                        era = f"Era {(event_index // era_bucket) + 1}"
                        headline = f"Event {event_id}"
                        body = f"Body {event_id} in {era}"
                        event_rows.append(
                            (
                                event_id,
                                topic_id,
                                headline,
                                float(date_key),
                                date_key,
                                year,
                                month,
                                day,
                                headline,
                                era,
                                "entry",
                                body,
                                body[:120],
                                body,
                                None,
                                "{}",
                                "[]",
                                "[]",
                                None,
                                now,
                                now,
                                0,
                                None,
                                None,
                            )
                        )
                        event_id += 1
                    topic_id += 1
                shelf_id += 1

            conn.executemany(
                "INSERT INTO bookshelves (id, name, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                bookshelf_rows,
            )
            conn.executemany(
                """
                INSERT INTO topics (
                  id, name, title, subtitle, bookshelf_id, columns_json, display_style, sort_json, group_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                topic_rows,
            )
            for batch in chunked(event_rows, 5000):
                conn.executemany(
                    """
                    INSERT INTO timeline_events (
                      id, topic_id, year, sort_key, date_key, date_year, date_month, date_day, headline, era,
                      note_type, body_markdown, preview_text, search_text, body_json, extra_json, attachments_json,
                      related_event_ids_json, image_id, created_at, updated_at, favorite, favorite_at, deleted_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    batch,
                )

        with SessionLocal() as db:
            backfill_event_text_fields(db)
            rebuild_topic_read_models(db)
            db.commit()

        return {
            "engine": engine,
            "SessionLocal": SessionLocal,
            "topic_count": shelves * topics_per_shelf,
            "event_count": shelves * topics_per_shelf * events_per_topic,
        }
    except Exception:
        engine.dispose()
        raise


def legacy_list_topics(conn: sqlite3.Connection):
    return conn.execute(
        """
        SELECT
          t.id,
          t.name,
          t.title,
          t.subtitle,
          t.bookshelf_id,
          b.name AS bookshelf_name,
          b.title AS bookshelf_title,
          COUNT(e.id) AS event_count,
          MIN(e.date_key) AS min_date_key,
          MAX(e.date_key) AS max_date_key
        FROM topics t
        LEFT JOIN bookshelves b ON b.id = t.bookshelf_id
        LEFT JOIN timeline_events e ON e.topic_id = t.id
        GROUP BY t.id
        ORDER BY t.id ASC
        """
    ).fetchall()


def legacy_list_bookshelves(conn: sqlite3.Connection):
    return conn.execute(
        """
        SELECT
          b.id,
          b.name,
          b.title,
          COUNT(DISTINCT t.id) AS topic_count,
          COUNT(e.id) AS event_count
        FROM bookshelves b
        LEFT JOIN topics t ON t.bookshelf_id = b.id
        LEFT JOIN timeline_events e ON e.topic_id = t.id
        GROUP BY b.id
        ORDER BY b.id ASC
        """
    ).fetchall()


def legacy_build_tree(conn: sqlite3.Connection, topics):
    shelves = {
        row["bookshelf_name"] or "default": {
            "id": row["bookshelf_id"],
            "name": row["bookshelf_name"] or "default",
            "title": row["bookshelf_title"] or row["bookshelf_name"] or "default",
            "topicCount": 0,
            "eventCount": 0,
            "topics": [],
        }
        for row in topics
    }
    events_by_topic: dict[int, list[sqlite3.Row]] = {}
    for row in conn.execute(
        """
        SELECT topic_id, era, deleted_at, date_key, id
        FROM timeline_events
        ORDER BY topic_id ASC, CASE WHEN date_key IS NULL THEN 1 ELSE 0 END ASC, date_key ASC, id ASC
        """
    ):
        if row["deleted_at"] is not None:
            continue
        events_by_topic.setdefault(int(row["topic_id"]), []).append(row)
    for row in topics:
        shelf = shelves[row["bookshelf_name"] or "default"]
        eras = []
        counts = {}
        for event in events_by_topic.get(int(row["id"]), []):
            era = (event["era"] or "").strip() or "未分组"
            if era not in counts:
                counts[era] = {"era": era, "count": 0}
                eras.append(counts[era])
            counts[era]["count"] += 1
        shelf["topicCount"] += 1
        shelf["eventCount"] += int(row["event_count"] or 0)
        shelf["topics"].append(
            {
                "topic": {
                    "id": row["id"],
                    "name": row["name"],
                    "title": row["title"],
                    "eventCount": int(row["event_count"] or 0),
                },
                "eras": eras,
            }
        )
    return list(shelves.values())


def measure(label: str, runs: int, fn):
    timings = []
    result = None
    for _ in range(runs):
        start = time.perf_counter()
        result = fn()
        timings.append((time.perf_counter() - start) * 1000)
    return {
        "label": label,
        "avg_ms": round(statistics.mean(timings), 2),
        "min_ms": round(min(timings), 2),
        "max_ms": round(max(timings), 2),
        "result_size": len(result) if hasattr(result, "__len__") else None,
    }


def main() -> int:
    args = parse_args()
    tmp_dir = Path(tempfile.mkdtemp(prefix="timeline-left-bench-"))
    engine = None
    try:
        db_path = tmp_dir / "bench.db"
        seeded = seed_database(
            db_path,
            shelves=args.shelves,
            topics_per_shelf=args.topics_per_shelf,
            events_per_topic=args.events_per_topic,
            eras_per_topic=args.eras_per_topic,
        )
        engine = seeded["engine"]
        SessionLocal = seeded["SessionLocal"]
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            legacy_topics = measure("legacy_list_topics", args.runs, lambda: legacy_list_topics(conn))
            legacy_shelves = measure("legacy_list_bookshelves", args.runs, lambda: legacy_list_bookshelves(conn))
            legacy_topic_rows = legacy_list_topics(conn)
            legacy_tree = measure("legacy_tree_build", args.runs, lambda: legacy_build_tree(conn, legacy_topic_rows))
        def current_tree():
            with SessionLocal() as db:
                return list_bookshelf_tree(db)

        new_tree = measure("read_model_bookshelf_tree", args.runs, current_tree)
        legacy_total = round(legacy_topics["avg_ms"] + legacy_shelves["avg_ms"] + legacy_tree["avg_ms"], 2)
        improvement = round(legacy_total / new_tree["avg_ms"], 2) if new_tree["avg_ms"] else None
        payload = {
            "dataset": {
                "bookshelves": args.shelves,
                "topics": seeded["topic_count"],
                "events": seeded["event_count"],
                "events_per_topic": args.events_per_topic,
                "eras_per_topic": args.eras_per_topic,
            },
            "legacy": {
                "topics_ms": legacy_topics["avg_ms"],
                "bookshelves_ms": legacy_shelves["avg_ms"],
                "tree_build_ms": legacy_tree["avg_ms"],
                "total_ms": legacy_total,
            },
            "current": {
                "bookshelf_tree_ms": new_tree["avg_ms"],
            },
            "speedup": {
                "legacy_total_div_current": improvement,
                "saved_ms": round(legacy_total - new_tree["avg_ms"], 2),
            },
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    finally:
        if engine is not None:
            engine.dispose()
        gc.collect()
        for _ in range(10):
            try:
                shutil.rmtree(tmp_dir)
                break
            except PermissionError:
                time.sleep(0.2)


if __name__ == "__main__":
    raise SystemExit(main())
