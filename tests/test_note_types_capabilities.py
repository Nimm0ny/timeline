"""W1 data layer for note types (axis 2) + display-style views (axis 1).

Covers the pure capability derivation (FE/BE SSOT), its exposure through the
topic DTOs, display_style read/write, note_type + body_json round-trip, and the
idempotent ALTER migration that brings an existing SQLite DB up to schema.
See docs/note-types-and-views-design.md.
"""

from sqlalchemy import create_engine, inspect, text

from backend.app.services import legacy_migration as legacy_migration_module
from backend.app.services.timeline import (
    normalize_display_style,
    normalize_note_type,
    topic_capabilities,
    topic_capability_signals,
)


def test_topic_capabilities_pure_derivation():
    # Empty/new notebook: only its own style + the always-on list/table, so a
    # brand-new notebook can still render (chicken-and-egg, F-3).
    empty = topic_capability_signals([], event_count=0, has_dated=False, has_image=False)
    assert topic_capabilities("timeline", empty) == ["list", "table", "timeline"]
    assert topic_capabilities("table", empty) == ["list", "table"]

    # Dated events unlock timeline; any events unlock outline.
    dated = topic_capability_signals([], event_count=3, has_dated=True, has_image=False)
    caps = topic_capabilities("table", dated)
    assert {"timeline", "table", "list", "outline"} == set(caps)
    assert "board" not in caps and "gallery" not in caps

    # A select column unlocks board; an image unlocks gallery.
    rich = topic_capability_signals(
        [{"key": "type", "type": "select"}],
        event_count=2,
        has_dated=True,
        has_image=True,
    )
    assert {"timeline", "table", "list", "outline", "board", "gallery"} == set(topic_capabilities("timeline", rich))


def test_normalizers_guard_unknown_values():
    assert normalize_display_style("board") == "board"
    assert normalize_display_style("kanban") == "timeline"
    assert normalize_display_style(None) == "timeline"
    assert normalize_note_type("mindmap") == "mindmap"
    assert normalize_note_type("doc") == "entry"
    assert normalize_note_type("") == "entry"


def test_meta_exposes_display_style_and_capabilities(client, seeded_topic):
    body = client.get(f"/api/topics/{seeded_topic.id}/meta").json()
    assert body["displayStyle"] == "timeline"
    # Seeded topic: dated events, no columns, no images.
    assert set(body["capabilities"]) == {"timeline", "table", "list", "outline"}
    assert body["capabilitySignals"]["hasDated"] is True
    assert body["capabilitySignals"]["hasSelectColumn"] is False
    assert body["capabilitySignals"]["hasImage"] is False


def test_list_topics_carries_capabilities(client, seeded_topic):
    rows = client.get("/api/topics").json()
    row = next(item for item in rows if item["id"] == seeded_topic.id)
    assert row["displayStyle"] == "timeline"
    assert set(row["capabilities"]) == {"timeline", "table", "list", "outline"}


def test_create_topic_defaults_display_style_and_capabilities(client):
    body = client.post("/api/topics", json={"name": "mybook"}).json()
    assert body["displayStyle"] == "timeline"
    # New notebooks seed select/multiselect columns -> board unlocked; no events
    # yet, so timeline is present only as the notebook's own default style.
    assert set(body["capabilities"]) == {"timeline", "table", "list", "board"}


def test_update_display_style_persists_and_normalizes(client, seeded_topic):
    updated = client.put(f"/api/topics/{seeded_topic.id}/meta", json={"displayStyle": "table"}).json()
    assert updated["displayStyle"] == "table"
    # Persisted across a fresh read.
    assert client.get(f"/api/topics/{seeded_topic.id}/meta").json()["displayStyle"] == "table"
    # Unknown values fall back to the default rather than corrupting state.
    reset = client.put(f"/api/topics/{seeded_topic.id}/meta", json={"displayStyle": "kanban"}).json()
    assert reset["displayStyle"] == "timeline"


def test_event_round_trips_note_type_and_body_json(client, seeded_topic):
    tree = {"data": {"text": "Root"}, "children": [{"data": {"text": "Branch"}, "children": []}]}
    created = client.post(
        f"/api/topics/{seeded_topic.id}/events",
        json={
            "dateYear": 1850,
            "dateMonth": 6,
            "dateDay": 1,
            "headline": "Mind map note",
            "era": "Modern China",
            "noteType": "mindmap",
            "bodyJson": tree,
            "items": [{"tag": "note", "text": "placeholder"}],
        },
    ).json()
    assert created["noteType"] == "mindmap"
    assert created["bodyJson"] == tree

    detail = client.get(f"/api/events/{created['id']}").json()
    assert detail["noteType"] == "mindmap"
    assert detail["bodyJson"] == tree

    # Entry notes use markdown; any bodyJson sent with an entry is dropped.
    entry = client.post(
        f"/api/topics/{seeded_topic.id}/events",
        json={
            "dateYear": 1851,
            "dateMonth": 1,
            "dateDay": 1,
            "headline": "Plain entry",
            "era": "Modern China",
            "bodyMarkdown": "Hello world",
            "bodyJson": {"data": {"text": "ignored"}},
        },
    ).json()
    assert entry["noteType"] == "entry"
    assert entry["bodyJson"] is None


def test_event_schema_migration_adds_columns_idempotently(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy.db"
    test_engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    # Realistic pre-feature DB: already on the current schema minus the 3 new
    # columns (display_style / note_type / body_json), with one populated row.
    with test_engine.begin() as conn:
        conn.execute(text("CREATE TABLE topics (id INTEGER PRIMARY KEY, name TEXT, columns_json TEXT DEFAULT '[]')"))
        conn.execute(
            text(
                "CREATE TABLE timeline_events ("
                "id INTEGER PRIMARY KEY, topic_id INTEGER, year TEXT, sort_key REAL, date_key INTEGER, "
                "date_year INTEGER, date_month INTEGER, date_day INTEGER, headline TEXT, era TEXT, "
                "body_markdown TEXT DEFAULT '', extra_json TEXT DEFAULT '{}', "
                "attachments_json TEXT DEFAULT '[]', related_event_ids_json TEXT DEFAULT '[]', "
                "image_id INTEGER, created_at DATETIME, updated_at DATETIME, "
                "favorite BOOLEAN DEFAULT 0 NOT NULL, deleted_at DATETIME)"
            )
        )
        conn.execute(text("INSERT INTO topics (id, name) VALUES (1, 'history')"))
        conn.execute(
            text(
                "INSERT INTO timeline_events "
                "(id, topic_id, year, sort_key, date_key, date_year, date_month, date_day, headline, era, "
                "created_at, updated_at) "
                "VALUES (1, 1, '1840', 18400101, 18400101, 1840, 1, 1, 'Opium War', 'Modern China', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )

    monkeypatch.setattr(legacy_migration_module, "engine", test_engine)
    legacy_migration_module.ensure_timeline_event_schema()
    legacy_migration_module.ensure_timeline_event_schema()  # second run is a no-op

    inspector = inspect(test_engine)
    assert "display_style" in {column["name"] for column in inspector.get_columns("topics")}
    assert {"note_type", "body_json"}.issubset({column["name"] for column in inspector.get_columns("timeline_events")})

    # Existing rows backfill to defaults (zero-break migration).
    with test_engine.begin() as conn:
        assert conn.execute(text("SELECT display_style FROM topics WHERE id=1")).scalar() == "timeline"
        note_type, body_json = conn.execute(
            text("SELECT note_type, body_json FROM timeline_events WHERE id=1")
        ).one()
    assert note_type == "entry"
    assert body_json is None
    test_engine.dispose()
