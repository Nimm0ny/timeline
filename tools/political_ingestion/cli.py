from __future__ import annotations

import argparse
from contextlib import closing, contextmanager
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from urllib.error import HTTPError
from urllib.parse import parse_qsl, unquote, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from lxml import html


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = Path(__file__).with_name("sources.json")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
SPACE_RE = re.compile(r"\s+")
DATE_RE = re.compile(r"(?P<year>20\d{2})[-年/](?P<month>\d{1,2})[-月/](?P<day>\d{1,2})")
DOC_NO_RE = re.compile(r"[\u4e00-\u9fffA-Za-z]{1,24}[〔\[]20\d{2}[〕\]]\s*\d+\s*号")
ATTACHMENT_EXTENSIONS = {
    ".7z", ".doc", ".docx", ".ofd", ".pdf", ".ppt", ".pptx",
    ".rar", ".wps", ".xls", ".xlsx", ".zip",
}
EXTRA_COLUMNS = [
    {"key": "source_id", "label": "来源键", "type": "text", "visible": False},
    {"key": "display_source", "label": "来源", "type": "text", "visible": True},
    {"key": "issuer", "label": "发布机构", "type": "text", "visible": True},
    {"key": "document_no", "label": "发文字号", "type": "text", "visible": True},
    {"key": "source_url", "label": "原文链接", "type": "url", "visible": True},
    {"key": "content_hash", "label": "正文哈希", "type": "text", "visible": False},
]


class ApiClient:
    def __init__(self, base_url: str, timeout: float):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(self, method: str, path: str, payload: dict | None = None):
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(f"{self.base_url}{path}", data=body, method=method, headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                content = response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} failed with HTTP {exc.code}: {detail}") from exc
        return json.loads(content.decode("utf-8")) if content else None


def load_registry(path: Path) -> dict:
    registry = json.loads(path.read_text(encoding="utf-8"))
    ids = [source.get("id") for source in registry.get("sources", [])]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("Source registry requires unique source ids")
    return registry


def selected_sources(registry: dict, source_ids: list[str], set_name: str | None) -> list[dict]:
    requested = list(source_ids)
    if set_name:
        if set_name not in registry.get("sets", {}):
            raise ValueError(f"Unknown source set: {set_name}")
        requested.extend(registry["sets"][set_name])
    if not requested:
        requested = [source["id"] for source in registry["sources"] if source.get("enabled")]
    by_id = {source["id"]: source for source in registry["sources"]}
    missing = sorted(set(requested) - set(by_id))
    if missing:
        raise ValueError(f"Unknown sources: {', '.join(missing)}")
    selected = [by_id[source_id] for source_id in dict.fromkeys(requested)]
    disabled = [source["id"] for source in selected if not source.get("enabled")]
    if disabled:
        raise ValueError(f"Disabled sources require an adapter before use: {', '.join(disabled)}")
    return sorted(selected, key=lambda source: (int(source.get("priority", 100)), source["id"]))


def fetch(url: str, timeout: float, retries: int) -> tuple[bytes, str]:
    error = None
    for attempt in range(retries):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9"})
            with urlopen(request, timeout=timeout) as response:
                return response.read(), str(response.headers.get("Content-Type") or "")
        except Exception as exc:  # pragma: no cover - network failures vary by platform
            error = exc
            if attempt + 1 < retries:
                time.sleep(min(2**attempt, 4))
    raise RuntimeError(f"Failed to fetch {url} after {retries} attempts") from error


def decode_html(payload: bytes, content_type: str) -> str:
    match = re.search(r"charset=([\w-]+)", content_type, re.IGNORECASE)
    encodings = [match.group(1)] if match else []
    encodings.extend(["utf-8", "gb18030"])
    for encoding in dict.fromkeys(encodings):
        try:
            return payload.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return payload.decode("utf-8", errors="replace")


def canonical_url(value: str) -> str:
    parts = urlsplit(value.strip())
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    return urlunsplit(((parts.scheme or "https").lower(), parts.netloc.lower(), path, "", ""))


def identity_url(value: str) -> str:
    parts = urlsplit(canonical_url(value))
    port = parts.port
    authority = parts.hostname or ""
    if port and port not in {80, 443}:
        authority = f"{authority}:{port}"
    return f"{authority}{parts.path}"


