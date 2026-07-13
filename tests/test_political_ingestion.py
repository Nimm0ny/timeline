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

NPC_SOURCE = {
    "id": "npc_reports", "name": "中国人大网权威报告", "enabled": True, "priority": 1,
    "adapter": "npc_reports", "bookshelf": SOURCE["bookshelf"], "notebook": "全国人大",
    "group": "工作报告", "issuer": "全国人大",
    "list_url": "http://www.npc.gov.cn/npc/c2/c12435/c12491/", "allow_http": True,
    "list_pages": 1, "max_items": 30, "allowed_hosts": ["www.npc.gov.cn"],
    "link_xpath": "//a[@href]", "link_pattern": r"/npc/c2/c30834/20\d{4}/.*\.(?:html|pdf)$",
    "title_xpaths": ["//h1"], "body_xpaths": ["//*[@id='Zoom']"],
}

LAW_SOURCE = {
    "id": "national_law_database", "name": "国家法律法规数据库", "enabled": True, "priority": 1,
    "adapter": "national_law_database", "bookshelf": SOURCE["bookshelf"], "notebook": "法律法规",
    "group": "法律法规", "issuer": "全国人大常委会", "list_url": "https://flk.npc.gov.cn/",
    "origin": "https://flk.npc.gov.cn", "list_api": "https://flk.npc.gov.cn/law-search/search/list",
    "detail_api": "https://flk.npc.gov.cn/law-search/search/flfgDetails",
    "detail_url": "https://flk.npc.gov.cn/detail", "max_items": 30,
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


def test_markdown_body_falls_back_to_text_only_layout():
    root = cli.html.fromstring(
        '<div><style>.ignored { color: red; }</style><script>ignored()</script>'
        '这是正文第一部分，页面使用换行标签而不是段落标签。<br>'
        '这是正文第二部分，采集器仍需保存完整文本，不能因为页面排版方式不同而丢弃。<br>'
        '这是正文第三部分，确保内容长度达到完整性校验要求。</div>'
    )

    body, _attachments, source_length, _media_count = cli.markdown_body(root, "https://example.gov.cn/a", {"example.gov.cn"})

    assert source_length >= 80
    assert "这是正文第二部分" in body
    assert "ignored" not in body


def test_npc_reports_support_html_and_link_pdf_without_downloading(monkeypatch):
    list_page = (
        '<ul><li><a href="../../c30834/202606/t20260626_1.html">HTML报告</a>2026-06-26</li>'
        '<li><a href="../../c30834/202606/P0202606251.pdf">PDF报告</a>2026-06-25</li></ul>'
    ).encode()
    article_page = (
        '<h1>HTML报告</h1><div id="Zoom"><p>这是全国人大网站发布的完整报告正文第一段，说明相关工作的总体情况和主要进展。</p>'
        '<p>这是报告正文第二段，继续说明后续工作安排、监督要求以及需要依法推进的具体事项。</p>'
        '<p>这是报告正文第三段，用于确认采集器保存的是报告内容而不是列表摘要或页面导航文字。</p></div>'
    ).encode()
    fetched = []

    def fake_fetch(url, _timeout, _retries):
        fetched.append(url)
        return (list_page if url == NPC_SOURCE["list_url"] else article_page), "text/html; charset=utf-8"

    monkeypatch.setattr(cli, "fetch", fake_fetch)
    items = cli.discover(NPC_SOURCE, 1, 1, 0)
    html_note = cli.article_note(NPC_SOURCE, items[0], 1, 1)
    pdf_note = cli.article_note(NPC_SOURCE, items[1], 1, 1)

    assert [item["listedTitle"] for item in items] == ["HTML报告", "PDF报告"]
    assert "完整报告正文第一段" in html_note["bodyMarkdown"]
    assert "不下载、不解析附件" in pdf_note["bodyMarkdown"]
    assert "[在中国人大网查看 PDF 报告原文](http://www.npc.gov.cn/npc/c2/c30834/202606/P0202606251.pdf)" in pdf_note["bodyMarkdown"]
    assert fetched == [NPC_SOURCE["list_url"], items[0]["url"]]


def test_law_database_uses_json_adapter_and_official_reader_link(monkeypatch):
    calls = []

    def fake_fetch_json(url, _timeout, _retries, **kwargs):
        calls.append((url, kwargs))
        if url == LAW_SOURCE["list_api"]:
            return {"code": 200, "rows": [
                {"bbbs": "law-1", "title": "测试法", "gbrq": "2026-06-26"},
                {"bbbs": "law-2", "title": "超量返回", "gbrq": "2026-06-25"},
            ]}
        return {"code": 200, "data": {
            "bbbs": "law-1", "title": "测试法", "gbrq": "2026-06-26", "sxrq": "2027-01-01", "sxx": 4,
            "flxz": "法律", "zdjgName": "全国人民代表大会常务委员会",
            "content": {"children": [{"title": "第一章 总则", "children": [{"title": "第一条", "children": []}]}]},
        }}

    monkeypatch.setattr(cli, "fetch_json", fake_fetch_json)
    items = cli.discover(LAW_SOURCE, 1, 1, 1)
    note = cli.article_note(LAW_SOURCE, items[0], 1, 1)

    assert note["headline"] == "测试法"
    assert "- 时效性：尚未生效" in note["bodyMarkdown"]
    assert "### 第一章 总则" in note["bodyMarkdown"]
    assert "[在国家法律法规数据库阅读标准文本](https://flk.npc.gov.cn/detail?id=law-1&title=%E6%B5%8B%E8%AF%95%E6%B3%95)" in note["bodyMarkdown"]
    assert note["extra"]["issuer"] == "全国人民代表大会常务委员会"
    assert calls[0][1]["method"] == "POST"
    assert calls[0][1]["payload"]["pageSize"] == 1
    assert calls[0][1]["payload"]["orderByParam"] == {"order": "gbrq", "sort": "DESC"}
    assert calls[1][0].endswith("?bbbs=law-1")


def test_law_database_rejects_mismatched_detail(monkeypatch):
    item = {
        "url": "https://flk.npc.gov.cn/detail?id=law-1", "listedTitle": "测试法",
        "record": {"bbbs": "law-1", "title": "测试法", "gbrq": "2026-06-26"},
    }
    monkeypatch.setattr(cli, "fetch_json", lambda *_args, **_kwargs: {
        "code": 200, "data": {"bbbs": "law-2", "title": "另一部法", "gbrq": "2026-06-25"},
    })

    with pytest.raises(ValueError, match="Mismatched law detail"):
        cli.article_note(LAW_SOURCE, item, 1, 1)


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
    assert cli.identity_url("https://flk.npc.gov.cn/detail?id=law-1&title=a") == "flk.npc.gov.cn/detail?id=law-1"
    assert cli.identity_url("https://flk.npc.gov.cn/detail?id=law-1") != cli.identity_url("https://flk.npc.gov.cn/detail?id=law-2")


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


def test_registry_requires_explicit_http_transport_exception(tmp_path):
    registry = {"sets": {}, "sources": [{"id": "unsafe", "enabled": True, "list_url": "http://example.test/list"}]}
    path = tmp_path / "sources.json"
    path.write_text(json.dumps(registry), encoding="utf-8")

    with pytest.raises(ValueError, match="fixed NPC exception"):
        cli.load_registry(path)

    registry["sources"][0]["allow_http"] = True
    path.write_text(json.dumps(registry), encoding="utf-8")
    with pytest.raises(ValueError, match="fixed NPC exception"):
        cli.load_registry(path)

    path.write_text(json.dumps({"sets": {}, "sources": [NPC_SOURCE]}), encoding="utf-8")
    assert cli.load_registry(path)["sources"][0]["id"] == "npc_reports"


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
