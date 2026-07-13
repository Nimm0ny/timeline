import json
import sqlite3

import pytest

from tools.political_ingestion import cli


SOURCE = {
    "id": "fixture",
    "name": "官方测试源",
    "enabled": True,
    "priority": 1,
    "bookshelf": {"name": "politics_central", "title": "中央国家机关"},
    "notebook": "测试机构",
    "group": "政策文件",
    "issuer": "测试机构",
    "list_url": "https://example.gov.cn/list/",
    "allowed_hosts": ["example.gov.cn"],
    "link_xpath": "//a[@href]",
    "link_pattern": "/2026/07/13/content_1\\.htm$",
    "title_xpaths": ["//h1"],
    "body_xpaths": ["//*[@id='content']"],
    "date_meta": "firstpublishedtime",
}


def test_discover_and_normalize_article(monkeypatch):
    pages = {
        SOURCE["list_url"]: (
            b'<html><a href="/2025/01/01/content_1.htm">Old duplicate path</a>'
            b'<a href="/2026/07/13/content_1.htm">Listed title</a><a href="https://evil.test/x">x</a></html>'
        ),
        "https://example.gov.cn/2026/07/13/content_1.htm": (
            '<html><meta name="firstpublishedtime" content="2026-07-13-09:00:00">'
            '<h1>关于测试工作的通知</h1><div id="content"><p>第一段正文，提供足够的正式文件内容。</p>'
            '<p>第二段正文，用于验证 Markdown 正文和稳定哈希生成。</p>'
            '<p>第三段正文，确保正文长度超过完整性检查阈值。</p>'
            '<p>第四段正文，验证完整文章能够进入标准化结果。</p>'
            '<a href="/attachments/policy.wps">政策附件</a></div></html>'
        ).encode(),
    }
    fetched_urls = []

    def fake_fetch(url, _timeout, _retries):
        fetched_urls.append(url)
        return pages[url], "text/html; charset=utf-8"

    monkeypatch.setattr(cli, "fetch", fake_fetch)

    items = cli.discover(SOURCE, 1, 1, 1)
    note = cli.article_note(SOURCE, items[0], 1, 1)

    assert [item["url"] for item in items] == ["https://example.gov.cn/2026/07/13/content_1.htm"]
    assert note["headline"] == "关于测试工作的通知"
    assert note["dateYear"] == 2026
    assert "第二段正文" in note["bodyMarkdown"]
    assert "## 原文附件" in note["bodyMarkdown"]
    assert "[政策附件](https://example.gov.cn/attachments/policy.wps)" in note["bodyMarkdown"]
    assert fetched_urls == [SOURCE["list_url"], "https://example.gov.cn/2026/07/13/content_1.htm"]
    assert len(note["extra"]["content_hash"]) == 64


def test_attachment_only_page_keeps_query_links_without_fetching_files(monkeypatch):
    article_url = "https://example.gov.cn/2026/07/13/content_1.htm"
    page = (
        '<html><meta name="firstpublishedtime" content="2026-07-13">'
        '<h1>附件承载的政策文件</h1><div id="content">'
        '<a href="/download?file=policy%2Epdf&amp;token=abc">PDF附件</a>'
        '<a href="/download?id=2" download="policy.ofd">OFD附件</a>'
        '<a href="javascript:alert(1)">危险链接</a></div></html>'
    ).encode()
    fetched_urls = []

    def fake_fetch(url, _timeout, _retries):
        fetched_urls.append(url)
        return page, "text/html; charset=utf-8"

    monkeypatch.setattr(cli, "fetch", fake_fetch)

    note = cli.article_note(SOURCE, {"url": article_url, "listedTitle": ""}, 1, 1)

    assert "[PDF附件](https://example.gov.cn/download?file=policy%2Epdf&token=abc)" in note["bodyMarkdown"]
    assert "[OFD附件](https://example.gov.cn/download?id=2)" in note["bodyMarkdown"]
    assert "javascript:" not in note["bodyMarkdown"]
    assert fetched_urls == [article_url]


def test_deduplicate_uses_document_url_fallback_and_hash():
    base = {
        "dateYear": 2026, "dateMonth": 7, "dateDay": 13, "headline": "测试通知",
        "extra": {"issuer": "国务院", "document_no": "国发〔2026〕1号", "source_url": "https://a.gov.cn/a?track=1", "content_hash": "abc"},
    }
    same_document = {**base, "extra": {**base["extra"], "source_url": "https://b.gov.cn/repost"}}
    different = {**base, "headline": "另一份通知", "extra": {"source_url": "https://a.gov.cn/b", "content_hash": "def"}}

    accepted, plan = cli.deduplicate([{"notes": [base, same_document, different]}], [])

    assert plan == {"candidates": 3, "added": 2, "duplicates": 1}
    assert [note["headline"] for note in accepted[0]["notes"]] == ["测试通知", "另一份通知"]

    other_issuer = {**base, "extra": {**base["extra"], "issuer": "某省人民政府", "source_url": "https://c.gov.cn/a", "content_hash": "ghi"}}
    _, issuer_plan = cli.deduplicate([{"notes": [base, other_issuer]}], [])
    assert issuer_plan["added"] == 2


