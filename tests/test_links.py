"""W4 link system: [[wikilink]] parse/resolve/sync + backlinks + batch preview.

The link graph is keyed by note id, not title, so rename/move never breaks an edge;
backlinks are one indexed lookup on timeline_links(target_event_id), not a body scan.
See docs/notes-app-pivot-design.md §6.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.session import Base
from backend.app.services import legacy_migration as legacy_migration_module
from backend.app.services.timeline import (
    batch_event_previews,
    create_event,
    create_topic,
    delete_event,
    get_backlinks,
    get_event_detail,
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
