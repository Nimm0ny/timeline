"""W4 link system: [[wikilink]] parse/resolve/sync + backlinks + batch preview.

The link graph is keyed by note id, not title, so rename/move never breaks an edge;
backlinks are one indexed lookup on timeline_links(target_event_id), not a body scan.
See docs/notes-app-pivot-design.md §6.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.session import Base
from backend.app.models.entities import TimelineEvent, TimelineLink
from backend.app.services import legacy_migration as legacy_migration_module
from backend.app.services.timeline import (
    batch_event_previews,
    create_event,
    create_topic,
    delete_event,
    get_backlinks,
    get_event_detail,
    parse_snapshot_embeds,
    parse_wikilinks,
    update_event,
)


def _session(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'links.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(legacy_migration_module, "engine", engine)
    legacy_migration_module.ensure_timeline_event_schema()
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)(), engine


def _entry(db, topic_id, headline, body=""):
    # An entry note requires a non-empty body (items derive from markdown); default to
    # the headline so callers can omit a body when only the note's identity matters.
    return create_event(
        db, topic_id, {"headline": headline, "era": "", "bodyMarkdown": body or headline, "noteType": "entry"}
    )


def _embed_cell(note_id, headline="", preview=""):
    # An embed card as the FE persists it: only data.kind/noteId reach the backend parser
    # (the Vue-shape node renders live from these + a batch-preview refresh). headline/preview
    # ride in data so the walker can index the canvas by what it embeds without a DB round-trip.
    return {
        "id": f"em-{note_id}",
        "shape": "embed-card",
        "data": {"kind": "embed", "noteId": note_id, "headline": headline, "preview": preview},
    }


def _canvas(db, topic_id, headline, cells):
    return create_event(
        db,
        topic_id,
        {
            "headline": headline,
            "era": "",
            "bodyMarkdown": "",
            "noteType": "canvas",
            "bodyJson": {"_fmt": "x6-canvas-v1", "cells": cells},
            "items": [],
        },
    )


def _resave_canvas(db, event_id, headline, cells):
    return update_event(
        db,
        event_id,
        {
            "headline": headline,
            "era": "",
            "bodyMarkdown": "",
            "noteType": "canvas",
            "bodyJson": {"_fmt": "x6-canvas-v1", "cells": cells},
            "items": [],
        },
    )


def test_parse_wikilinks_id_bare_and_context():
    links = parse_wikilinks("intro\nsee [[42|Napoleon]] and [[Waterloo]] here\nend")
    assert [(link["id"], link["title"]) for link in links] == [(42, "Napoleon"), (None, "Waterloo")]
    # Context is the whole surrounding line; positions are byte offsets in document order.
    assert links[0]["context"] == "see [[42|Napoleon]] and [[Waterloo]] here"
    assert links[0]["position"] < links[1]["position"]


def test_parse_ignores_empty_and_malformed():
    assert parse_wikilinks("[[]] [[  ]] [[|noid]] plain text") == []


def test_sync_and_backlinks_id_anchored(tmp_path, monkeypatch):
    db, engine = _session(tmp_path, monkeypatch)
    try:
        topic = create_topic(db, "t1", None)
        target = _entry(db, topic["id"], "Target Note")
        source = _entry(db, topic["id"], "Source", body=f"body [[{target['id']}|Target Note]] done")
        back = get_backlinks(db, target["id"])
        assert back["total"] == 1
        item = back["items"][0]
        assert item["sourceId"] == source["id"]
        assert item["headline"] == "Source"
        assert item["anchorType"] == "wikilink"
        assert "[[" in item["contextText"]
    finally:
        db.close()
        engine.dispose()


def test_bare_title_resolves_only_on_unique_headline(tmp_path, monkeypatch):
    db, engine = _session(tmp_path, monkeypatch)
    try:
        topic = create_topic(db, "t1", None)
        unique = _entry(db, topic["id"], "UniqueTitle")
        _entry(db, topic["id"], "Src", body="ref [[UniqueTitle]] end")
        assert get_backlinks(db, unique["id"])["total"] == 1

        # Two notes share a headline → a bare [[Dup]] is ambiguous → dangling, no backlink.
        dup_a = _entry(db, topic["id"], "Dup")
        _entry(db, topic["id"], "Dup")
        _entry(db, topic["id"], "Ambi", body="[[Dup]]")
        assert get_backlinks(db, dup_a["id"])["total"] == 0
    finally:
        db.close()
        engine.dispose()


def test_resync_on_edit_and_rename_keeps_link(tmp_path, monkeypatch):
    db, engine = _session(tmp_path, monkeypatch)
    try:
        topic = create_topic(db, "t1", None)
        target = _entry(db, topic["id"], "T")
        src = _entry(db, topic["id"], "S", body="[[NoSuchNote]]")
        assert get_backlinks(db, target["id"])["total"] == 0  # dangling

        # Point it at the target → backlink appears.
        update_event(db, src["id"], {"headline": "S", "era": "", "bodyMarkdown": f"[[{target['id']}|T]]", "noteType": "entry"})
        assert get_backlinks(db, target["id"])["total"] == 1

        # Rename the target: id-anchored link survives (backlink still resolves).
        update_event(db, target["id"], {"headline": "T renamed", "era": "", "bodyMarkdown": "renamed body", "noteType": "entry"})
        assert get_backlinks(db, target["id"])["total"] == 1

        # Edit the link away → resync drops it.
        update_event(db, src["id"], {"headline": "S", "era": "", "bodyMarkdown": "no links now", "noteType": "entry"})
        assert get_backlinks(db, target["id"])["total"] == 0
    finally:
        db.close()
        engine.dispose()


def test_deleted_source_drops_out_of_backlinks(tmp_path, monkeypatch):
    db, engine = _session(tmp_path, monkeypatch)
    try:
        topic = create_topic(db, "t1", None)
        target = _entry(db, topic["id"], "T")
        src = _entry(db, topic["id"], "S", body=f"[[{target['id']}|T]]")
        assert get_backlinks(db, target["id"])["total"] == 1
        delete_event(db, src["id"])  # soft delete → source no longer live
        assert get_backlinks(db, target["id"])["total"] == 0
    finally:
        db.close()
        engine.dispose()


def test_batch_event_previews(tmp_path, monkeypatch):
    db, engine = _session(tmp_path, monkeypatch)
    try:
        topic = create_topic(db, "t1", None)
        a = _entry(db, topic["id"], "A", body="alpha body")
        b = _entry(db, topic["id"], "B", body="beta body")
        previews = batch_event_previews(db, [a["id"], b["id"], 999999])  # unknown id ignored
        by_id = {p["id"]: p for p in previews}
        assert set(by_id) == {a["id"], b["id"]}
        assert by_id[a["id"]]["headline"] == "A"
        assert "alpha" in by_id[a["id"]]["preview"]
        assert batch_event_previews(db, []) == []
    finally:
        db.close()
        engine.dispose()


def test_backlinks_dedup_per_source(tmp_path, monkeypatch):
    db, engine = _session(tmp_path, monkeypatch)
    try:
        topic = create_topic(db, "t1", None)
        target = _entry(db, topic["id"], "Target")
        # One source referencing the target TWICE is ONE backlink (deduped per source), not
        # two rows — otherwise the panel emits duplicate Vue keys and inflates the count.
        _entry(
            db,
            topic["id"],
            "Src",
            body=f"see [[{target['id']}|Target]] and again [[{target['id']}|Target]]",
        )
        back = get_backlinks(db, target["id"])
        assert back["total"] == 1
        assert len(back["items"]) == 1
        assert back["items"][0]["headline"] == "Src"
    finally:
        db.close()
        engine.dispose()


def test_link_targets_ride_detail_payload(tmp_path, monkeypatch):
    db, engine = _session(tmp_path, monkeypatch)
    try:
        topic = create_topic(db, "t1", None)
        target = _entry(db, topic["id"], "Target")
        source = _entry(
            db, topic["id"], "Source", body=f"see [[{target['id']}|Target]] and [[999999|Ghost]]"
        )
        # Live id-anchored target → current headline; dead id (999999) → absent = dangling on FE.
        detail = get_event_detail(db, source["id"])
        assert detail["linkTargets"] == {str(target["id"]): "Target"}

        # Rename the target → the map carries the FRESH title although the source body is
        # untouched (the whole point of id-addressing; §6.1).
        update_event(db, target["id"], {"headline": "Renamed", "era": "", "bodyMarkdown": "b", "noteType": "entry"})
        assert get_event_detail(db, source["id"])["linkTargets"] == {str(target["id"]): "Renamed"}

        # A note with no wikilinks → empty map, never null.
        assert get_event_detail(db, target["id"])["linkTargets"] == {}
    finally:
        db.close()
        engine.dispose()


def test_parse_snapshot_embeds_picks_only_embed_cards():
    snap = {
        "_fmt": "x6-canvas-v1",
        "cells": [
            {"shape": "rect", "data": {"kind": "card", "text": "free card"}},  # not an embed
            {"shape": "embed-card", "data": {"kind": "embed", "noteId": 7, "headline": "Seven"}},
            {"shape": "embed-card", "data": {"kind": "embed", "noteId": "nope"}},  # non-numeric → skip
            {"shape": "edge"},
        ],
    }
    parsed = parse_snapshot_embeds(snap)
    assert [(p["noteId"], p["title"], p["position"]) for p in parsed] == [(7, "Seven", 1)]
    # Tolerates the bare shapes and non-snapshots.
    assert parse_snapshot_embeds(None) == []
    assert parse_snapshot_embeds({"cells": []}) == []
    assert parse_snapshot_embeds([{"shape": "embed-card", "data": {"kind": "embed", "noteId": 3}}])[0]["noteId"] == 3


def test_canvas_embed_writes_backlink(tmp_path, monkeypatch):
    db, engine = _session(tmp_path, monkeypatch)
    try:
        topic = create_topic(db, "t1", None)
        target = _entry(db, topic["id"], "Embedded Note")
        board = _canvas(db, topic["id"], "Board", [_embed_cell(target["id"], "Embedded Note", "some preview")])
        back = get_backlinks(db, target["id"])
        assert back["total"] == 1
        item = back["items"][0]
        assert item["sourceId"] == board["id"]
        # Distinguishable from a wikilink backlink so the panel can label it "被嵌入于画布".
        assert item["anchorType"] == "embed"
    finally:
        db.close()
        engine.dispose()


def test_canvas_embed_resync_drops_removed_card(tmp_path, monkeypatch):
    db, engine = _session(tmp_path, monkeypatch)
    try:
        topic = create_topic(db, "t1", None)
        target = _entry(db, topic["id"], "T")
        board = _canvas(db, topic["id"], "Board", [_embed_cell(target["id"], "T")])
        assert get_backlinks(db, target["id"])["total"] == 1
        # Remove the embed card → idempotent resync clears the embed row (mirrors wikilink resync).
        _resave_canvas(db, board["id"], "Board", [])
        assert get_backlinks(db, target["id"])["total"] == 0
        # An embed row never touches the source's wikilink rows and vice versa.
        _resave_canvas(db, board["id"], "Board", [_embed_cell(target["id"], "T"), _embed_cell(target["id"], "T")])
        # Same target embedded twice on one board = ONE relationship (deduped per source).
        assert get_backlinks(db, target["id"])["total"] == 1
        rows = (
            db.query(TimelineLink)
            .filter(TimelineLink.source_event_id == board["id"], TimelineLink.anchor_type == "embed")
            .all()
        )
        assert len(rows) == 1
    finally:
        db.close()
        engine.dispose()


def test_canvas_embed_dangling_and_tombstone(tmp_path, monkeypatch):
    db, engine = _session(tmp_path, monkeypatch)
    try:
        topic = create_topic(db, "t1", None)
        # Embed an id that does not exist → row stored with target_event_id NULL, canvas saves fine
        # (no crash), keeping the cached title as the dangling label.
        board = _canvas(db, topic["id"], "Board", [_embed_cell(999999, "Ghost")])
        rows = (
            db.query(TimelineLink)
            .filter(TimelineLink.source_event_id == board["id"], TimelineLink.anchor_type == "embed")
            .all()
        )
        assert len(rows) == 1 and rows[0].target_event_id is None and rows[0].target_title == "Ghost"

        # Live target → resolved; then soft-delete the target and re-save → becomes a tombstone
        # (target_event_id NULL), the same treatment as a dangling wikilink (§7.5).
        target = _entry(db, topic["id"], "Real")
        board2 = _canvas(db, topic["id"], "Board2", [_embed_cell(target["id"], "Real")])
        assert get_backlinks(db, target["id"])["total"] == 1
        delete_event(db, target["id"])
        _resave_canvas(db, board2["id"], "Board2", [_embed_cell(target["id"], "Real")])
        rows2 = (
            db.query(TimelineLink)
            .filter(TimelineLink.source_event_id == board2["id"], TimelineLink.anchor_type == "embed")
            .all()
        )
        assert len(rows2) == 1 and rows2[0].target_event_id is None
    finally:
        db.close()
        engine.dispose()


def test_canvas_indexed_by_embedded_headline(tmp_path, monkeypatch):
    db, engine = _session(tmp_path, monkeypatch)
    try:
        topic = create_topic(db, "t1", None)
        target = _entry(db, topic["id"], "Waterloo")
        board = _canvas(db, topic["id"], "Board", [_embed_cell(target["id"], "Waterloo", "the 1815 battle")])
        # The walker folds the embed card's cached headline+preview into the canvas search text,
        # so the board is findable by what it embeds — even though it holds no free-text card.
        event = db.query(TimelineEvent).filter(TimelineEvent.id == board["id"]).one()
        assert "Waterloo" in (event.search_text or "")
        assert "1815" in (event.search_text or "")
    finally:
        db.close()
        engine.dispose()
