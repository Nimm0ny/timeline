#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET
from zipfile import ZipFile


WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
DEFAULT_TOPIC_COLUMNS = [
    {"key": "type", "label": "类型", "type": "select", "width": 96, "order": 0, "visible": True, "options": []},
    {"key": "tags", "label": "标签", "type": "multiselect", "width": 150, "order": 1, "visible": True, "options": []},
]
DEFAULT_SORT = [{"field": "time", "dir": 1}]
DEFAULT_GROUP_BY = "era"
DEFAULT_DISPLAY_STYLE = "outline"
DEFAULT_NOTE_TYPE = "entry"
UNDATED_LABEL = "未定时间"
SEARCH_INDEX_TABLE = "timeline_events_fts"


@dataclass
class Subsection:
    title: str
    paragraphs: list[str] = field(default_factory=list)


@dataclass
class Section:
    title: str
    intro: list[str] = field(default_factory=list)
    subsections: list[Subsection] = field(default_factory=list)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import a DOCX as bookshelf/topic outline notes split by level-1 headings."
    )
    parser.add_argument("--docx", required=True, help="Source DOCX path")
    parser.add_argument("--db-path", required=True, help="SQLite database path")
    parser.add_argument("--shelf-name", default="整理理论", help="Bookshelf stable name")
    parser.add_argument("--shelf-title", default="整理理论", help="Bookshelf title")
    parser.add_argument("--bookshelf-id", type=int, help="Existing bookshelf id to target explicitly")
    parser.add_argument("--topic-name", default="纲要", help="Topic stable name")
    parser.add_argument("--topic-title", default="纲要", help="Topic title")
    parser.add_argument("--topic-id", type=int, help="Existing topic id to target explicitly")
    parser.add_argument(
        "--topic-subtitle",
        default="《习近平新时代中国特色社会主义思想学习纲要》按一级章节整理",
        help="Topic subtitle",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace all existing notes in the target topic before importing",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only parse and print the discovered structure",
    )
    return parser.parse_args()


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_spaces(text: str) -> str:
    text = text.replace("\u3000", " ")
    return re.sub(r"\s+", " ", text).strip()


def paragraph_style_name(style_map: dict[str, str], paragraph: ET.Element) -> str:
    style = paragraph.find("w:pPr/w:pStyle", WORD_NS)
    if style is None:
        return ""
    style_id = style.attrib.get(f"{{{WORD_NS['w']}}}val", "")
    return style_map.get(style_id, style_id)


def paragraph_text(paragraph: ET.Element) -> str:
    texts = [node.text or "" for node in paragraph.findall(".//w:t", WORD_NS)]
    return normalize_spaces("".join(texts))


def read_docx_sections(docx_path: Path) -> list[Section]:
    with ZipFile(docx_path) as docx:
        styles_xml = ET.fromstring(docx.read("word/styles.xml"))
        document_xml = ET.fromstring(docx.read("word/document.xml"))

    style_map: dict[str, str] = {}
    for style in styles_xml.findall("w:style", WORD_NS):
        style_id = style.attrib.get(f"{{{WORD_NS['w']}}}styleId", "")
        name = style.find("w:name", WORD_NS)
        style_map[style_id] = name.attrib.get(f"{{{WORD_NS['w']}}}val", "") if name is not None else style_id

    sections: list[Section] = []
    current_section: Section | None = None
    current_subsection: Subsection | None = None
    started = False

    for paragraph in document_xml.findall(".//w:body/w:p", WORD_NS):
        text = paragraph_text(paragraph)
        if not text:
            continue
        style = paragraph_style_name(style_map, paragraph).lower()

        if style == "heading 1":
            started = True
            current_section = Section(title=text)
            sections.append(current_section)
            current_subsection = None
            continue
        if not started or current_section is None:
            continue
        if style == "heading 2":
            current_subsection = Subsection(title=text)
            current_section.subsections.append(current_subsection)
            continue

        if current_subsection is not None:
            current_subsection.paragraphs.append(text)
        else:
            current_section.intro.append(text)

    if not sections:
        raise ValueError(f"No level-1 headings found in {docx_path}")
    return sections