def content_link_url(value: str) -> str:
    parts = urlsplit(value.strip())
    if parts.scheme.lower() not in {"http", "https"}:
        return ""
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def is_attachment_link(anchor, url: str) -> bool:
    if anchor.get("download") is not None:
        return True
    parts = urlsplit(url)
    candidates = [parts.path, *(value for _key, value in parse_qsl(parts.query, keep_blank_values=True))]
    return any(Path(urlsplit(unquote(value)).path).suffix.lower() in ATTACHMENT_EXTENSIONS for value in candidates)


def clean_text(value: object) -> str:
    normalized = str(value or "").replace("\u200b", "").replace("\ufeff", "")
    return SPACE_RE.sub(" ", normalized).strip()


def nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be at least 0")
    return parsed


def url_date_key(url: str) -> str:
    path = urlsplit(url).path
    match = re.search(r"/(20\d{2})/(\d{1,2})/(\d{1,2})/", path)
    if match:
        year, month, day = (int(value) for value in match.groups())
        return f"{year:04d}{month:02d}{day:02d}"
    match = re.search(r"/(20\d{4})/", path)
    return f"{match.group(1)}00" if match else ""


def discover(source: dict, timeout: float, retries: int, limit: int) -> list[dict]:
    payload, content_type = fetch(source["list_url"], timeout, retries)
    document = html.fromstring(decode_html(payload, content_type), base_url=source["list_url"])
    pattern = re.compile(source["link_pattern"])
    allowed_hosts = set(source["allowed_hosts"])
    found: dict[str, dict] = {}
    for anchor in document.xpath(source["link_xpath"]):
        href = anchor.get("href") if hasattr(anchor, "get") else ""
        url = canonical_url(urljoin(source["list_url"], str(href or "")))
        if source.get("force_https") and urlsplit(url).scheme == "http":
            parts = urlsplit(url)
            url = urlunsplit(("https", parts.netloc, parts.path, "", ""))
        if urlsplit(url).netloc not in allowed_hosts or not pattern.search(urlsplit(url).path):
            continue
        found.setdefault(url, {"url": url, "listedTitle": clean_text("".join(anchor.itertext()))})
    if not found:
        raise ValueError(f"Source {source['id']} yielded no article links")
    ordered = sorted(found.values(), key=lambda item: url_date_key(item["url"]), reverse=True)
    effective_limit = limit or int(source.get("max_items", 0))
    return ordered[:effective_limit] if effective_limit else ordered


def xpath_text(document, expressions: list[str]) -> str:
    for expression in expressions:
        values = document.xpath(expression)
        if not values:
            continue
        value = values[0]
        text = clean_text("".join(value.itertext())) if hasattr(value, "itertext") else clean_text(value)
        if text:
            return text
    return ""


def markdown_body(root, article_url: str, allowed_media_hosts: set[str]) -> tuple[str, list[tuple[str, str]], int, int]:
    blocks: list[str] = []
    source_text_length = 0
    media_count = 0
    for node in root.xpath(".//*[self::h2 or self::h3 or self::p or self::li or self::img]"):
        if node.tag == "img":
            src = str(node.get("src") or node.get("data-src") or "").strip()
            url = content_link_url(urljoin(article_url, src)) if src else ""
            if url and urlsplit(url).netloc in allowed_media_hosts:
                blocks.append(f"![{clean_text(node.get('alt'))}]({url})")
                media_count += 1
            continue
        text = clean_text("".join(node.itertext()))
        if not text:
            continue
        source_text_length += len(text)
        prefix = "## " if node.tag == "h2" else "### " if node.tag == "h3" else "- " if node.tag == "li" else ""
        blocks.append(prefix + text)
    links = []
    attachments = []
    for anchor in root.xpath(".//a[@href]"):
        url = content_link_url(urljoin(article_url, str(anchor.get("href") or "")))
        if not url:
            continue
        label = clean_text("".join(anchor.itertext())) or Path(urlsplit(url).path).name
        if is_attachment_link(anchor, url):
            attachments.append((label, url))
        else:
            links.append((label, url))
    blocks.extend(f"[{label}]({url})" for label, url in dict.fromkeys(links))
    attachments = list(dict.fromkeys(attachments))
    if attachments:
        blocks.extend([
            "## 原文附件",
            "> 附件文件不下载、不解析；请通过以下原页面提供的链接查看完整内容。",
            *(f"- [{label}]({url})" for label, url in attachments),
        ])
    return "\n\n".join(dict.fromkeys(blocks)), attachments, source_text_length, media_count


