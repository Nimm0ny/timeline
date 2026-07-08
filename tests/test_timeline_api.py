import io

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from backend.app.api.config import router as config_router
from backend.app.api.media import router as media_router
from backend.app import main as main_module
from backend.app.db.session import Base
from backend.app.db.session import get_db
from backend.app.models.entities import Bookshelf, NoteItem, Note, Topic, TopicEraStat, TopicStat
from backend.app.services.date_utils import build_display_label, make_date_key
from backend.app.services import legacy_migration as legacy_migration_module, timeline as timeline_service
from backend.app.services.timeline import ensure_topic_bookshelf_assignments
from backend.app.services.timeline import (
    backfill_note_text_fields,
    export_topic_data,
    import_topic_data,
    rebuild_topic_read_models,
)


def make_media_client(db_session):
    app = FastAPI()
    app.include_router(config_router)
    app.include_router(media_router)
    app.add_api_route("/images/{filename:path}", main_module.image_response, methods=["GET"])

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def make_image_bytes(fmt="JPEG", size=(1200, 900), color=(120, 80, 220)) -> bytes:
    image = Image.effect_noise(size, 80).convert("RGB")
    overlay = Image.new("RGB", size, color)
    image = Image.blend(image, overlay, 0.22)
    buffer = io.BytesIO()
    save_kwargs = {"quality": 95} if fmt.upper() in {"JPEG", "WEBP"} else {}
    image.save(buffer, format=fmt, **save_kwargs)
    return buffer.getvalue()


def test_topic_meta_range_and_summary(client, seeded_topic):
    meta = client.get(f"/api/topics/{seeded_topic.id}/meta")
    assert meta.status_code == 200
    body = meta.json()
    assert body["bookshelfName"] == "default"
    assert body["bookshelfTitle"] == "编年"
    assert body["columns"] == []
    assert body["minDateKey"] == 18400101
    assert body["maxDateKey"] == 18410215
    assert body["eventCount"] == 4

    summary = client.get(f"/api/topics/{seeded_topic.id}/summary", params={"groupBy": "month"})
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["items"][0]["displayLabel"] == "1840-01"
    assert payload["items"][0]["eventCount"] == 2


def test_bookshelf_contracts_cover_list_create_update_delete_and_topic_assignment(client, seeded_topic):
    shelves = client.get("/api/bookshelves")
    assert shelves.status_code == 200
    default_shelf = next(item for item in shelves.json() if item["name"] == "default")
    assert default_shelf["title"] == "编年"
    assert default_shelf["topicCount"] == 1
    assert default_shelf["eventCount"] == 4
    tree = client.get("/api/bookshelves/tree")
    assert tree.status_code == 200
    default_tree = next(item for item in tree.json() if item["name"] == "default")
    assert default_tree["topicCount"] == 1
    assert default_tree["topics"][0]["topic"]["id"] == seeded_topic.id
    assert default_tree["topics"][0]["eras"][0]["era"] == "Modern China"
    assert default_tree["topics"][0]["eras"][0]["count"] == 4

    reserved = client.post("/api/bookshelves", json={"name": "qstheory", "title": "错误标题"})
    assert reserved.status_code == 400

    created_shelf = client.post("/api/bookshelves", json={"name": "qishi", "title": "求是"}).json()
    assert created_shelf["name"] == "qishi"
    assert created_shelf["title"] == "求是"

    moved = client.put(
        f"/api/topics/{seeded_topic.id}/meta",
        json={"bookshelfId": created_shelf["id"]},
    )
    assert moved.status_code == 200
    assert moved.json()["bookshelfId"] == created_shelf["id"]
    assert moved.json()["bookshelfName"] == "qishi"
    assert moved.json()["bookshelfTitle"] == "求是"

    created_topic = client.post(
        "/api/topics",
        json={"name": "qishi_theory", "bookshelfId": created_shelf["id"]},
    )
    assert created_topic.status_code == 200
    assert created_topic.json()["bookshelfId"] == created_shelf["id"]

    updated_shelf = client.put(
        f"/api/bookshelves/{created_shelf['id']}",
        json={"title": "求是文库"},
    )
    assert updated_shelf.status_code == 200
    assert updated_shelf.json()["title"] == "求是文库"

    immutable_name = client.put(
        f"/api/bookshelves/{created_shelf['id']}",
        json={"name": "renamed-shelf"},
    )
    assert immutable_name.status_code == 400

    non_empty_delete = client.delete(f"/api/bookshelves/{created_shelf['id']}")
    assert non_empty_delete.status_code == 409

    invalid_clear = client.put(f"/api/topics/{seeded_topic.id}/meta", json={"bookshelfId": None})
    assert invalid_clear.status_code == 400

    qstheory_topic = client.post("/api/topics", json={"name": "求是网-新增专题"})
    assert qstheory_topic.status_code == 200
    assert qstheory_topic.json()["bookshelfName"] == "qstheory"
    assert qstheory_topic.json()["bookshelfTitle"] == "求是"

    empty_shelf = client.post("/api/bookshelves", json={"name": "archive", "title": "档案"}).json()
    removed = client.delete(f"/api/bookshelves/{empty_shelf['id']}")
    assert removed.status_code == 200
    assert removed.json() == {"ok": True}


