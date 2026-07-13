import json

import pytest

from tools.qstheory_batch_scraper import latest_issue_link, record_skipped_article
from tools.qstheory_sync import build_sync_plan, canonical_source_url, exclusive_lock, load_batches, sync_batches


def note(url, headline="文章", day=1):
    return {
        "dateYear": 2026,
        "dateMonth": 7,
        "dateDay": day,
        "headline": headline,
        "era": "理论",
        "bodyMarkdown": "正文",
        "extra": {"source_url": url},
    }


class FakeApiClient:
    def __init__(self):
        self.next_topic_id = 20
        self.shelves = [
            {
                "id": 3,
                "name": "qstheory_web",
                "topics": [{"topic": {"id": 18, "name": "理论"}, "eras": []}],
            },
            {"id": 4, "name": "qstheory_magazine", "topics": []},
        ]
        self.notes = {18: []}
        self.columns = {18: []}
        self.fail_meta_once = False

    def request(self, method, path, payload=None):
        if method == "GET" and path == "/api/bookshelves/tree":
            return self.shelves
        if method == "GET" and path.endswith("/export"):
            topic_id = int(path.split("/")[3])
            return {"notes": list(self.notes[topic_id])}
        if method == "GET" and path.endswith("/meta"):
            topic_id = int(path.split("/")[3])
            return {"columns": list(self.columns[topic_id])}
        if method == "POST" and path == "/api/topics":
            topic = {"id": self.next_topic_id, "name": payload["name"]}
            self.next_topic_id += 1
            shelf = next(item for item in self.shelves if item["id"] == payload["bookshelfId"])
            shelf["topics"].append({"topic": topic, "eras": []})
            self.notes[topic["id"]] = []
            self.columns[topic["id"]] = []
            return topic
        if method == "PUT" and path.endswith("/meta"):
            if self.fail_meta_once:
                self.fail_meta_once = False
                raise RuntimeError("simulated metadata failure")
            topic_id = int(path.split("/")[3])
            if "columns" in payload:
                self.columns[topic_id] = list(payload["columns"])
            return {"ok": True}
        if method == "POST" and path.endswith("/notes"):
            topic_id = int(path.split("/")[3])
            self.notes[topic_id].append(payload)
            return {"id": len(self.notes[topic_id])}
        raise AssertionError((method, path, payload))


def test_canonical_source_url_removes_tracking_and_normalizes_host_and_scheme():
    assert canonical_source_url("http://qstheory.cn/a/c.html?from=home#part") == "https://www.qstheory.cn/a/c.html"


def test_sync_plan_deduplicates_candidates_and_existing_notes():
    first = note("https://www.qstheory.cn/a/c.html")
    duplicate = note("https://www.qstheory.cn/a/c.html?tracking=1", headline="另一个列表标题")
    existing = note("http://qstheory.cn/b/c.html")
    plan = build_sync_plan([first, duplicate, existing], [existing])
    assert plan.notes == [first]
    assert plan.duplicate_candidates == 1
    assert plan.existing_matches == 1


def test_sync_plan_matches_url_candidate_to_legacy_note_without_url():
    candidate = note("https://www.qstheory.cn/a/c.html", headline="同一文章")
    legacy = {**candidate, "extra": {}}
    plan = build_sync_plan([candidate], [legacy])
    assert plan.notes == []
    assert plan.existing_matches == 1


def test_sync_is_idempotent_and_keeps_sources_in_separate_bookshelves():
    client = FakeApiClient()
    columns = [{"key": "source_url", "label": "原文链接", "type": "url"}]
    web_batches = [("理论", {"columns": columns, "notes": [note("https://www.qstheory.cn/a/c.html"), note("https://www.qstheory.cn/a/c.html")]})]
    first = sync_batches(client, web_batches, "web", dry_run=False)
    second = sync_batches(client, web_batches, "web", dry_run=False)
    assert first["added"] == 1
    assert first["skippedDuplicateCandidates"] == 1
    assert second["added"] == 0
    assert second["skippedExisting"] == 1
    assert client.columns[18] == columns

    magazine_batches = [("2026年第14期", {"title": "2026年第14期", "columns": [], "notes": [note("https://www.qstheory.cn/m/c.html")]})]
    magazine = sync_batches(client, magazine_batches, "magazine", dry_run=False)
    assert magazine["createdTopics"] == 1
    magazine_shelf = next(item for item in client.shelves if item["name"] == "qstheory_magazine")
    assert [item["topic"]["name"] for item in magazine_shelf["topics"]] == ["2026年第14期"]


def test_sync_recovers_when_new_topic_metadata_write_failed():
    client = FakeApiClient()
    client.fail_meta_once = True
    columns = [{"key": "source_url", "label": "原文链接", "type": "url"}]
    batches = [("2026年第14期", {"columns": columns, "notes": [note("https://www.qstheory.cn/m/c.html")]})]
    with pytest.raises(RuntimeError, match="metadata failure"):
        sync_batches(client, batches, "magazine", dry_run=False)
    result = sync_batches(client, batches, "magazine", dry_run=False)
    assert result["added"] == 1
    assert client.columns[20] == columns


def test_load_batches_rejects_cross_source_manifest(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"source": "magazine", "topics": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="does not match"):
        load_batches(tmp_path, "web")


def test_load_batches_rejects_errors_and_path_escape(tmp_path):
    outside = tmp_path.parent / "outside.json"
    outside.write_text(json.dumps({"events": []}), encoding="utf-8")
    manifest = {"source": "web", "errors": ["network"], "topics": []}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="crawl errors"):
        load_batches(tmp_path, "web")

    manifest = {"source": "web", "errors": [], "topics": [{"topic": "理论", "file": "../outside.json"}]}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid topic file path"):
        load_batches(tmp_path, "web")


def test_load_batches_rejects_duplicate_topic_mapping(tmp_path):
    topic_path = tmp_path / "理论.json"
    topic_path.write_text(json.dumps({"events": []}), encoding="utf-8")
    item = {"topic": "理论", "file": topic_path.name}
    manifest = {"source": "web", "errors": [], "topics": [item, item]}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate topic or file"):
        load_batches(tmp_path, "web")


def test_latest_issue_link_uses_numeric_issue_order():
    links = [("2026年第9期", "nine"), ("2026年第13期", "thirteen"), ("2026年第10期", "ten")]
    assert latest_issue_link(links) == [("2026年第13期", "thirteen")]


def test_strict_or_latest_issue_records_skipped_articles():
    failures = []
    record_skipped_article(failures, "https://example.test/a", RuntimeError("missing"), strict=False)
    assert failures == []
    record_skipped_article(failures, "https://example.test/a", RuntimeError("missing"), strict=True)
    assert len(failures) == 1


def test_exclusive_lock_rejects_overlap(tmp_path):
    lock_path = tmp_path / "sync.lock"
    with exclusive_lock(lock_path):
        with pytest.raises(RuntimeError, match="Another qstheory sync"):
            with exclusive_lock(lock_path):
                pass


def test_exclusive_lock_preserves_body_oserror(tmp_path):
    with pytest.raises(OSError, match="network failure"):
        with exclusive_lock(tmp_path / "sync.lock"):
            raise OSError("network failure")
