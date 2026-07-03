"""W1 data layer for note types (axis 2) + display-style views (axis 1).

Covers the pure capability derivation (FE/BE SSOT), its exposure through the
topic DTOs, display_style read/write, note_type + body_json round-trip, and the
idempotent ALTER migration that brings an existing SQLite DB up to schema.
See docs/note-types-and-views-design.md.
"""

from sqlalchemy import create_engine, inspect, text

from backend.app.models.entities import ImageAsset, TimelineEvent
from backend.app.services import legacy_migration as legacy_migration_module
from backend.app.services.timeline import (
    build_timeline_index,
    get_event_detail,
    normalize_display_style,
    normalize_group_by,
    normalize_note_type,
    normalize_sort_levels,
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


def test_sort_and_group_by_normalizers():
    # group_by dimension guarded to era/year/month.
    assert normalize_group_by("year") == "year"
    assert normalize_group_by("decade") == "era"
    assert normalize_group_by(None) == "era"
    # Sort levels mirror the front-end normalizer: legacy single object wraps,
    # a JSON string (as stored in sort_json) parses, garbage → default, dirs
    # coerce to ±1, duplicate fields dedupe (first wins), empty fields drop.
    assert normalize_sort_levels({"field": "time", "dir": -1}) == [{"field": "time", "dir": -1}]
    assert normalize_sort_levels('[{"field":"title","dir":-1}]') == [{"field": "title", "dir": -1}]
    assert normalize_sort_levels([]) == [{"field": "time", "dir": 1}]
    assert normalize_sort_levels("not json") == [{"field": "time", "dir": 1}]
    assert normalize_sort_levels(None) == [{"field": "time", "dir": 1}]
    assert normalize_sort_levels([{"field": "title", "dir": 1}, {"field": "title", "dir": -1}]) == [
        {"field": "title", "dir": 1}
    ]
    assert normalize_sort_levels([{"field": "", "dir": 1}, {"field": "pri", "dir": 0}]) == [{"field": "pri", "dir": 1}]


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


def test_update_sort_and_group_by_persist_and_normalize(client, seeded_topic):
    # A fresh notebook defaults to time-ascending / era grouping (today's behavior).
    meta = client.get(f"/api/topics/{seeded_topic.id}/meta").json()
    assert meta["sort"] == [{"field": "time", "dir": 1}]
    assert meta["groupBy"] == "era"

    # A multi-level sort + a grouping dimension persist across a fresh read.
    updated = client.put(
        f"/api/topics/{seeded_topic.id}/meta",
        json={"sort": [{"field": "title", "dir": -1}, {"field": "time", "dir": 1}], "groupBy": "year"},
    ).json()
    assert updated["sort"] == [{"field": "title", "dir": -1}, {"field": "time", "dir": 1}]
    assert updated["groupBy"] == "year"
    reread = client.get(f"/api/topics/{seeded_topic.id}/meta").json()
    assert reread["sort"] == [{"field": "title", "dir": -1}, {"field": "time", "dir": 1}]
    assert reread["groupBy"] == "year"

    # Unknown dimension → era; a malformed sort (dir out of ±1, duplicate field)
    # normalizes rather than corrupting state.
    reset = client.put(
        f"/api/topics/{seeded_topic.id}/meta",
        json={"groupBy": "decade", "sort": [{"field": "time", "dir": 5}, {"field": "time", "dir": -1}]},
    ).json()
    assert reset["groupBy"] == "era"
    assert reset["sort"] == [{"field": "time", "dir": 1}]


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


def test_mindmap_allows_empty_items_and_era(client, seeded_topic):
    """A mindmap's content is its tree (body_json); it needs neither markdown items
    nor an era nor a date. Entries still require body + date."""
    tree = {"data": {"text": "中心主题"}, "children": []}
    created = client.post(
        f"/api/topics/{seeded_topic.id}/events",
        json={
            "headline": "导图笔记",
            "noteType": "mindmap",
            "bodyJson": tree,
            # no "items", no "era", no date
        },
    )
    assert created.status_code == 200
    body = created.json()
    assert body["noteType"] == "mindmap"
    assert body["bodyJson"] == tree
    assert body["era"] == ""
    assert body["hasDate"] is False
    assert body["dateKey"] is None
    assert body["displayLabel"] == "未定时间"

    # An entry with no body still fails — the relaxation is mindmap-only.
    entry = client.post(
        f"/api/topics/{seeded_topic.id}/events",
        json={"dateYear": 2026, "dateMonth": 6, "dateDay": 30, "headline": "空条目", "era": "Modern China"},
    )
    assert entry.status_code == 400


def test_mindmap_body_json_size_guard(client, seeded_topic):
    """An oversized structured body is rejected (413) so one note can't store an
    unbounded blob."""
    huge = {"data": {"text": "x" * (5_000_001)}, "children": []}
    res = client.post(
        f"/api/topics/{seeded_topic.id}/events",
        json={"dateYear": 2026, "dateMonth": 6, "dateDay": 30, "headline": "巨树", "noteType": "mindmap", "bodyJson": huge},
    )
    assert res.status_code == 413


def test_mindmap_tree_text_flows_into_index_preview_and_search(client, seeded_topic):
    tree = {
        "data": {"text": "<p>中心主题</p>"},
        "children": [
            {"data": {"text": "<p>分支甲</p>", "note": "<p>细节点</p>"}, "children": []},
        ],
    }
    created = client.post(
        f"/api/topics/{seeded_topic.id}/events",
        json={"headline": "导图检索", "noteType": "mindmap", "bodyJson": tree},
    )
    assert created.status_code == 200
    event_id = created.json()["id"]

    indexed = client.get("/api/index").json()["events"]
    row = next(item for item in indexed if item["id"] == event_id)
    assert row["preview"] == "中心主题 分支甲 细节点"
    assert "分支甲" in row["searchText"]
    assert row["dateKey"] is None

    matched = client.get("/api/search", params={"q": "细节点"})
    assert matched.status_code == 200
    result = next(item for item in matched.json() if item["id"] == event_id)
    assert result["isoDate"] is None


def test_index_events_carry_primary_image_urls_for_gallery(db_session, seeded_topic):
    """The gallery view (W3) reads the index DTO, so an event's primary image must
    ride it (thumb preferred for the grid). Imageless events keep null image fields."""
    image = ImageAsset(filename="abc.webp", thumb_filename="abc.thumb.webp", mime_type="image/webp")
    db_session.add(image)
    db_session.flush()

    events = db_session.query(TimelineEvent).order_by(TimelineEvent.date_key.asc()).all()
    events[0].image_id = image.id
    db_session.commit()

    by_id = {event["id"]: event for event in build_timeline_index(db_session)["events"]}

    with_image = by_id[events[0].id]
    assert with_image["image"] == "abc.webp"
    assert with_image["imageUrl"] == "/images/abc.webp"
    assert with_image["thumbUrl"] == "/images/abc.thumb.webp"

    without_image = by_id[events[1].id]
    assert without_image["image"] is None
    assert without_image["imageUrl"] is None
    assert without_image["thumbUrl"] is None

    # The detail DTO must also carry thumbUrl so an edit round-trip (detail →
    # index event) preserves the real thumb instead of the full-res image.
    detail = get_event_detail(db_session, events[0].id)
    assert detail["thumbUrl"] == "/images/abc.thumb.webp"
    assert detail["imageUrl"] == "/images/abc.webp"


def test_index_event_thumb_falls_back_to_full_image_when_no_thumb(db_session, seeded_topic):
    """No thumb generated (e.g. gif/svg keep their original) → thumbUrl falls back
    to the full image URL so a gallery card still has something to render."""
    image = ImageAsset(filename="pic.gif", thumb_filename=None, mime_type="image/gif")
    db_session.add(image)
    db_session.flush()
    event = db_session.query(TimelineEvent).order_by(TimelineEvent.date_key.asc()).first()
    event.image_id = image.id
    db_session.commit()

    entry = next(item for item in build_timeline_index(db_session)["events"] if item["id"] == event.id)
    assert entry["imageUrl"] == "/images/pic.gif"
    assert entry["thumbUrl"] == "/images/pic.gif"


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
    topic_cols = {column["name"] for column in inspector.get_columns("topics")}
    assert {"display_style", "sort_json", "group_by"}.issubset(topic_cols)
    assert {"note_type", "body_json"}.issubset({column["name"] for column in inspector.get_columns("timeline_events")})

    # Existing rows backfill to defaults (zero-break migration).
    with test_engine.begin() as conn:
        display_style, sort_json, group_by = conn.execute(
            text("SELECT display_style, sort_json, group_by FROM topics WHERE id=1")
        ).one()
        note_type, body_json = conn.execute(
            text("SELECT note_type, body_json FROM timeline_events WHERE id=1")
        ).one()
    assert (display_style, sort_json, group_by) == ("timeline", "[]", "era")
    assert note_type == "entry"
    assert body_json is None
    test_engine.dispose()