def article_note(source: dict, item: dict, timeout: float, retries: int) -> dict:
    payload, content_type = fetch(item["url"], timeout, retries)
    document = html.fromstring(decode_html(payload, content_type), base_url=item["url"])
    title = xpath_text(document, source["title_xpaths"]) or item["listedTitle"]
    for suffix in source.get("title_suffixes", []):
        suffix = clean_text(suffix)
        if title.endswith(suffix):
            title = title[: -len(suffix)].strip()
    body_root = next((nodes[0] for expression in source["body_xpaths"] if (nodes := document.xpath(expression))), None)
    body, attachments, source_text_length, media_count = (
        markdown_body(body_root, item["url"], set(source.get("allowed_media_hosts", source["allowed_hosts"])))
        if body_root is not None else ("", [], 0, 0)
    )
    image_only = bool(source.get("allow_image_only")) and media_count > 0
    if not title or (not attachments and not image_only and source_text_length < 80):
        raise ValueError(f"Incomplete article parse: {item['url']}")
    meta_name = source.get("date_meta")
    meta_date = document.xpath(f"string(//meta[@name='{meta_name}']/@content)") if meta_name else ""
    date_match = DATE_RE.search(str(meta_date)) or DATE_RE.search(item["url"]) or DATE_RE.search(clean_text("".join(document.itertext())))
    if not date_match:
        raise ValueError(f"Missing publication date: {item['url']}")
    body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    issuer = xpath_text(document, source.get("issuer_xpaths", [])) or source["issuer"]
    document_no = xpath_text(document, source.get("document_no_xpaths", []))
    document_no = document_no or clean_text((DOC_NO_RE.search(f"{title} {body}") or [""])[0])
    parts = {key: int(value) for key, value in date_match.groupdict().items()}
    return {
        "dateYear": parts["year"], "dateMonth": parts["month"], "dateDay": parts["day"],
        "headline": title, "era": source["group"], "bodyMarkdown": body,
        "tags": [source["group"], source["name"]], "items": [],
        "extra": {"source_id": source["id"], "display_source": source["name"], "issuer": issuer,
                  "document_no": document_no, "source_url": item["url"], "content_hash": body_hash},
    }


def identity_keys(note: dict) -> set[str]:
    extra = note.get("extra") if isinstance(note.get("extra"), dict) else {}
    issuer = re.sub(r"\s+", "", clean_text(extra.get("issuer"))).lower()
    title = re.sub(r"\s+", "", clean_text(note.get("headline"))).lower()
    date = f"{note.get('dateYear')}-{note.get('dateMonth')}-{note.get('dateDay')}"
    keys = {f"fallback:{issuer}:{date}:{title}"}
    if extra.get("document_no"):
        document_no = re.sub(r"\s+", "", str(extra["document_no"])).lower()
        keys.add(f"doc:{issuer}:{document_no}")
        keys.add(f"doc-title:{document_no}:{title}")
    if extra.get("source_url"):
        keys.add("url:" + identity_url(str(extra["source_url"])))
    if extra.get("content_hash"):
        keys.add("hash:" + str(extra["content_hash"]))
    return keys


def deduplicate(batches: list[dict], existing: list[dict]) -> tuple[list[dict], dict]:
    seen = set().union(*(identity_keys(note) for note in existing)) if existing else set()
    accepted, duplicates = [], 0
    for batch in batches:
        notes = []
        for note in batch["notes"]:
            keys = identity_keys(note)
            if keys & seen:
                duplicates += 1
                continue
            seen.update(keys)
            notes.append(note)
        accepted.append({**batch, "notes": notes})
    return accepted, {"candidates": sum(len(batch["notes"]) for batch in batches), "added": sum(len(batch["notes"]) for batch in accepted), "duplicates": duplicates}


def existing_political_notes(client: ApiClient, tree: list[dict], shelf_names: set[str]) -> list[dict]:
    notes = []
    for shelf in tree:
        if shelf.get("name") not in shelf_names:
            continue
        for item in shelf.get("topics", []):
            topic = item["topic"]
            exported = client.request("GET", f"/api/topics/{int(topic['id'])}/export")
            notes.extend(exported.get("notes", exported.get("events", [])))
    return notes


def validate_topic_targets(tree: list[dict], batches: list[dict]) -> None:
    existing = {
        item["topic"]["name"]: shelf["name"]
        for shelf in tree
        for item in shelf.get("topics", [])
    }
    requested: dict[str, str] = {}
    for batch in batches:
        notebook = batch["notebook"]
        shelf_name = batch["bookshelf"]["name"]
        if notebook in existing and existing[notebook] != shelf_name:
            raise ValueError(f"Notebook {notebook!r} exists outside bookshelf {shelf_name!r}")
        if notebook in requested and requested[notebook] != shelf_name:
            raise ValueError(f"Notebook {notebook!r} maps to multiple bookshelves")
        requested[notebook] = shelf_name


