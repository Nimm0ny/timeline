import argparse
import json
import sqlite3

import pytest

from tools.political_ingestion import cli
from tools import political_ingestion_scheduled_run as scheduled


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
    "force_https": True,
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
            b'<a href="/2026/07/13/content_1.htm">Listed title</a>'
            b'<a href="http://example.gov.cn/2026/07/13/content_1.htm">HTTP duplicate</a>'
            b'<a href="https://evil.test/x">x</a></html>'
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


def test_image_only_official_document_is_kept_as_remote_markdown_image(monkeypatch):
    article_url = "https://example.gov.cn/2026/07/13/content_1.htm"
    page = (
        '<html><meta name="firstpublishedtime" content="2026-07-13">'
        '<h1>图片正文政策文件</h1><div id="content">'
        '<p><img src="/images/policy.jpg" alt="政策正文"></p></div></html>'
    ).encode()
    monkeypatch.setattr(cli, "fetch", lambda *_args: (page, "text/html; charset=utf-8"))

    source = {**SOURCE, "allow_image_only": True}
    note = cli.article_note(source, {"url": article_url, "listedTitle": ""}, 1, 1)

    assert "![政策正文](https://example.gov.cn/images/policy.jpg)" in note["bodyMarkdown"]


@pytest.mark.parametrize("image_url", ["javascript:alert(1)", "data:image/png;base64,abc", "https://evil.test/a.jpg"])
def test_image_only_document_rejects_unsafe_or_external_media(monkeypatch, image_url):
    article_url = "https://example.gov.cn/2026/07/13/content_1.htm"
    page = (
        '<html><meta name="firstpublishedtime" content="2026-07-13">'
        f'<h1>无效图片正文</h1><div id="content"><img src="{image_url}"></div></html>'
    ).encode()
    monkeypatch.setattr(cli, "fetch", lambda *_args: (page, "text/html; charset=utf-8"))

    with pytest.raises(ValueError, match="Incomplete article parse"):
        cli.article_note({**SOURCE, "allow_image_only": True}, {"url": article_url, "listedTitle": ""}, 1, 1)


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
    assert issuer_plan["added"] == 1

    assert cli.identity_url("http://a.gov.cn:80/b?track=1") == cli.identity_url("https://a.gov.cn:443/b")


def test_clean_text_and_url_date_key_handle_provincial_page_variants():
    assert cli.clean_text("\u200b北京市人民政府\ufeff") == "北京市人民政府"
    assert cli.url_date_key("https://www.jiangsu.gov.cn/art/2026/6/5/article.html") == "20260605"


def test_source_max_items_bounds_default_discovery(monkeypatch):
    source = {**SOURCE, "max_items": 1, "link_pattern": "/20\\d{2}/07/13/content_1\\.htm$"}
    page = (
        b'<a href="/2026/07/13/content_1.htm">Newest</a>'
        b'<a href="/2025/07/13/content_1.htm">Older</a>'
    )
    monkeypatch.setattr(cli, "fetch", lambda *_args: (page, "text/html; charset=utf-8"))

    assert len(cli.discover(source, 1, 1, 0)) == 1
    assert len(cli.discover(source, 1, 1, 2)) == 2


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

    changed_adapter = {**SOURCE, "body_xpaths": ["//main"]}
    with pytest.raises(ValueError, match="no longer valid"):
        cli.validate_manifest_registry(manifest, {"sources": [changed_adapter]})


