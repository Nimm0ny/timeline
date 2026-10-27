from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


SOURCE_CONFIG = {
    "web": {"bookshelf": "qstheory_web", "topic_pattern": re.compile(r"^(要闻资讯|理论|经济|政治|文化|社会|党建|科教|生态|国防|国际|图书)$")},
    "magazine": {"bookshelf": "qstheory_magazine", "topic_pattern": re.compile(r"^\d{4}年第\d+期$")},
}


@dataclass(frozen=True)
class SyncPlan:
    notes: list[dict]
    candidate_count: int
    duplicate_candidates: int
    existing_matches: int


class ApiClient:
    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(self, method: str, path: str, payload: dict | None = None):
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                content = response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} failed with HTTP {exc.code}: {detail}") from exc
        return json.loads(content.decode("utf-8")) if content else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Incrementally append qstheory crawl output to Chronicle.")
    parser.add_argument("--source", choices=tuple(SOURCE_CONFIG), required=True)
    parser.add_argument("--input-dir", required=True, help="Directory containing scraper manifest.json and topic JSON files.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Chronicle API base URL.")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--dry-run", action="store_true", help="Plan changes without creating notebooks or notes.")
    parser.add_argument("--lock-file", help="Required for writes; prevents overlapping sync processes.")
    return parser.parse_args()


def canonical_source_url(value: object) -> str:
    parts = urlsplit(str(value or "").strip())
    if not parts.netloc:
        return ""
    netloc = parts.netloc.lower()
    if netloc == "qstheory.cn":
        netloc = "www.qstheory.cn"
    path = parts.path or "/"
    scheme = "https" if netloc in {"qstheory.cn", "www.qstheory.cn"} else (parts.scheme.lower() or "https")
    return urlunsplit((scheme, netloc, path, "", ""))


def note_identity(note: dict) -> tuple[str, str]:
    extra = note.get("extra") if isinstance(note.get("extra"), dict) else {}
    source_url = canonical_source_url(extra.get("source_url"))
    parts = note.get("dateParts") if isinstance(note.get("dateParts"), dict) else {}
    year = note.get("dateYear", parts.get("year", ""))
    month = note.get("dateMonth", parts.get("month", ""))
    day = note.get("dateDay", parts.get("day", ""))
    headline = re.sub(r"\s+", "", str(note.get("headline") or "")).lower()
    if not headline:
        raise ValueError("Every qstheory note requires a headline")
    return (f"url:{source_url}" if source_url else "", f"fallback:{year}-{month}-{day}:{headline}")


def build_sync_plan(candidates: list[dict], existing: list[dict]) -> SyncPlan:
    existing_identities = [note_identity(note) for note in existing]
    existing_urls = {url_key for url_key, _ in existing_identities if url_key}
    existing_fallbacks = {fallback for _, fallback in existing_identities}
    existing_no_url_fallbacks = {fallback for url_key, fallback in existing_identities if not url_key}
    candidate_urls: set[str] = set()
    candidate_fallbacks: set[str] = set()
    candidate_no_url_fallbacks: set[str] = set()
    new_notes: list[dict] = []
    duplicate_candidates = 0
    existing_matches = 0
    for note in candidates:
        url_key, fallback = note_identity(note)
        is_duplicate = (url_key and (url_key in candidate_urls or fallback in candidate_no_url_fallbacks)) or (
            not url_key and fallback in candidate_fallbacks
        )
        if is_duplicate:
            duplicate_candidates += 1
            continue
        if url_key:
            candidate_urls.add(url_key)
        else:
            candidate_no_url_fallbacks.add(fallback)
        candidate_fallbacks.add(fallback)
        exists = (url_key and (url_key in existing_urls or fallback in existing_no_url_fallbacks)) or (
            not url_key and fallback in existing_fallbacks
        )
        if exists:
            existing_matches += 1
            continue
        new_notes.append(note)
    return SyncPlan(new_notes, len(candidates), duplicate_candidates, existing_matches)