def apply_batches(client: ApiClient, tree: list[dict], batches: list[dict]) -> dict:
    shelves = {shelf["name"]: shelf for shelf in tree}
    topics = {
        (shelf["name"], item["topic"]["name"]): item["topic"]
        for shelf in tree
        for item in shelf.get("topics", [])
    }
    result = {"createdBookshelves": 0, "createdNotebooks": 0, "added": 0}
    for batch in batches:
        shelf_spec = batch["bookshelf"]
        shelf = shelves.get(shelf_spec["name"])
        if shelf is None:
            shelf = client.request("POST", "/api/bookshelves", shelf_spec)
            shelf["topics"] = []
            shelves[shelf["name"]] = shelf
            result["createdBookshelves"] += 1
        topic_key = (shelf_spec["name"], batch["notebook"])
        topic = topics.get(topic_key)
        if topic is None:
            topic = client.request("POST", "/api/topics", {"name": batch["notebook"], "bookshelfId": int(shelf["id"])})
            topics[topic_key] = topic
            result["createdNotebooks"] += 1
        meta = client.request("GET", f"/api/topics/{int(topic['id'])}/meta")
        current = meta.get("columns", [])
        current_keys = {column.get("key") for column in current}
        additions = [column for column in EXTRA_COLUMNS if column["key"] not in current_keys]
        if additions:
            client.request("PUT", f"/api/topics/{int(topic['id'])}/meta", {"columns": [*current, *additions]})
        for note in batch["notes"]:
            client.request("POST", f"/api/topics/{int(topic['id'])}/notes", note)
            result["added"] += 1
    return result


def backup_database(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.unlink(missing_ok=True)
    try:
        with closing(sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)) as source_db:
            with closing(sqlite3.connect(temporary)) as backup_db:
                source_db.backup(backup_db)
        with closing(sqlite3.connect(f"file:{temporary.as_posix()}?mode=ro", uri=True)) as backup_db:
            if backup_db.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise RuntimeError("SQLite backup integrity check failed")
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


@contextmanager
def exclusive_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt
            if handle.tell() == 0:
                handle.write(b"0"); handle.flush()
            handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        handle.close()


def manifest_checksum(manifest: dict) -> str:
    payload = {key: value for key, value in manifest.items() if key != "checksum"}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def write_manifest(path: Path, manifest: dict) -> None:
    manifest["checksum"] = manifest_checksum(manifest)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def source_contract(source: dict) -> dict:
    encoded = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "id": source["id"], "enabled": bool(source.get("enabled")), "bookshelf": source["bookshelf"],
        "notebook": source["notebook"], "group": source["group"],
        "configHash": hashlib.sha256(encoded).hexdigest(),
    }


def validate_manifest_registry(manifest: dict, registry: dict) -> None:
    current = {source["id"]: source_contract(source) for source in registry["sources"]}
    recorded = {source["id"]: source for source in manifest.get("registry", [])}
    for batch in manifest.get("batches", []):
        source_id = batch.get("source")
        expected = current.get(source_id)
        if expected is None or not expected["enabled"] or recorded.get(source_id) != expected:
            raise ValueError(f"Manifest source contract is no longer valid: {source_id!r}")
        if batch.get("bookshelf") != expected["bookshelf"] or batch.get("notebook") != expected["notebook"]:
            raise ValueError(f"Manifest target mapping does not match the registry: {source_id!r}")
        if any(note.get("era") != expected["group"] for note in batch.get("notes", [])):
            raise ValueError(f"Manifest group mapping does not match the registry: {source_id!r}")


def run_workflow(args, sources: list[dict], all_shelf_names: set[str]) -> dict:
    state_dir = Path(args.state_dir).resolve()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output_dir = state_dir / "runs" / stamp
    output_dir.mkdir(parents=True, exist_ok=False)
    batches, errors = [], []
    for source in sources:
        notes = []
        try:
            for item in discover(source, args.timeout, args.retries, args.limit):
                notes.append(article_note(source, item, args.timeout, args.retries))
        except Exception as exc:
            errors.append({"source": source["id"], "error": str(exc)})
        batches.append({"source": source["id"], "bookshelf": source["bookshelf"], "notebook": source["notebook"], "notes": notes})
    manifest_path = output_dir / "manifest.json"
    manifest = {
        "schemaVersion": 1,
        "createdAt": datetime.now().astimezone().isoformat(),
        "registry": [source_contract(source) for source in sources],
        "errors": errors,
        "batches": batches,
    }
    if errors:
        write_manifest(manifest_path, manifest)
        raise RuntimeError(f"Crawl failed; inspect {manifest_path}")
    client = ApiClient(args.base_url, args.timeout)
    tree = client.request("GET", "/api/bookshelves/tree")
    validate_topic_targets(tree, batches)
    planned, plan = deduplicate(batches, existing_political_notes(client, tree, all_shelf_names))
    manifest["batches"] = planned
    manifest["plan"] = plan
    write_manifest(manifest_path, manifest)
    return {"outputDir": str(output_dir), "manifest": str(manifest_path), "dryRun": True, "plan": plan}