@pytest.mark.parametrize("dry_run", [True, False])
def test_scheduled_cycle_applies_only_the_new_manifest(monkeypatch, tmp_path, dry_run):
    registry = {"sets": {"weekly": [SOURCE["id"]]}, "sources": [SOURCE]}
    manifest_path = tmp_path / "runs" / "new" / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
    applied = []

    monkeypatch.setattr(scheduled.cli, "load_registry", lambda _path: registry)
    monkeypatch.setattr(scheduled, "wait_for_api", lambda *_args: None)
    monkeypatch.setattr(
        scheduled.cli,
        "run_workflow",
        lambda *_args: {
            "outputDir": str(manifest_path.parent), "manifest": str(manifest_path),
            "dryRun": True, "plan": {"candidates": 1, "added": 1, "duplicates": 0},
        },
    )
    monkeypatch.setattr(
        scheduled.cli,
        "apply_manifest",
        lambda args, _registry: applied.append(args.manifest) or {"status": "complete"},
    )
    args = argparse.Namespace(
        registry=str(tmp_path / "sources.json"), set_name="weekly", state_dir=str(tmp_path),
        database=str(tmp_path / "timeline.db"), base_url="http://127.0.0.1",
        backup_dir=str(tmp_path / "backups"), timeout=1, retries=1, limit=1,
        keep_runs=8, keep_backups=16, ready_timeout=1, ready_delay=0.01, dry_run=dry_run,
    )

    result = scheduled.run_cycle(args)

    assert applied == ([] if dry_run else [str(manifest_path)])
    assert result["apply"] == (None if dry_run else {"status": "complete"})


def test_scheduled_pruning_is_bounded_and_backup_specific(tmp_path):
    run_root = tmp_path / "runs"
    backup_dir = tmp_path / "backups"
    for name in ("001", "002", "003"):
        (run_root / name).mkdir(parents=True)
        (backup_dir / f"timeline_db_prepolitics_{name}.db").parent.mkdir(parents=True, exist_ok=True)
        (backup_dir / f"timeline_db_prepolitics_{name}.db").touch()
    unrelated = backup_dir / "timeline_predeploy_keep.db"
    unrelated.touch()

    scheduled.prune_runs(run_root, 2)
    scheduled.prune_backups(backup_dir, 2)

    assert sorted(path.name for path in run_root.iterdir()) == ["002", "003"]
    assert sorted(path.name for path in backup_dir.glob("timeline_db_prepolitics_*.db")) == [
        "timeline_db_prepolitics_002.db", "timeline_db_prepolitics_003.db",
    ]
    assert unrelated.exists()


def test_scheduled_cycle_prunes_after_crawl_failure(monkeypatch, tmp_path):
    registry = {"sets": {"weekly": [SOURCE["id"]]}, "sources": [SOURCE]}
    run_root = tmp_path / "runs"
    backup_dir = tmp_path / "backups"
    for name in ("001", "002"):
        (run_root / name).mkdir(parents=True)
        backup_dir.mkdir(parents=True, exist_ok=True)
        (backup_dir / f"timeline_db_prepolitics_{name}.db").touch()
    monkeypatch.setattr(scheduled.cli, "load_registry", lambda _path: registry)
    monkeypatch.setattr(scheduled, "wait_for_api", lambda *_args: None)
    monkeypatch.setattr(scheduled.cli, "run_workflow", lambda *_args: (_ for _ in ()).throw(RuntimeError("crawl failed")))
    args = argparse.Namespace(
        registry=str(tmp_path / "sources.json"), set_name="weekly", state_dir=str(tmp_path),
        database=str(tmp_path / "timeline.db"), base_url="http://127.0.0.1",
        backup_dir=str(backup_dir), timeout=1, retries=1, limit=1,
        keep_runs=1, keep_backups=1, ready_timeout=1, ready_delay=0.01, dry_run=False,
    )

    with pytest.raises(RuntimeError, match="crawl failed"):
        scheduled.run_cycle(args)

    assert [path.name for path in run_root.iterdir()] == ["002"]
    assert [path.name for path in backup_dir.iterdir()] == ["timeline_db_prepolitics_002.db"]


def test_limit_parser_rejects_negative_values():
    with pytest.raises(argparse.ArgumentTypeError):
        cli.nonnegative_int("-1")
    with pytest.raises(argparse.ArgumentTypeError):
        scheduled.positive_float("nan")


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
