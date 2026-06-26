from backend.app.services.timeline import export_topic_data, import_topic_data


def test_topic_meta_range_and_summary(client, seeded_topic):
    meta = client.get(f"/api/topics/{seeded_topic.id}/meta")
    assert meta.status_code == 200
    body = meta.json()
    assert body["columns"] == []
    assert body["minDateKey"] == 18400101
    assert body["maxDateKey"] == 18410215
    assert body["eventCount"] == 4

    summary = client.get(f"/api/topics/{seeded_topic.id}/summary", params={"groupBy": "month"})
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["items"][0]["displayLabel"] == "1840-01"
    assert payload["items"][0]["eventCount"] == 2


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
    assert existing.json()["items"][0]["bodyMarkdown"] == "Conflict begins."

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
    event_id = events[0]["id"]

    favorite = client.put(f"/api/events/{event_id}", json={"favorite": True})
    assert favorite.status_code == 200
    assert favorite.json()["favorite"] is True
    assert favorite.json()["deletedAt"] is None

    deleted = client.delete(f"/api/events/{event_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deletedAt"]

    after_delete = client.get(f"/api/topics/{seeded_topic.id}/events").json()["items"]
    deleted_event = next(item for item in after_delete if item["id"] == event_id)
    assert deleted_event["deletedAt"]

    blocked_favorite = client.put(f"/api/events/{event_id}", json={"favorite": False})
    assert blocked_favorite.status_code == 409

    blocked_edit = client.put(
        f"/api/events/{event_id}",
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

    restored = client.put(f"/api/events/{event_id}", json={"deletedAt": None})
    assert restored.status_code == 200
    assert restored.json()["deletedAt"] is None

    permanent = client.delete(f"/api/events/{event_id}", params={"permanent": "true"})
    assert permanent.status_code == 200

    after_permanent = client.get(f"/api/topics/{seeded_topic.id}/events").json()["items"]
    assert event_id not in [item["id"] for item in after_permanent]


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
