from backend.app.services.timeline import export_topic_data, import_topic_data


def test_topic_meta_range_and_summary(client, seeded_topic):
    meta = client.get(f"/api/topics/{seeded_topic.id}/meta")
    assert meta.status_code == 200
    body = meta.json()
    assert body["minDateKey"] == 18400101
    assert body["maxDateKey"] == 18410215
    assert body["eventCount"] == 4

    summary = client.get(f"/api/topics/{seeded_topic.id}/summary", params={"groupBy": "month"})
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["items"][0]["displayLabel"] == "1840-01"
    assert payload["items"][0]["eventCount"] == 2


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


def test_event_contract_persists_markdown_tags_attachments_and_related_events(client, seeded_topic, db_session):
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
            "tags": ["source", "treaty", "source"],
            "attachments": [
                {
                    "id": None,
                    "name": "archive-note.md",
                    "filename": "archive-note.md",
                    "mimeType": "text/markdown",
                }
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
    assert created["tags"] == ["source", "treaty"]
    assert created["attachments"][0]["url"] == "/images/archive-note.md"
    assert created["relatedEventIds"] == [related_id]
    assert created["relatedEvents"][0]["id"] == related_id
    assert created["createdAt"]
    assert created["updatedAt"]
    assert created["favorite"] is True
    assert created["deletedAt"] is None
    assert created["items"][0]["tag"] == "source"

    updated = client.put(
        f"/api/events/{created['id']}",
        json={
            "dateYear": 1842,
            "dateMonth": 4,
            "dateDay": 9,
            "headline": "Markdown Contract Updated",
            "era": "Modern China",
            "bodyMarkdown": "Updated body",
            "tags": ["updated"],
            "attachments": [],
            "relatedEventIds": [related_id],
            "items": [{"tag": "updated", "text": "Explicit item path."}],
            "image": None,
        },
    )
    assert updated.status_code == 200
    payload = updated.json()
    assert payload["headline"] == "Markdown Contract Updated"
    assert payload["bodyMarkdown"] == "Updated body"
    assert payload["tags"] == ["updated"]
    assert payload["items"] == [{"tag": "updated", "text": "Explicit item path."}]
    assert payload["favorite"] is True

    exported, _ = export_topic_data(db_session, seeded_topic.id)
    exported_event = next(item for item in exported["events"] if item["id"] == created["id"])
    assert exported_event["bodyMarkdown"] == "Updated body"
    assert exported_event["relatedEvents"][0]["id"] == related_id


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
        "events": [
            {
                "dateYear": 1844,
                "dateMonth": 4,
                "dateDay": 2,
                "headline": "V2 Import",
                "era": "Modern China",
                "items": [{"tag": "politics", "text": "V2 import path."}],
                "image": None,
            }
        ],
    }
    result = import_topic_data(db_session, seeded_topic.id, v2_payload)
    assert result["count"] == 1

    exported, _ = export_topic_data(db_session, seeded_topic.id)
    assert exported["schemaVersion"] == 2
    assert exported["events"][0]["headline"] == "V2 Import"