def load_batches(input_dir: Path, source: str) -> list[tuple[str, dict]]:
    input_root = input_dir.resolve()
    manifest_path = input_root / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"Missing manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_source = str(manifest.get("source") or "all")
    if manifest_source not in {source, "all"}:
        raise ValueError(f"Manifest source {manifest_source!r} does not match {source!r}")
    if manifest.get("errors"):
        raise ValueError("Refusing to sync a manifest that contains crawl errors")
    pattern = SOURCE_CONFIG[source]["topic_pattern"]
    batches: list[tuple[str, dict]] = []
    seen_topics: set[str] = set()
    seen_paths: set[Path] = set()
    for item in manifest.get("topics", []):
        topic = str(item.get("topic") or "").strip()
        if not pattern.fullmatch(topic):
            continue
        raw_file = str(item.get("file") or "").strip()
        relative_path = Path(raw_file)
        path = (input_root / relative_path).resolve()
        if (
            not raw_file
            or relative_path.is_absolute()
            or path.suffix.lower() != ".json"
            or not path.is_relative_to(input_root)
            or not path.is_file()
        ):
            raise ValueError(f"Invalid topic file path: {raw_file!r}")
        if topic in seen_topics or path in seen_paths:
            raise ValueError(f"Duplicate topic or file mapping in manifest: {topic!r}")
        seen_topics.add(topic)
        seen_paths.add(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        notes = payload.get("notes", payload.get("events"))
        if not isinstance(notes, list):
            raise ValueError(f"{path} must contain notes or events")
        batches.append((topic, {**payload, "notes": notes}))
    if not batches:
        raise ValueError(f"No {source} topic payloads found in {manifest_path}")
    return batches


def bookshelf_context(tree: list[dict], source: str) -> tuple[dict, dict[str, dict], dict[str, dict]]:
    shelf_name = SOURCE_CONFIG[source]["bookshelf"]
    shelf = next((item for item in tree if item.get("name") == shelf_name), None)
    if shelf is None:
        raise ValueError(f"Required bookshelf {shelf_name!r} does not exist")
    target_topics = {item["topic"]["name"]: item["topic"] for item in shelf.get("topics", [])}
    all_topics = {
        item["topic"]["name"]: item["topic"]
        for bookshelf in tree
        for item in bookshelf.get("topics", [])
    }
    return shelf, target_topics, all_topics


def missing_columns(current: list[dict], required: list[dict]) -> list[dict]:
    current_keys = {str(column.get("key") or "") for column in current if isinstance(column, dict)}
    return [column for column in required if isinstance(column, dict) and column.get("key") not in current_keys]


def ensure_topic_columns(client: ApiClient, topic_id: int, required: list[dict]) -> None:
    meta = client.request("GET", f"/api/topics/{topic_id}/meta")
    current = meta.get("columns", [])
    additions = missing_columns(current, required)
    if additions:
        client.request("PUT", f"/api/topics/{topic_id}/meta", {"columns": [*current, *additions]})


def sync_batches(client: ApiClient, batches: list[tuple[str, dict]], source: str, *, dry_run: bool) -> dict:
    shelf, target_topics, all_topics = bookshelf_context(client.request("GET", "/api/bookshelves/tree"), source)
    result = {"source": source, "dryRun": dry_run, "topics": 0, "createdTopics": 0, "candidates": 0, "added": 0, "skippedExisting": 0, "skippedDuplicateCandidates": 0}
    for topic_name, payload in batches:
        topic = target_topics.get(topic_name)
        if topic is None and topic_name in all_topics:
            raise ValueError(f"Topic {topic_name!r} exists outside bookshelf {shelf['name']!r}")
        existing = []
        if topic is not None:
            exported = client.request("GET", f"/api/topics/{int(topic['id'])}/export")
            existing = exported.get("notes", exported.get("events", []))
        plan = build_sync_plan(payload["notes"], existing)
        result["topics"] += 1
        result["candidates"] += plan.candidate_count
        result["skippedExisting"] += plan.existing_matches
        result["skippedDuplicateCandidates"] += plan.duplicate_candidates
        if dry_run:
            result["added"] += len(plan.notes)
            continue
        if topic is None:
            topic = client.request("POST", "/api/topics", {"name": topic_name, "bookshelfId": int(shelf["id"])})
            target_topics[topic_name] = topic
            result["createdTopics"] += 1
        ensure_topic_columns(client, int(topic["id"]), payload.get("columns", []))
        for note in plan.notes:
            client.request("POST", f"/api/topics/{int(topic['id'])}/notes", note)
            result["added"] += 1
    return result


@contextmanager
def exclusive_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt

            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        raise RuntimeError(f"Another qstheory sync holds {path}") from exc
    try:
        yield
    finally:
        handle.close()


def main() -> int:
    args = parse_args()
    batches = load_batches(Path(args.input_dir), args.source)
    client = ApiClient(args.base_url, args.timeout)
    if args.dry_run:
        result = sync_batches(client, batches, args.source, dry_run=True)
    else:
        if not args.lock_file:
            raise ValueError("--lock-file is required for a write sync")
        with exclusive_lock(Path(args.lock_file)):
            result = sync_batches(client, batches, args.source, dry_run=False)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