def test_index_and_event_detail_contract(client, seeded_topic):
    long_body = "Short preview. " + ("filler " * 40) + "deep-search-token"
    created = client.post(
        f"/api/topics/{seeded_topic.id}/events",
        json={
            "dateYear": 1842,
            "dateMonth": 5,
            "dateDay": 1,
            "headline": "Searchable Index Event",
            "era": "Modern China",
            "bodyMarkdown": long_body,
            "attachments": [
                {"id": None, "name": "rare-attachment-name.pdf", "filename": "rare-attachment-name.pdf", "mimeType": "application/pdf"}
            ],
            "items": [],
            "image": None,
        },
    )
    assert created.status_code == 200

    index = client.get("/api/index")
    assert index.status_code == 200
    payload = index.json()
    assert payload["topics"][0]["id"] == seeded_topic.id
    assert payload["topics"][0]["eventCount"] == 5

    event = payload["events"][0]
    assert event["topicId"] == seeded_topic.id
    assert event["headline"] == "Opium War Begins"
    assert event["preview"] == "Conflict begins."
    assert event["attachmentCount"] == 0
    assert "bodyMarkdown" not in event
    assert "attachments" not in event

    indexed_created = next(item for item in payload["events"] if item["id"] == created.json()["id"])
    assert indexed_created["attachmentCount"] == 1
    assert "deep-search-token" in indexed_created["searchText"]
    assert "rare-attachment-name.pdf" in indexed_created["searchText"]
    assert "deep-search-token" not in indexed_created["preview"]
    assert "bodyMarkdown" not in indexed_created
    assert "attachments" not in indexed_created

    detail = client.get(f"/api/events/{event['id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["id"] == event["id"]
    assert body["topicId"] == seeded_topic.id
    assert body["bodyMarkdown"] == "Conflict begins."
    assert body["attachments"] == []


def test_search_endpoint_matches_and_syncs_event_writes(client, seeded_topic):
    meta = client.put(
        f"/api/topics/{seeded_topic.id}/meta",
        json={
            "columns": [
                {
                    "key": "category",
                    "label": "Category",
                    "type": "select",
                    "width": 120,
                    "order": 0,
                    "visible": True,
                    "options": [{"id": "policy_option", "label": "Policy Label", "color": ""}],
                }
            ]
        },
    )
    assert meta.status_code == 200
    payload = {
        "dateYear": 1842,
        "dateMonth": 6,
        "dateDay": 8,
        "headline": "Command Palette Treaty",
        "era": "Modern China",
        "bodyMarkdown": "A searchable body contains uniqueneedle text.",
        "extra": {"category": "policy_option"},
        "items": [],
        "image": None,
    }
    created = client.post(f"/api/topics/{seeded_topic.id}/events", json=payload)
    assert created.status_code == 200
    note_id = created.json()["id"]

    matched = client.get("/api/search", params={"q": "uniqueneedle", "limit": 5})
    assert matched.status_code == 200
    rows = matched.json()
    assert rows[0]["id"] == note_id
    assert rows[0]["topicId"] == seeded_topic.id
    assert rows[0]["headline"] == "Command Palette Treaty"
    assert rows[0]["isoDate"] == "1842-06-08"
    assert "snippet" in rows[0]
    assert "rank" in rows[0]

    extra_match = client.get("/api/search", params={"q": "Policy Label"})
    assert extra_match.status_code == 200
    assert any(row["id"] == note_id for row in extra_match.json())

    relabeled = client.put(
        f"/api/topics/{seeded_topic.id}/meta",
        json={
            "columns": [
                {
                    "key": "category",
                    "label": "Category",
                    "type": "select",
                    "width": 120,
                    "order": 0,
                    "visible": True,
                    "options": [{"id": "policy_option", "label": "Policy Renamed", "color": ""}],
                }
            ]
        },
    )
    assert relabeled.status_code == 200
    assert all(row["id"] != note_id for row in client.get("/api/search", params={"q": "Policy Label"}).json())
    relabeled_match = client.get("/api/search", params={"q": "Policy Renamed"})
    assert relabeled_match.status_code == 200
    assert any(row["id"] == note_id for row in relabeled_match.json())
    listed = client.get(f"/api/topics/{seeded_topic.id}/events", params={"limit": 200})
    assert listed.status_code == 200
    listed_event = next(row for row in listed.json()["items"] if row["id"] == note_id)
    assert "Policy Renamed" in listed_event["searchText"]

    updated = client.put(
        f"/api/events/{note_id}",
        json={**payload, "headline": "Updated Search Event", "bodyMarkdown": "replacementneedle is now the indexed body."},
    )
    assert updated.status_code == 200
    assert all(row["id"] != note_id for row in client.get("/api/search", params={"q": "uniqueneedle"}).json())
    assert any(row["id"] == note_id for row in client.get("/api/search", params={"q": "replacementneedle"}).json())

    deleted = client.delete(f"/api/events/{note_id}")
    assert deleted.status_code == 200
    assert all(row["id"] != note_id for row in client.get("/api/search", params={"q": "replacementneedle"}).json())


def test_structured_event_creation_and_range_fetch(client, seeded_topic):
    response = client.post(
        f"/api/topics/{seeded_topic.id}/events",
        json={
            "dateYear": 1842,
            "dateMonth": 3,
            "dateDay": 6,
            "headline": "Structured Event",
            "era": "Modern China",
            "items": [{"tag": "science", "text": "Structured payload path."}],
            "image": None,
        },
    )
    assert response.status_code == 200
    created = response.json()
    assert created["dateKey"] == 18420306
    assert created["headline"] == "Structured Event"

    ranged = client.get(
        f"/api/topics/{seeded_topic.id}/events",
        params={"from": "1842-03-01", "to": "1842-03-31"},
    )
    assert ranged.status_code == 200
    items = ranged.json()["items"]
    assert len(items) == 1
    assert items[0]["headline"] == "Structured Event"


def test_media_upload_transcodes_thumbnails_dedupes_and_serves_immutable_cache(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(timeline_service, "IMAGES_DIR", tmp_path)
    monkeypatch.setattr(main_module, "IMAGES_DIR", tmp_path)
    content = make_image_bytes("JPEG")

    with make_media_client(db_session) as client:
        initial_config = client.get("/api/config").json()
        assert initial_config["media"]["compress"] is True
        # Desktop layout knobs ship defaults so a fresh device paints the right
        # column order before any user save (docs/layout-swap-design.md §3/§7).
        assert initial_config["navPosition"] == "left"
        assert initial_config["detailPosition"] == "edge"
        swapped = client.put("/api/config", json={"detailPosition": "center"})
        assert swapped.status_code == 200
        assert swapped.json()["detailPosition"] == "center"
        client.put("/api/config", json={"detailPosition": "edge"})
        config = client.put(
            "/api/config",
            json={"media": {"compress": True, "keepOriginal": False, "quality": 72, "maxEdge": 800, "thumbEdge": 200}},
        )
        assert config.status_code == 200
        assert config.json()["media"]["quality"] == 72

        uploaded = client.post(
            "/api/media/upload",
            files={"file": ("photo.jpg", content, "image/jpeg")},
        )
        assert uploaded.status_code == 200
        body = uploaded.json()
        content_hash = body["filename"].split(".", 1)[0]
        assert body["filename"] == f"{content_hash}.webp"
        assert body["thumbFilename"] == f"{content_hash}.thumb.webp"
        assert body["originalFilename"] is None
        assert body["mimeType"] == "image/webp"
        assert body["url"] == f"/images/{body['filename']}"
        assert body["thumbUrl"] == f"/images/{body['thumbFilename']}"
        assert body["imageUrl"] == body["url"]
        assert body["width"] <= 800
        assert body["height"] <= 800

        with Image.open(tmp_path / body["filename"]) as work_image:
            assert work_image.format == "WEBP"
            assert max(work_image.size) <= 800
        with Image.open(tmp_path / body["thumbFilename"]) as thumb_image:
            assert thumb_image.format == "WEBP"
            assert max(thumb_image.size) <= 200

        files_before = {path.name for path in tmp_path.iterdir()}
        repeated = client.post(
            "/api/media/upload",
            files={"file": ("photo-copy.jpg", content, "image/jpeg")},
        )
        assert repeated.status_code == 200
        assert repeated.json()["id"] == body["id"]
        assert {path.name for path in tmp_path.iterdir()} == files_before

        media = client.get(body["url"])
        assert media.status_code == 200
        assert media.headers["cache-control"] == "public, max-age=31536000, immutable"
        assert media.headers["etag"] == f'"{content_hash}"'


def test_media_upload_honors_keep_original_and_compress_off(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(timeline_service, "IMAGES_DIR", tmp_path)
    monkeypatch.setattr(main_module, "IMAGES_DIR", tmp_path)

    with make_media_client(db_session) as client:
        keep_original = client.put(
            "/api/config",
            json={"media": {"compress": True, "keepOriginal": True, "quality": 80, "maxEdge": 700, "thumbEdge": 180}},
        )
        assert keep_original.status_code == 200
        png_content = make_image_bytes("PNG", color=(40, 150, 120))
        uploaded_png = client.post(
            "/api/media/upload",
            files={"file": ("diagram.png", png_content, "image/png")},
        )
        assert uploaded_png.status_code == 200
        png_body = uploaded_png.json()
        assert png_body["filename"].endswith(".webp")
        assert png_body["originalFilename"].endswith(".orig.png")
        assert (tmp_path / png_body["originalFilename"]).read_bytes() == png_content

        no_compress = client.put("/api/config", json={"media": {"compress": False, "keepOriginal": False, "quality": 66}})
        assert no_compress.status_code == 200
        assert no_compress.json()["media"]["quality"] == 66
        jpeg_content = make_image_bytes("JPEG", color=(180, 70, 70))
        uploaded_jpeg = client.post(
            "/api/media/upload",
            files={"file": ("scan.jpg", jpeg_content, "image/jpeg")},
        )
        assert uploaded_jpeg.status_code == 200
        jpeg_body = uploaded_jpeg.json()
        assert jpeg_body["filename"].endswith(".jpg")
        assert jpeg_body["thumbFilename"].endswith(".thumb.webp")
        assert jpeg_body["originalFilename"] is None
        assert (tmp_path / jpeg_body["filename"]).read_bytes() == jpeg_content


def test_invalid_compress_off_image_leaves_no_orphan_file(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(timeline_service, "IMAGES_DIR", tmp_path)
    monkeypatch.setattr(main_module, "IMAGES_DIR", tmp_path)

    with make_media_client(db_session) as client:
        no_compress = client.put("/api/config", json={"media": {"compress": False}})
        assert no_compress.status_code == 200
        response = client.post(
            "/api/media/upload",
            files={"file": ("broken.jpg", b"not a real jpeg", "image/jpeg")},
        )
        assert response.status_code == 400
        assert list(tmp_path.iterdir()) == []


PROPERTY_COLUMNS = [
    {
        "key": "type",
        "label": "类型",
        "type": "select",
        "width": 96,
        "order": 0,
        "visible": True,
        "options": [
            {"id": "battle", "label": "战役", "color": "#c05a52"},
            {"id": "treaty", "label": "条约", "color": "#5a7fc0"},
        ],
    },
    {
        "key": "tags",
        "label": "标签",
        "type": "multiselect",
        "width": 150,
        "order": 1,
        "visible": True,
        "options": [
            {"id": "important", "label": "重要", "color": ""},
            {"id": "archive", "label": "档案", "color": ""},
        ],
    },
    {"key": "place", "label": "地点", "type": "text", "width": 88, "order": 2, "visible": True},
    {"key": "source", "label": "来源", "type": "text", "width": 112, "order": 3, "visible": False},
]


def test_event_contract_persists_markdown_properties_attachments_and_related_events(client, seeded_topic, db_session):
    meta = client.put(
        f"/api/topics/{seeded_topic.id}/meta",
        json={"title": "History", "subtitle": "Daily history", "columns": PROPERTY_COLUMNS},
    )
    assert meta.status_code == 200
    saved_columns = {column["key"]: column for column in meta.json()["columns"]}
    assert saved_columns["type"]["type"] == "select"
    assert saved_columns["tags"]["type"] == "multiselect"
    assert [option["id"] for option in saved_columns["tags"]["options"]] == ["important", "archive"]

    existing = client.get(f"/api/topics/{seeded_topic.id}/events")
    assert existing.status_code == 200
    related_id = existing.json()["items"][0]["id"]
    assert "bodyMarkdown" not in existing.json()["items"][0]
    assert client.get(f"/api/events/{related_id}").json()["bodyMarkdown"] == "Conflict begins."

    response = client.post(
        f"/api/topics/{seeded_topic.id}/events",
        json={
            "dateYear": 1842,
            "dateMonth": 4,
            "dateDay": 8,
            "headline": "Markdown Contract",
            "era": "Modern China",
            "bodyMarkdown": "## Notes\n\nStructured markdown body.",
            # type: single valid id; tags: dedup + drop unknown id; place/source kept; ignored dropped
            "extra": {
                "type": "battle",
                "tags": ["important", "archive", "important", "ghost"],
                "place": "广州",
                "source": "档案馆",
                "ignored": "drop me",
            },
            "attachments": [
                {"id": None, "name": "archive-note.md", "filename": "archive-note.md", "mimeType": "text/markdown"}
            ],
            "relatedEventIds": [related_id],
            "favorite": True,
            "items": [],
            "image": None,
        },
    )
    assert response.status_code == 200
    created = response.json()
    assert created["bodyMarkdown"] == "## Notes\n\nStructured markdown body."
    assert "tags" not in created  # tags are a property now, no top-level field
    assert created["extra"] == {
        "type": "battle",
        "tags": ["important", "archive"],
        "place": "广州",
        "source": "档案馆",
    }
    assert created["attachments"][0]["url"] == "/images/archive-note.md"
    assert created["relatedEventIds"] == [related_id]
    assert created["relatedEvents"][0]["id"] == related_id
    assert created["createdAt"]
    assert created["updatedAt"]
    assert created["favorite"] is True
    assert created["favoriteAt"]
    assert created["deletedAt"] is None
    # Body is the canonical store; items derive from markdown with a neutral tag.
    assert created["items"][0]["tag"] == "note"

    updated = client.put(
        f"/api/events/{created['id']}",
        json={
            "dateYear": 1842,
            "dateMonth": 4,
            "dateDay": 9,
            "headline": "Markdown Contract Updated",
            "era": "Modern China",
            "bodyMarkdown": "Updated body",
            # invalid select id falls back to ""; unknown property key dropped
            "extra": {"type": "ghost", "tags": ["archive"], "place": "南京", "source": "条约文本", "unknown": "drop"},
            "attachments": [],
            "relatedEventIds": [related_id],
            "items": [],
            "image": None,
        },
    )
    assert updated.status_code == 200
    payload = updated.json()
    assert payload["headline"] == "Markdown Contract Updated"
    assert payload["bodyMarkdown"] == "Updated body"
    assert payload["extra"] == {"type": "", "tags": ["archive"], "place": "南京", "source": "条约文本"}
    assert payload["favorite"] is True
    assert payload["favoriteAt"] == created["favoriteAt"]

    exported, _ = export_topic_data(db_session, seeded_topic.id)
    assert exported["columns"][0]["key"] == "type"
    exported_event = next(item for item in exported["events"] if item["id"] == created["id"])
    assert exported_event["bodyMarkdown"] == "Updated body"
    assert exported_event["extra"] == {"type": "", "tags": ["archive"], "place": "南京", "source": "条约文本"}
    assert exported_event["relatedEvents"][0]["id"] == related_id

    # Remove the `source` property; its value must survive as an orphan soft-keep.
    removed_column = client.put(
        f"/api/topics/{seeded_topic.id}/meta",
        json={
            "title": "History",
            "subtitle": "Daily history",
            "columns": [column for column in PROPERTY_COLUMNS if column["key"] != "source"],
        },
    )
    assert removed_column.status_code == 200

    preserved = client.put(
        f"/api/events/{created['id']}",
        json={
            "dateYear": 1842,
            "dateMonth": 4,
            "dateDay": 10,
            "headline": "Markdown Contract Preserved",
            "era": "Modern China",
            "bodyMarkdown": "Preserve orphan extra",
            "extra": {"type": "treaty", "tags": ["important"], "place": "上海"},
            "attachments": [],
            "relatedEventIds": [related_id],
            "items": [],
            "image": None,
        },
    )
    assert preserved.status_code == 200
    assert preserved.json()["extra"] == {
        "type": "treaty",
        "tags": ["important"],
        "place": "上海",
        "source": "条约文本",
    }


def test_event_state_contract_supports_favorite_soft_delete_restore_and_permanent_delete(client, seeded_topic):
    events = client.get(f"/api/topics/{seeded_topic.id}/events").json()["items"]
    note_id = events[0]["id"]

    favorite = client.put(f"/api/events/{note_id}", json={"favorite": True})
    assert favorite.status_code == 200
    assert favorite.json()["favorite"] is True
    assert favorite.json()["favoriteAt"]
    assert favorite.json()["deletedAt"] is None

    deleted = client.delete(f"/api/events/{note_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deletedAt"]
    assert next(item for item in client.get("/api/topics").json() if item["id"] == seeded_topic.id)["eventCount"] == 3
    assert next(item for item in client.get("/api/bookshelves").json() if item["name"] == "default")["eventCount"] == 3

    after_delete = client.get(f"/api/topics/{seeded_topic.id}/events").json()["items"]
    deleted_event = next(item for item in after_delete if item["id"] == note_id)
    assert deleted_event["deletedAt"]

    blocked_favorite = client.put(f"/api/events/{note_id}", json={"favorite": False})
    assert blocked_favorite.status_code == 409

    blocked_edit = client.put(
        f"/api/events/{note_id}",
        json={
            "dateYear": 1840,
            "dateMonth": 1,
            "dateDay": 1,
            "headline": "Should Not Edit",
            "era": "Modern China",
            "bodyMarkdown": "Blocked",
            "tags": ["blocked"],
            "items": [{"tag": "blocked", "text": "Blocked"}],
            "image": None,
        },
    )
    assert blocked_edit.status_code == 409

    restored = client.put(f"/api/events/{note_id}", json={"deletedAt": None})
    assert restored.status_code == 200
    assert restored.json()["deletedAt"] is None
    assert next(item for item in client.get("/api/topics").json() if item["id"] == seeded_topic.id)["eventCount"] == 4

    unfavorite = client.put(f"/api/events/{note_id}", json={"favorite": False})
    assert unfavorite.status_code == 200
    assert unfavorite.json()["favorite"] is False
    assert unfavorite.json()["favoriteAt"] is None

    permanent = client.delete(f"/api/events/{note_id}", params={"permanent": "true"})
    assert permanent.status_code == 200
    assert next(item for item in client.get("/api/topics").json() if item["id"] == seeded_topic.id)["eventCount"] == 3

    after_permanent = client.get(f"/api/topics/{seeded_topic.id}/events").json()["items"]
    assert note_id not in [item["id"] for item in after_permanent]


def test_topic_era_stats_merges_normalized_eras(db_session):
    # Regression: rebuild grouped by RAW era but stored the NORMALIZED era, so a raw
    # "" (e.g. a mindmap) and a typed "未分组" collided on the (topic_id, era) primary
    # key and raised IntegrityError — which, because every write rebuilds, would
    # write-lock the whole notebook. They must merge into one row instead.
    shelf = Bookshelf(name="default", title="编年")
    db_session.add(shelf)
    db_session.flush()
    topic = Topic(name="mixed", title="Mixed", bookshelf_id=shelf.id)
    db_session.add(topic)
    db_session.flush()
    db_session.add(Note(topic_id=topic.id, year="a", sort_key=1.0, date_key=1, era=""))
    db_session.add(Note(topic_id=topic.id, year="b", sort_key=2.0, date_key=2, era="未分组"))
    db_session.flush()

    rebuild_topic_read_models(db_session, [topic.id])  # must not raise IntegrityError
    db_session.flush()

    rows = db_session.query(TopicEraStat).filter(TopicEraStat.topic_id == topic.id).all()
    assert len(rows) == 1
    assert rows[0].era == "未分组"
    assert rows[0].live_event_count == 2

    # Changing one event's era splits the counts back out.
    event = (
        db_session.query(Note)
        .filter(Note.topic_id == topic.id, Note.era == "未分组")
        .first()
    )
    event.era = "清朝"
    db_session.flush()
    rebuild_topic_read_models(db_session, [topic.id])
    db_session.flush()
    counts = {
        row.era: row.live_event_count
        for row in db_session.query(TopicEraStat).filter(TopicEraStat.topic_id == topic.id).all()
    }
    assert counts == {"未分组": 1, "清朝": 1}


def test_topic_stat_favorite_count_tracks_soft_delete(client, seeded_topic, db_session):
    events = client.get(f"/api/topics/{seeded_topic.id}/events").json()["items"]
    note_id = events[0]["id"]

    client.put(f"/api/events/{note_id}", json={"favorite": True})
    stat = db_session.get(TopicStat, seeded_topic.id)
    db_session.refresh(stat)
    assert stat.live_event_count == 4
    assert stat.favorite_count == 1

    # Soft-deleting the favorited event drops live + favorite and bumps deleted.
    client.delete(f"/api/events/{note_id}")
    db_session.refresh(stat)
    assert stat.live_event_count == 3
    assert stat.deleted_event_count == 1
    assert stat.favorite_count == 0

    # Restore brings the (still-favorited) event back into the live/favorite counts.
    client.put(f"/api/events/{note_id}", json={"deletedAt": None})
    db_session.refresh(stat)
    assert stat.live_event_count == 4
    assert stat.deleted_event_count == 0
    assert stat.favorite_count == 1


def test_negative_year_range_fetch(client, seeded_topic):
    response = client.post(
        f"/api/topics/{seeded_topic.id}/events",
        json={
            "dateYear": -1,
            "dateMonth": 1,
            "dateDay": 6,
            "headline": "BCE Event",
            "era": "Ancient History",
            "items": [{"tag": "politics", "text": "Negative year range path."}],
            "image": None,
        },
    )
    assert response.status_code == 200

    ranged = client.get(
        f"/api/topics/{seeded_topic.id}/events",
        params={"from": "-0001-01-01", "to": "-0001-01-31"},
    )
    assert ranged.status_code == 200
    items = ranged.json()["items"]
    assert len(items) == 1
    assert items[0]["headline"] == "BCE Event"

    summary = client.get(f"/api/topics/{seeded_topic.id}/summary", params={"groupBy": "month"})
    assert summary.status_code == 200
    assert summary.json()["items"][0]["displayLabel"] == "-0001-01"


def test_topic_events_default_to_lightweight_pagination_and_keep_undated_tail(client, db_session, seeded_topic):
    undated_ids = []
    for offset in range(97):
        month = offset // 28 + 1
        day = offset % 28 + 1
        date_key = make_date_key(1842, month, day)
        headline = f"Paged Event {offset + 1}"
        event = Note(
            topic_id=seeded_topic.id,
            year=build_display_label(1842, month, day, headline),
            sort_key=float(date_key),
            date_key=date_key,
            date_year=1842,
            date_month=month,
            date_day=day,
            headline=headline,
            era="Modern China",
            body_markdown=f"Body {offset + 1}",
        )
        db_session.add(event)
    for offset in range(2):
        event = Note(
            topic_id=seeded_topic.id,
            year=f"Undated {offset + 1}",
            sort_key=0.0,
            date_key=None,
            date_year=None,
            date_month=None,
            date_day=None,
            headline=f"Undated {offset + 1}",
            era="Archive",
            note_type="mindmap",
            body_markdown="",
            body_json='{"data":{"text":"undated"}}',
        )
        db_session.add(event)
        db_session.flush()
        undated_ids.append(event.id)
    backfill_note_text_fields(db_session)
    rebuild_topic_read_models(db_session)
    db_session.commit()

    page = client.get(f"/api/topics/{seeded_topic.id}/events")
    assert page.status_code == 200
    payload = page.json()
    assert len(payload["items"]) == 100
    assert payload["hasMore"] is True
    assert payload["nextCursor"]
    first = payload["items"][0]
    assert "bodyMarkdown" not in first
    assert "attachments" not in first
    assert "items" not in first
    assert "searchText" in first
    assert "preview" in first

    seen = {item["id"] for item in payload["items"]}
    cursor = payload["nextCursor"]
    while cursor:
        next_page = client.get(f"/api/topics/{seeded_topic.id}/events", params={"cursor": cursor})
        assert next_page.status_code == 200
        next_payload = next_page.json()
        ids = [item["id"] for item in next_payload["items"]]
        assert not (seen & set(ids))
        seen.update(ids)
        cursor = next_payload["nextCursor"] if next_payload["hasMore"] else None

    final_ids = {item["id"] for item in client.get(f"/api/topics/{seeded_topic.id}/events", params={"limit": 500}).json()["items"]}
    assert seen == final_ids
    assert set(undated_ids).issubset(seen)


def test_topic_events_descending_flips_dated_order_and_keeps_undated_tail(client, db_session, seeded_topic):
    undated = Note(
        topic_id=seeded_topic.id,
        year="Undated Note",
        sort_key=0.0,
        date_key=None,
        headline="Undated Note",
        era="Archive",
        body_markdown="No date here.",
    )
    db_session.add(undated)
    db_session.flush()
    undated_id = undated.id
    backfill_note_text_fields(db_session)
    rebuild_topic_read_models(db_session)
    db_session.commit()

    asc = client.get(f"/api/topics/{seeded_topic.id}/events").json()["items"]
    asc_dated = [item["dateKey"] for item in asc if item["dateKey"] is not None]
    assert asc_dated == sorted(asc_dated)  # dir defaults to ascending (oldest -> newest)
    assert asc[-1]["id"] == undated_id  # undated sinks to the tail

    desc = client.get(f"/api/topics/{seeded_topic.id}/events", params={"dir": -1}).json()["items"]
    desc_dated = [item["dateKey"] for item in desc if item["dateKey"] is not None]
    assert desc_dated == sorted(desc_dated, reverse=True)  # newest -> oldest
    assert desc[-1]["id"] == undated_id  # undated is NOT floated to the top by descending

    assert {item["id"] for item in asc} == {item["id"] for item in desc}  # same set, reordered


def test_topic_events_descending_cursor_pagination_is_complete_and_ordered(client, db_session, seeded_topic):
    for n in range(2):
        db_session.add(
            Note(
                topic_id=seeded_topic.id,
                year=f"Undated {n}",
                sort_key=0.0,
                date_key=None,
                headline=f"Undated {n}",
                era="Archive",
                body_markdown="",
            )
        )
    backfill_note_text_fields(db_session)
    rebuild_topic_read_models(db_session)
    db_session.commit()

    single_shot = client.get(
        f"/api/topics/{seeded_topic.id}/events", params={"dir": -1, "limit": 500}
    ).json()["items"]
    expected_ids = [item["id"] for item in single_shot]

    walked = []
    seen = set()
    cursor = None
    for _ in range(50):  # safety bound against a runaway cursor
        params = {"dir": -1, "limit": 2}
        if cursor:
            params["cursor"] = cursor
        payload = client.get(f"/api/topics/{seeded_topic.id}/events", params=params).json()
        ids = [item["id"] for item in payload["items"]]
        assert not (seen & set(ids))  # pages never overlap
        seen.update(ids)
        walked.extend(ids)
        if not payload["hasMore"]:
            break
        cursor = payload["nextCursor"]

    assert walked == expected_ids  # small-limit paged walk == single-shot descending order
    dated = [item["dateKey"] for item in single_shot if item["dateKey"] is not None]
    assert dated == sorted(dated, reverse=True)
    tail = [item for item in single_shot if item["dateKey"] is None]
    assert len(tail) == 2 and single_shot[-2:] == tail  # undated pair trails the whole descending run


def _walk_all_pages(client, topic_id, *, limit, direction=1):
    seen = []
    cursor = None
    for _ in range(200):  # safety bound against a runaway cursor
        params = {"limit": limit, "dir": direction}
        if cursor:
            params["cursor"] = cursor
        resp = client.get(f"/api/topics/{topic_id}/events", params=params)
        assert resp.status_code == 200, resp.text  # every cursor token must resume, never 500/400
        payload = resp.json()
        seen.extend(item["id"] for item in payload["items"])
        if not payload["hasMore"]:
            return seen
        cursor = payload["nextCursor"]
    raise AssertionError("pagination did not terminate")


def test_topic_events_pages_through_an_undated_tail_that_crosses_a_boundary(client, db_session, seeded_topic):
    # 3 undated notes at limit=2 forces the undated tail to span a page boundary, so
    # next_cursor becomes "null:<id>" — building the dated comparison for that cursor
    # would raise (date_key < None). Guards against the hoisted-`dated_after` regression.
    for n in range(3):
        db_session.add(
            Note(
                topic_id=seeded_topic.id,
                year=f"Undated {n}",
                sort_key=0.0,
                date_key=None,
                headline=f"Undated {n}",
                era="Archive",
                body_markdown="",
            )
        )
    backfill_note_text_fields(db_session)
    rebuild_topic_read_models(db_session)
    db_session.commit()

    all_ids = [
        item["id"]
        for item in client.get(f"/api/topics/{seeded_topic.id}/events", params={"limit": 500}).json()["items"]
    ]
    assert _walk_all_pages(client, seeded_topic.id, limit=2) == all_ids  # complete across the null-cursor hop


def test_topic_events_cursor_round_trips_for_non_four_digit_years(client, db_session, seeded_topic):
    # date_key for years <1000 / <100 / BCE is not an 8-digit YYYYMMDD, so a cursor
    # token minted from it must parse back as a raw int, not a human date (else 400 on
    # a 7-digit/negative key, or a silent mis-parse on a 6-digit key).
    for year in (-626, 99, 907, 1050):
        dk = make_date_key(year, 1, 1)
        db_session.add(
            Note(
                topic_id=seeded_topic.id,
                year=str(year),
                sort_key=float(dk),
                date_key=dk,
                date_year=year,
                date_month=1,
                date_day=1,
                headline=f"Y{year}",
                era="Ancient",
                body_markdown="",
            )
        )
    backfill_note_text_fields(db_session)
    rebuild_topic_read_models(db_session)
    db_session.commit()

    for direction in (1, -1):
        expected = [
            item["id"]
            for item in client.get(
                f"/api/topics/{seeded_topic.id}/events", params={"limit": 500, "dir": direction}
            ).json()["items"]
        ]
        assert _walk_all_pages(client, seeded_topic.id, limit=2, direction=direction) == expected, f"dir={direction}"


def test_import_accepts_legacy_and_v2_payloads(db_session, seeded_topic):
    legacy_payload = [
        {
            "year": "1843年1月1日 Legacy Import",
            "sortKey": 18430101,
            "era": "Modern China",
            "events": [{"tag": "war", "text": "Legacy import path."}],
        }
    ]
    result = import_topic_data(db_session, seeded_topic.id, legacy_payload)
    assert result["count"] == 1

    v2_payload = {
        "title": "History",
        "subtitle": "Daily history",
        "columns": [
            {"key": "place", "label": "地点", "type": "text", "width": 96, "order": 0, "visible": True}
        ],
        "events": [
            {
                "dateYear": 1844,
                "dateMonth": 4,
                "dateDay": 2,
                "headline": "V2 Import",
                "era": "Modern China",
                "extra": {"place": "上海"},
                "items": [{"tag": "politics", "text": "V2 import path."}],
                "image": None,
            }
        ],
    }
    result = import_topic_data(db_session, seeded_topic.id, v2_payload)
    assert result["count"] == 1

    exported, _ = export_topic_data(db_session, seeded_topic.id)
    assert exported["schemaVersion"] == 2
    assert exported["columns"][0]["key"] == "place"
    assert exported["events"][0]["headline"] == "V2 Import"
    assert exported["events"][0]["extra"] == {"place": "上海"}


def test_bookshelf_schema_migration_adds_topic_column_and_assigns_default_and_qs_topics(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy-bookshelf.db"
    test_engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    with test_engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE topics ("
                "id INTEGER PRIMARY KEY, name TEXT, title TEXT, subtitle TEXT, "
                "created_at DATETIME, updated_at DATETIME)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO topics (id, name, title, subtitle, created_at, updated_at) "
                "VALUES (1, 'history', 'History', '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO topics (id, name, title, subtitle, created_at, updated_at) "
                "VALUES (2, '求是网-理论', '求是网-理论', '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO topics (id, name, title, subtitle, created_at, updated_at) "
                "VALUES (3, '求是杂志-2026年第13期', '求是杂志-2026年第13期', '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )

    Base.metadata.create_all(bind=test_engine)
    monkeypatch.setattr(legacy_migration_module, "engine", test_engine)
    legacy_migration_module.ensure_note_schema()
    legacy_migration_module.ensure_note_schema()

    inspector = inspect(test_engine)
    assert "bookshelves" in inspector.get_table_names()
    assert "bookshelf_id" in {column["name"] for column in inspector.get_columns("topics")}

    SessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False, future=True)
    session = SessionLocal()
    try:
        assert ensure_topic_bookshelf_assignments(session) == 5
        session.commit()
        rows = session.execute(
            text(
                """
                SELECT topics.name, bookshelves.name AS bookshelf_name, bookshelves.title AS bookshelf_title
                FROM topics
                LEFT JOIN bookshelves ON bookshelves.id = topics.bookshelf_id
                ORDER BY topics.id
                """
            )
        ).mappings().all()
    finally:
        session.close()
        test_engine.dispose()

    assert rows[0]["bookshelf_name"] == "default"
    assert rows[0]["bookshelf_title"] == "编年"
    assert rows[1]["bookshelf_name"] == "qstheory"
    assert rows[1]["bookshelf_title"] == "求是"
    assert rows[2]["bookshelf_name"] == "qstheory"
    assert rows[2]["bookshelf_title"] == "求是"


def test_bookshelf_migration_seeds_default_shelf_for_empty_database(monkeypatch, tmp_path):
    db_path = tmp_path / "empty.db"
    test_engine = create_engine(f"sqlite:///{db_path}", future=True)

    Base.metadata.create_all(bind=test_engine)
    monkeypatch.setattr(legacy_migration_module, "engine", test_engine)
    legacy_migration_module.ensure_note_schema()

    SessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False, future=True)
    session = SessionLocal()
    try:
        assert ensure_topic_bookshelf_assignments(session) == 1
        session.commit()
        rows = session.execute(
            text("SELECT name, title FROM bookshelves ORDER BY id")
        ).mappings().all()
    finally:
        session.close()
        test_engine.dispose()

    assert rows == [{"name": "default", "title": "编年"}]