def test_registry_rejects_disabled_source(tmp_path):
    registry = {"sets": {"all": ["disabled"]}, "sources": [{"id": "disabled", "enabled": False}]}
    path = tmp_path / "sources.json"
    path.write_text(json.dumps(registry), encoding="utf-8")

    loaded = cli.load_registry(path)
    with pytest.raises(ValueError, match="Disabled sources"):
        cli.selected_sources(loaded, [], "all")


def test_backup_database_is_valid(tmp_path):
    source = tmp_path / "source.db"
    destination = tmp_path / "backups" / "backup.db"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE sample (value TEXT)")
        connection.execute("INSERT INTO sample VALUES ('kept')")

    cli.backup_database(source, destination)

    with sqlite3.connect(destination) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone() == ("kept",)
        assert connection.execute("PRAGMA quick_check").fetchone() == ("ok",)


def test_apply_batches_creates_shelf_topic_columns_and_notes():
    class FakeClient:
        def __init__(self):
            self.calls = []

        def request(self, method, path, payload=None):
            self.calls.append((method, path, payload))
            if method == "POST" and path == "/api/bookshelves":
                return {"id": 10, **payload, "topics": []}
            if method == "POST" and path == "/api/topics":
                return {"id": 20, "name": payload["name"]}
            if method == "GET" and path == "/api/topics/20/meta":
                return {"columns": []}
            return {"id": 30}

    client = FakeClient()
    note = {"headline": "政策", "dateYear": 2026, "dateMonth": 7, "dateDay": 13, "extra": {}}
    batches = [
        {"bookshelf": SOURCE["bookshelf"], "notebook": SOURCE["notebook"], "notes": [note]},
        {"bookshelf": SOURCE["bookshelf"], "notebook": SOURCE["notebook"], "notes": [{**note, "headline": "政策二"}]},
    ]
    result = cli.apply_batches(client, [], batches)

    assert result == {"createdBookshelves": 1, "createdNotebooks": 1, "added": 2}
    assert ("POST", "/api/topics/20/notes", note) in client.calls
    assert sum(call[:2] == ("POST", "/api/topics") for call in client.calls) == 1
    column_call = next(call for call in client.calls if call[:2] == ("PUT", "/api/topics/20/meta"))
    assert {column["key"] for column in column_call[2]["columns"]} == {column["key"] for column in cli.EXTRA_COLUMNS}


def test_target_validation_and_apply_target_are_strict(tmp_path):
    tree = [{"name": "default", "topics": [{"topic": {"name": SOURCE["notebook"]}}]}]
    batch = {"bookshelf": SOURCE["bookshelf"], "notebook": SOURCE["notebook"], "notes": []}
    with pytest.raises(ValueError, match="exists outside bookshelf"):
        cli.validate_topic_targets(tree, [batch])
    with pytest.raises(ValueError, match="loopback"):
        cli.validate_apply_target("https://remote.example", cli.ROOT / "data" / "timeline.db")
    with pytest.raises(ValueError, match="data/timeline.db"):
        cli.validate_apply_target("http://127.0.0.1", tmp_path / "other.db")


def test_manifest_checksum_detects_changes():
    manifest = {"schemaVersion": 1, "errors": [], "batches": [{"notes": []}]}
    manifest["checksum"] = cli.manifest_checksum(manifest)
    assert manifest["checksum"] == cli.manifest_checksum(manifest)
    manifest["batches"][0]["notes"].append({"headline": "tampered"})
    assert manifest["checksum"] != cli.manifest_checksum(manifest)


def test_manifest_must_match_enabled_registry_contract():
    manifest = {
        "registry": [cli.source_contract(SOURCE)],
        "batches": [{"source": SOURCE["id"], "bookshelf": SOURCE["bookshelf"], "notebook": SOURCE["notebook"], "notes": []}],
    }
    cli.validate_manifest_registry(manifest, {"sources": [SOURCE]})

    disabled = {**SOURCE, "enabled": False}
    with pytest.raises(ValueError, match="no longer valid"):
        cli.validate_manifest_registry(manifest, {"sources": [disabled]})


def test_real_api_contract_is_idempotent(client):
    class TestClientAdapter:
        def request(self, method, path, payload=None):
            response = client.request(method, path, json=payload)
            assert response.status_code < 400, response.text
            return response.json() if response.content else None

    api = TestClientAdapter()
    runtime_identity = api.request("GET", "/api/runtime/identity")["databaseIdentity"]
    assert len(runtime_identity) == 64
    note = {
        "dateYear": 2026, "dateMonth": 7, "dateDay": 13, "headline": "中央测试政策", "era": "政策文件",
        "bodyMarkdown": "完整政策正文", "tags": ["政策文件"], "items": [],
        "extra": {"issuer": "测试部委", "document_no": "测试〔2026〕1号", "source_url": "https://example.gov.cn/policy/1", "content_hash": "hash-1"},
    }
    batches = [{"bookshelf": SOURCE["bookshelf"], "notebook": SOURCE["notebook"], "notes": [note]}]
    tree = api.request("GET", "/api/bookshelves/tree")
    cli.validate_topic_targets(tree, batches)

    first = cli.apply_batches(api, tree, batches)
    updated_tree = api.request("GET", "/api/bookshelves/tree")
    existing = cli.existing_political_notes(api, updated_tree, {SOURCE["bookshelf"]["name"]})
    _, rerun = cli.deduplicate(batches, existing)

    assert first == {"createdBookshelves": 1, "createdNotebooks": 1, "added": 1}
    assert rerun["added"] == 0