def validate_apply_target(base_url: str, database: Path) -> None:
    if urlsplit(base_url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Apply only supports a loopback Chronicle API; run the command on the target host")
    if database.resolve() != (ROOT / "data" / "timeline.db").resolve():
        raise ValueError("Apply database must be this Chronicle checkout's data/timeline.db")


def local_database_identity(database: Path) -> str:
    return hashlib.sha256(str(database.resolve()).encode("utf-8")).hexdigest()


def apply_manifest(args, registry: dict) -> dict:
    manifest_path = Path(args.manifest).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("checksum") != manifest_checksum(manifest):
        raise ValueError("Manifest checksum mismatch")
    if manifest.get("errors"):
        raise ValueError("Refusing to apply a manifest with crawl errors")
    batches = manifest.get("batches")
    if manifest.get("schemaVersion") != 1 or not isinstance(batches, list):
        raise ValueError("Unsupported political ingestion manifest")
    validate_manifest_registry(manifest, registry)
    database = Path(args.database).resolve()
    validate_apply_target(args.base_url, database)
    client = ApiClient(args.base_url, args.timeout)
    runtime = client.request("GET", "/api/runtime/identity")
    if runtime.get("databaseIdentity") != local_database_identity(database):
        raise ValueError("Chronicle API is connected to a different database")
    tree = client.request("GET", "/api/bookshelves/tree")
    validate_topic_targets(tree, batches)
    shelf_names = {source["bookshelf"]["name"] for source in registry["sources"]}
    planned, plan = deduplicate(batches, existing_political_notes(client, tree, shelf_names))
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    result = {"manifest": str(manifest_path), "plan": plan, "backup": None, "sync": None, "status": "complete"}
    result_path = manifest_path.with_name("apply-result.json")
    try:
        if plan["added"]:
            backup_path = Path(args.backup_dir).expanduser().resolve() / f"timeline_db_prepolitics_{stamp}.db"
            backup_database(database, backup_path)
            result["backup"] = str(backup_path)
            result["sync"] = apply_batches(client, tree, planned)
    except BaseException as exc:
        result.update({"status": "failed", "error": str(exc)})
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        raise
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit, crawl, deduplicate and import official political sources.")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("sources")
    for command in ("audit", "run"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--source", action="append", default=[])
        sub.add_argument("--set", dest="set_name")
        sub.add_argument("--timeout", type=float, default=20.0)
        sub.add_argument("--retries", type=int, default=3)
        sub.add_argument("--limit", type=nonnegative_int, default=0)
        if command == "run":
            sub.add_argument("--base-url", default="http://127.0.0.1")
            sub.add_argument("--state-dir", default=str(ROOT / "data" / "political-ingestion"))
    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("--manifest", required=True)
    apply_parser.add_argument("--base-url", default="http://127.0.0.1")
    apply_parser.add_argument("--database", default=str(ROOT / "data" / "timeline.db"))
    apply_parser.add_argument("--backup-dir", default=str(Path.home() / "timeline_backups"))
    apply_parser.add_argument("--timeout", type=float, default=20.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry = load_registry(Path(args.registry))
    if args.command == "sources":
        print(json.dumps(registry, ensure_ascii=False, indent=2))
        return 0
    if args.command == "apply":
        lock_path = Path(args.database).resolve().with_suffix(".political-ingestion.lock")
        with exclusive_lock(lock_path):
            result = apply_manifest(args, registry)
    else:
        sources = selected_sources(registry, args.source, args.set_name)
    if args.command == "audit":
        result = [{"source": source["id"], "links": len(discover(source, args.timeout, args.retries, args.limit))} for source in sources]
    elif args.command == "run":
        all_shelf_names = {source["bookshelf"]["name"] for source in registry["sources"]}
        result = run_workflow(args, sources, all_shelf_names)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