def read_docx_title(docx_path: Path) -> str:
    with ZipFile(docx_path) as docx:
        document_xml = ET.fromstring(docx.read("word/document.xml"))
    for paragraph in document_xml.findall(".//w:body/w:p", WORD_NS):
        text = paragraph_text(paragraph)
        if text and text != "目录":
            return text
    return docx_path.stem


def section_to_markdown(section: Section, *, source_title: str) -> str:
    lines: list[str] = [f"> 来源：{source_title}", ""]
    if section.intro:
        lines.extend(section.intro)
        lines.append("")
    for subsection in section.subsections:
        lines.append(f"## {subsection.title}")
        lines.append("")
        lines.extend(subsection.paragraphs or ["（原文此节无正文）"])
        lines.append("")
    return "\n".join(lines).strip()


def markdown_plain_text(source: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", source)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[#>*_`~\-\[\]()]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def ensure_search_index(conn: sqlite3.Connection) -> None:
    conn.execute(
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


def require_tables(conn: sqlite3.Connection, names: Iterable[str]) -> None:
    existing = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")
    }
    missing = [name for name in names if name not in existing]
    if missing:
        raise RuntimeError(f"Missing required tables: {', '.join(missing)}")


def get_bookshelf(conn: sqlite3.Connection, shelf_name: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id, name, title FROM bookshelves WHERE name = ?",
        (shelf_name,),
    ).fetchone()


def get_bookshelf_by_id(conn: sqlite3.Connection, bookshelf_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id, name, title FROM bookshelves WHERE id = ?",
        (bookshelf_id,),
    ).fetchone()


def resolve_bookshelf(conn: sqlite3.Connection, *, shelf_name: str, shelf_title: str, bookshelf_id: int | None) -> int:
    if bookshelf_id is not None:
        row = get_bookshelf_by_id(conn, bookshelf_id)
        if row is None:
            raise RuntimeError(f"Bookshelf id {bookshelf_id} does not exist")
        return int(row["id"])

    row = get_bookshelf(conn, shelf_name)
    now = utcnow_iso()
    if row is not None:
        raise RuntimeError(
            f"Bookshelf name '{shelf_name}' already exists as id={row['id']}. "
            "Pass --bookshelf-id to target it explicitly."
        )
    cursor = conn.execute(
        """
        INSERT INTO bookshelves (name, title, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        (shelf_name, shelf_title, now, now),
    )
    return int(cursor.lastrowid)


def get_topic(conn: sqlite3.Connection, topic_name: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT id, name, title, subtitle, bookshelf_id
        FROM topics
        WHERE name = ?
        """,
        (topic_name,),
    ).fetchone()


def get_topic_by_id(conn: sqlite3.Connection, topic_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT id, name, title, subtitle, bookshelf_id
        FROM topics
        WHERE id = ?
        """,
        (topic_id,),
    ).fetchone()


def resolve_topic(
    conn: sqlite3.Connection,
    *,
    topic_name: str,
    topic_title: str,
    topic_subtitle: str,
    bookshelf_id: int,
    topic_id: int | None,
) -> int:
    now = utcnow_iso()
    if topic_id is not None:
        row = get_topic_by_id(conn, topic_id)
        if row is None:
            raise RuntimeError(f"Topic id {topic_id} does not exist")
        conn.execute(
            """
            UPDATE topics
            SET title = ?, subtitle = ?, bookshelf_id = ?, display_style = ?, group_by = ?, updated_at = ?
            WHERE id = ?
            """,
            (topic_title, topic_subtitle, bookshelf_id, DEFAULT_DISPLAY_STYLE, DEFAULT_GROUP_BY, now, row["id"]),
        )
        return int(row["id"])

    row = get_topic(conn, topic_name)
    if row is not None:
        raise RuntimeError(
            f"Topic name '{topic_name}' already exists as id={row['id']}. "
            "Pass --topic-id to target it explicitly."
        )

    cursor = conn.execute(
        """
        INSERT INTO topics (
          name, title, subtitle, bookshelf_id, columns_json, display_style, sort_json, group_by, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            topic_name,
            topic_title,
            topic_subtitle,
            bookshelf_id,
            json.dumps(DEFAULT_TOPIC_COLUMNS, ensure_ascii=False),
            DEFAULT_DISPLAY_STYLE,
            json.dumps(DEFAULT_SORT, ensure_ascii=False),
            DEFAULT_GROUP_BY,
            now,
            now,
        ),
    )
    return int(cursor.lastrowid)


def remove_topic_events(conn: sqlite3.Connection, topic_id: int) -> None:
    event_ids = [row["id"] for row in conn.execute("SELECT id FROM timeline_events WHERE topic_id = ?", (topic_id,))]
    if not event_ids:
        return
    placeholders = ",".join("?" for _ in event_ids)
    conn.execute(f"DELETE FROM {SEARCH_INDEX_TABLE} WHERE topic_id = ?", (topic_id,))
    conn.execute(f"DELETE FROM event_items WHERE event_id IN ({placeholders})", event_ids)
    conn.execute(f"DELETE FROM timeline_events WHERE id IN ({placeholders})", event_ids)


def insert_note(conn: sqlite3.Connection, *, topic_id: int, headline: str, era: str, body_markdown: str) -> int:
    now = utcnow_iso()
    cursor = conn.execute(
        """
        INSERT INTO timeline_events (
          topic_id, year, sort_key, date_key, date_year, date_month, date_day, headline, era,
          note_type, body_markdown, body_json, extra_json, attachments_json, related_event_ids_json,
          image_id, created_at, updated_at, favorite, favorite_at, deleted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            topic_id,
            UNDATED_LABEL,
            0.0,
            None,
            None,
            None,
            None,
            headline,
            era,
            DEFAULT_NOTE_TYPE,
            body_markdown,
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
        ),
    )
    event_id = int(cursor.lastrowid)
    conn.execute(
        f"""
        INSERT INTO {SEARCH_INDEX_TABLE} (event_id, topic_id, headline, body, era, extra)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (event_id, topic_id, headline, markdown_plain_text(body_markdown), era, ""),
    )
    return event_id


def build_import_payload(docx_path: Path) -> list[dict]:
    sections = read_docx_sections(docx_path)
    source_title = read_docx_title(docx_path)
    payload = []
    for section in sections:
        payload.append(
            {
                "headline": section.title,
                "era": section.title,
                "bodyMarkdown": section_to_markdown(section, source_title=source_title),
            }
        )
    return payload


def print_outline(notes: list[dict]) -> None:
    print(f"notes={len(notes)}")
    for index, note in enumerate(notes, 1):
        body = note["bodyMarkdown"]
        subsection_count = len(re.findall(r"^## ", body, flags=re.MULTILINE))
        print(f"{index:02d}. {note['headline']} | subsections={subsection_count} | chars={len(body)}")


def main() -> int:
    args = parse_args()
    docx_path = Path(args.docx).expanduser().resolve()
    db_path = Path(args.db_path).expanduser().resolve()
    if not docx_path.exists():
        raise FileNotFoundError(f"Missing DOCX: {docx_path}")
    if not db_path.exists():
        raise FileNotFoundError(f"Missing database: {db_path}")

    notes = build_import_payload(docx_path)
    print_outline(notes)
    if args.dry_run:
        return 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        require_tables(conn, ["bookshelves", "topics", "timeline_events", "event_items"])
        ensure_search_index(conn)
        with conn:
            bookshelf_id = resolve_bookshelf(
                conn,
                shelf_name=args.shelf_name.strip(),
                shelf_title=args.shelf_title.strip() or args.shelf_name.strip(),
                bookshelf_id=args.bookshelf_id,
            )
            topic_id = resolve_topic(
                conn,
                topic_name=args.topic_name.strip(),
                topic_title=args.topic_title.strip() or args.topic_name.strip(),
                topic_subtitle=args.topic_subtitle.strip(),
                bookshelf_id=bookshelf_id,
                topic_id=args.topic_id,
            )
            if args.replace:
                remove_topic_events(conn, topic_id)
            for note in notes:
                insert_note(
                    conn,
                    topic_id=topic_id,
                    headline=note["headline"],
                    era=note["era"],
                    body_markdown=note["bodyMarkdown"],
                )
    finally:
        conn.close()

    print(f"imported_topic={args.topic_name.strip()} imported_notes={len(notes)} db={db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
