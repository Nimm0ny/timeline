from __future__ import annotations

import argparse
from collections import defaultdict
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from lxml import html

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
ARTICLE_PATH_RE = re.compile(r"(/\d{8}/[0-9a-f]+/c\.html|/c_\d+\.htm)$", re.IGNORECASE)
SPACE_RE = re.compile(r"\s+")
DEFAULT_TIMEOUT = 20.0
DEFAULT_RETRIES = 3
DEFAULT_DELAY = 0.2
DEFAULT_LIMIT = 0
DEFAULT_OUTPUT_DIR = "qstheory-topics"
DEFAULT_TOPIC_GROUPS = [
    (
        "要闻资讯",
        [
            ("要闻", "https://www.qstheory.cn/qsyw/index.htm"),
            ("资讯", "https://www.qstheory.cn/qsgdzx/index.htm"),
            ("求是动态", "https://www.qstheory.cn/dt/index.htm"),
        ],
    ),
    (
        "理论",
        [
            ("网评", "https://www.qstheory.cn/qswp.htm"),
            ("原创", "https://www.qstheory.cn/qslgxd/index.htm"),
            ("学习笔记", "https://www.qstheory.cn/qszq/xxbj/index.htm"),
            ("理论文选", "https://www.qstheory.cn/qszq/llwx/index.htm"),
            ("深度调研", "https://www.qstheory.cn/v9zhuanqu/zhuanqu/sddy/index.htm"),
            ("求是专访", "https://www.qstheory.cn/v9zhuanqu/zhuanqu/qszf/index.htm"),
            ("学习问答", "https://www.qstheory.cn/v9zhuanqu/zhuanqu/xxwd/index.htm"),
        ],
    ),
    ("经济", [("经济", "https://www.qstheory.cn/economy/index.htm")]),
    ("政治", [("政治", "https://www.qstheory.cn/politics/index.htm")]),
    ("文化", [("文化", "https://www.qstheory.cn/culture/index.htm")]),
    ("社会", [("社会", "https://www.qstheory.cn/society/index.htm")]),
    ("党建", [("党建", "https://www.qstheory.cn/cpc/index.htm")]),
    ("科教", [("科教", "https://www.qstheory.cn/science/index.htm")]),
    ("生态", [("生态", "https://www.qstheory.cn/zoology/index.htm")]),
    ("国防", [("国防", "https://www.qstheory.cn/defense/index.htm")]),
    ("国际", [("国际", "https://www.qstheory.cn/international/index.htm")]),
    ("图书", [("图书", "https://www.qstheory.cn/books/index.htm")]),
]
CHANNEL_ALIASES = {
    "求是网评论员": "网评",
}
EXTRA_COLUMNS = [
    {"key": "channel", "label": "栏目", "type": "text", "width": 110, "order": 0, "visible": True},
    {"key": "issue_label", "label": "期号", "type": "text", "width": 120, "order": 1, "visible": True},
    {"key": "subtitle", "label": "副题", "type": "text", "width": 200, "order": 2, "visible": True},
    {"key": "display_source", "label": "来源", "type": "text", "width": 140, "order": 3, "visible": True},
    {"key": "meta_source", "label": "站点来源", "type": "text", "width": 140, "order": 4, "visible": False},
    {"key": "author_name", "label": "作者", "type": "text", "width": 110, "order": 5, "visible": True},
    {"key": "publish_time", "label": "发布时间", "type": "text", "width": 140, "order": 6, "visible": True},
    {"key": "source_url", "label": "原文链接", "type": "url", "width": 220, "order": 7, "visible": True},
    {"key": "keywords", "label": "关键词", "type": "text", "width": 200, "order": 8, "visible": False},
]


class SkipArticle(RuntimeError):
    """Known upstream non-article pages (expired, redirect stubs, site-info links)."""


@dataclass(frozen=True)
class Seed:
    topic: str
    channel: str
    url: str
    mode: str = "page"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Crawl qstheory.cn and emit one timeline schemaVersion 2 JSON per topic group."
    )
    parser.add_argument(
        "--seed",
        action="append",
        default=[],
        help="Repeatable TOPIC/CHANNEL=URL seed. CHANNEL=URL also works and uses CHANNEL as topic.",
    )
    parser.add_argument("--topic", action="append", default=[], help="Only crawl the named default topic group.")
    parser.add_argument(
        "--magazine-year",
        action="append",
        default=[],
        help="Restrict 求是杂志 crawling to specific years like 2026. Repeatable.",
    )
    parser.add_argument("--subtitle", default="", help="Optional subtitle written to every generated topic JSON.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Directory for grouped topic JSON files.")
    parser.add_argument("--title-prefix", default="", help="Optional prefix added before each topic title.")
    parser.add_argument("--manifest-name", default="manifest.json", help="Manifest file name inside output dir.")
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help="Optional max exported article count per topic. 0 means no limit.",
    )
    parser.add_argument("--per-seed-limit", type=int, default=0, help="Optional max links per seed page.")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="Per-request timeout in seconds.")
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES, help="Per-request retry count.")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="Pause between requests in seconds.")
    parser.add_argument("--verbose", action="store_true", help="Print crawl progress.")
    return parser.parse_args()


def parse_seed_spec(spec: str) -> Seed:
    raw = str(spec or "").strip()
    if not raw:
        raise ValueError("Seed cannot be empty")
    if "=" not in raw:
        label = seed_label_from_url(raw)
        return Seed(topic=label, channel=label, url=canonical_url(raw))
    label, url = raw.split("=", 1)
    cleaned = clean_text(label)
    if "/" in cleaned:
        topic, channel = cleaned.split("/", 1)
    else:
        topic = cleaned or seed_label_from_url(url)
        channel = cleaned or seed_label_from_url(url)
    return Seed(topic=clean_text(topic), channel=clean_text(channel), url=canonical_url(url))


def seed_label_from_url(url: str) -> str:
    path = urlsplit(url).path.strip("/")
    if not path:
        return "求是网"
    stem = path.rsplit("/", 1)[-1].split(".", 1)[0]
    return stem or "求是网"


def canonical_url(url: str) -> str:
    parts = urlsplit(str(url or "").strip())
    scheme = "https" if parts.scheme in {"http", "https", ""} else parts.scheme
    netloc = parts.netloc or "www.qstheory.cn"
    if netloc == "qstheory.cn":
        netloc = "www.qstheory.cn"
    path = parts.path or "/"
    return urlunsplit((scheme, netloc, path, "", ""))


def clean_text(value: str) -> str:
    return SPACE_RE.sub(" ", str(value or "").replace("\xa0", " ")).strip()


def comparable_text(value: str) -> str:
    compact = clean_text(value).replace("※", "")
    return SPACE_RE.sub("", compact).lower()


def fetch_bytes(url: str, *, timeout: float, retries: int, delay: float, verbose: bool) -> bytes:
    error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            request = Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept-Language": "zh-CN,zh;q=0.9",
                },
            )
            with urlopen(request, timeout=timeout) as response:
                payload = response.read()
            if delay > 0:
                time.sleep(delay)
            return payload
        except Exception as exc:  # pragma: no cover - network variance
            error = exc
            if verbose:
                print(f"[retry {attempt}/{retries}] {url} -> {exc}", file=sys.stderr)
            if attempt < retries and delay > 0:
                time.sleep(delay)
    raise RuntimeError(f"Failed to fetch {url}: {error}") from error


def parse_html(payload: bytes):
    return html.fromstring(payload)


def is_article_url(url: str) -> bool:
    parts = urlsplit(url)
    if parts.netloc not in {"www.qstheory.cn", "qstheory.cn"}:
        return False
    return bool(ARTICLE_PATH_RE.search(parts.path))


def article_url_from_href(base_url: str, href: str) -> str | None:
    raw = str(href or "").strip()
    if not raw or raw.startswith(("javascript:", "mailto:", "#")):
        return None
    absolute = canonical_url(urljoin(base_url, raw))
    return absolute if is_article_url(absolute) else None


def extract_article_links(seed: Seed, document, *, per_seed_limit: int) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    seen: set[str] = set()
    for node in document.xpath("//a[@href]"):
        href = node.get("href")
        article_url = article_url_from_href(seed.url, href)
        if article_url is None or article_url in seen:
            continue
        label = clean_text("".join(node.xpath(".//text()")))
        links.append((article_url, label))
        seen.add(article_url)
        if per_seed_limit > 0 and len(links) >= per_seed_limit:
            break
    return links


def meta_content(document, name: str) -> str:
    values = document.xpath(f'//meta[@name="{name}"]/@content')
    return clean_text(values[0]) if values else ""


def parse_header_spans(document) -> tuple[str, str, str]:
    display_source = ""
    author_name = ""
    publish_time = ""
    for text in document.xpath('//div[contains(@class,"inner")][1]/span//text()'):
        entry = clean_text(text)
        if entry.startswith("来源："):
            display_source = entry.removeprefix("来源：").strip()
        elif entry.startswith("作者："):
            author_name = entry.removeprefix("作者：").strip()
        elif re.match(r"\d{4}-\d{2}-\d{2}", entry):
            publish_time = entry
    return display_source, author_name, publish_time


def detail_root(document):
    nodes = document.xpath('//div[@id="detailContent"]')
    if nodes:
        return nodes[0]
    fallbacks = document.xpath('//div[contains(@class,"text")]')
    return fallbacks[0] if fallbacks else None


def should_skip_article_page(article_url: str, document) -> bool:
    title = clean_text("".join(document.xpath("//title//text()")))
    body = clean_text(" ".join(document.xpath("//body//text()")))
    if "已删除或过期的稿件" in title or "已删除或过期的稿件" in body:
        return True
    if title == "找不到页面了" or "秒之后将返回首页" in body:
        return True
    refresh = " ".join(document.xpath("//meta[@http-equiv='refresh' or @http-equiv='Refresh']/@content"))
    if "url=http://www.qstheory.cn" in refresh or "url=https://www.qstheory.cn" in refresh:
        return True
    if title == "求是网" and not clean_text("".join(document.xpath("//h1//text()"))) and not detail_root(document):
        return True
    if "/qssyggw/" in urlsplit(article_url).path:
        return True
    return False


def filtered_image_urls(node, article_url: str) -> list[str]:
    results: list[str] = []
    for src in node.xpath(".//img/@src"):
        name = src.rsplit("/", 1)[-1]
        if not src or name.startswith("zxcode_"):
            continue
        results.append(urljoin(article_url, src))
    return results


def paragraph_markdown(node, article_url: str, skip: set[str]) -> list[str]:
    blocks: list[str] = []
    images = filtered_image_urls(node, article_url)
    text = clean_text("".join(node.xpath(".//text()")))
    marker = comparable_text(text)
    if images:
        for image_url in images:
            blocks.append(f"![图片]({image_url})")
        if text and marker not in skip:
            blocks.append(text)
        return blocks
    if text and marker not in skip:
        blocks.append(text)
    return blocks


def body_markdown(document, article_url: str, *, title: str, subtitle: str, author_name: str) -> str:
    root = detail_root(document)
    if root is None:
        return subtitle or ""
    skip = {value for value in map(comparable_text, [title, subtitle, author_name]) if value}
    blocks: list[str] = [subtitle] if subtitle else []
    for node in root.xpath(".//p | .//h3 | .//h4 | .//li"):
        blocks.extend(paragraph_markdown(node, article_url, skip))
    compact: list[str] = []
    for block in blocks:
        if block and (not compact or compact[-1] != block):
            compact.append(block)
    return "\n\n".join(compact).strip()


def publish_parts(publish_date: str, publish_time: str) -> tuple[int, int, int]:
    source = publish_time[:10] if publish_time else publish_date
    try:
        parsed = datetime.strptime(source, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"Unsupported publish date: {source}") from exc
    return parsed.year, parsed.month, parsed.day


def publish_parts_from_url(article_url: str) -> tuple[int, int, int] | None:
    path = urlsplit(article_url).path
    match = re.search(r"/(\d{8})/[0-9a-f]+/c\.html$", path, flags=re.IGNORECASE)
    if match:
        stamp = match.group(1)
        return int(stamp[:4]), int(stamp[4:6]), int(stamp[6:8])
    match = re.search(r"/(\d{4})-(\d{2})/(\d{2})/c_[0-9]+\.htm$", path, flags=re.IGNORECASE)
    if match:
        return int(match.group(1)), int(match.group(2)), int(match.group(3))
    return None


def infer_channel(title: str, fallback: str) -> str:
    text = clean_text(title)
    for separator in (" | ", " │ ", "│", "｜", "|"):
        if separator in text:
            prefix = clean_text(text.split(separator, 1)[0])
            if prefix:
                return CHANNEL_ALIASES.get(prefix, prefix)
    if text.startswith("求是网评论员："):
        return "网评"
    return fallback


def article_payload(seed: Seed, article_url: str, document, *, listed_title: str = "") -> dict:
    if should_skip_article_page(article_url, document):
        raise SkipArticle(f"Skip non-article page: {article_url}")
    title = clean_text("".join(document.xpath("//h1//text()")))
    subtitle = clean_text("".join(document.xpath("//h2//text()")))
    publish_date = meta_content(document, "publishdate")
    meta_source = meta_content(document, "source")
    keywords = meta_content(document, "keywords")
    display_source, author_name, publish_time = parse_header_spans(document)
    if not author_name:
        author_name = meta_content(document, "author")
    channel = infer_channel(title or listed_title, seed.channel)
    try:
        year, month, day = publish_parts(publish_date, publish_time)
    except ValueError:
        fallback = publish_parts_from_url(article_url)
        if fallback is None:
            raise
        year, month, day = fallback
    body = body_markdown(document, article_url, title=title, subtitle=subtitle, author_name=author_name)
    if not title or not body:
        raise ValueError(f"Incomplete article payload for {article_url}")
    extra = {
        "channel": channel,
        "subtitle": subtitle,
        "display_source": display_source,
        "meta_source": meta_source,
        "author_name": author_name,
        "publish_time": publish_time or publish_date,
        "source_url": article_url,
        "keywords": keywords,
    }
    return {
        "dateYear": year,
        "dateMonth": month,
        "dateDay": day,
        "headline": title,
        "era": channel,
        "bodyMarkdown": body,
        "extra": extra,
    }


def build_topic_payload(title: str, subtitle: str, events: Iterable[dict]) -> dict:
    ordered = sorted(
        events,
        key=lambda item: (
            item["dateYear"],
            item["dateMonth"],
            item["dateDay"],
            item["headline"],
        ),
    )
    return {
        "schemaVersion": 2,
        "title": title,
        "subtitle": subtitle,
        "columns": EXTRA_COLUMNS,
        "events": ordered,
    }


def write_output(path: str | Path, payload: dict) -> None:
    content = json.dumps(payload, ensure_ascii=False, indent=2)
    if str(path) == "-":
        print(content)
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content + "\n", encoding="utf-8")


def default_seeds() -> list[Seed]:
    seeds: list[Seed] = []
    for topic, channels in DEFAULT_TOPIC_GROUPS:
        for channel, url in channels:
            seeds.append(Seed(topic=topic, channel=channel, url=url))
    return seeds


def configured_seeds(raw_specs: list[str], topic_filters: list[str]) -> list[Seed]:
    if raw_specs:
        return [parse_seed_spec(spec) for spec in raw_specs]
    allowed = {clean_text(item) for item in topic_filters if clean_text(item)}
    seeds = default_seeds()
    if not allowed:
        return seeds
    return [seed for seed in seeds if seed.topic in allowed]


def topic_title(topic: str, title_prefix: str) -> str:
    return f"{title_prefix}{topic}" if title_prefix else topic


def safe_filename(name: str) -> str:
    text = clean_text(name)
    text = re.sub(r'[<>:"/\\|?*]', "_", text)
    return text or "topic"


def build_manifest(stats: dict, output_dir: Path, manifest_name: str) -> dict:
    topics = []
    for topic in stats["topicOrder"]:
        count = stats["eventCountByTopic"].get(topic, 0)
        if count <= 0:
            continue
        topics.append(
            {
                "topic": topic,
                "file": f"{safe_filename(topic)}.json",
                "count": count,
                "channels": sorted(stats["channelsByTopic"].get(topic, set())),
            }
        )
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "outputDir": str(output_dir),
        "manifest": manifest_name,
        "topics": topics,
        "errors": list(stats["errors"]),
    }


def retired_output_files(payloads: dict[str, dict]) -> set[str]:
    # Magazine exports used to aggregate every issue into one notebook file
    # named 求是杂志.json. The current model emits one file per issue, so we
    # retire only that known obsolete artifact instead of broadly deleting any
    # non-current JSON in the output directory.
    if any(re.fullmatch(r"\d{4}年第\d+期", topic) for topic in payloads):
        return {"求是杂志.json"}
    return set()


def write_batch_output(output_dir: Path, payloads: dict[str, dict], stats: dict, manifest_name: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    retired_files = retired_output_files(payloads)
    for path in output_dir.glob("*.json"):
        if path.name in retired_files:
            path.unlink()
    for topic, payload in payloads.items():
        write_output(output_dir / f"{safe_filename(topic)}.json", payload)
    write_output(output_dir / manifest_name, build_manifest(stats, output_dir, manifest_name))


def ordered_topics(seeds: list[Seed]) -> list[str]:
    topics: list[str] = []
    for seed in seeds:
        if seed.topic not in topics:
            topics.append(seed.topic)
    return topics


def should_crawl_magazine(raw_specs: list[str], topic_filters: list[str]) -> bool:
    if raw_specs:
        return False
    allowed = {clean_text(item) for item in topic_filters if clean_text(item)}
    return not allowed or "求是杂志" in allowed


def issue_year_filters(values: list[str]) -> set[str]:
    return {clean_text(value).removesuffix("年") for value in values if clean_text(value)}


def extract_qishi_year_links(document, archive_url: str, allowed_years: set[str]) -> list[tuple[str, str]]:
    years: list[tuple[str, str]] = []
    seen: set[str] = set()
    for node in document.xpath("//a[@href]"):
        text = clean_text("".join(node.xpath(".//text()")))
        if not re.fullmatch(r"\d{4}年", text):
            continue
        year = text[:-1]
        if allowed_years and year not in allowed_years:
            continue
        url = canonical_url(urljoin(archive_url, node.get("href", "").strip()))
        if url in seen:
            continue
        years.append((year, url))
        seen.add(url)
    return years


def extract_qishi_issue_links(document, year_page_url: str, year: str) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    seen: set[str] = set()
    pattern = re.compile(rf"《求是》{re.escape(year)}年第(\d+)期")
    for node in document.xpath("//a[@href]"):
        text = clean_text("".join(node.xpath(".//text()")))
        match = pattern.fullmatch(text)
        if not match:
            continue
        url = canonical_url(urljoin(year_page_url, node.get("href", "").strip()))
        if url in seen:
            continue
        issues.append((f"{year}年第{match.group(1)}期", url))
        seen.add(url)
    return issues


def extract_qishi_issue_article_links(issue_url: str, document) -> list[tuple[str, str]]:
    root = detail_root(document)
    if root is None:
        return []
    links: list[tuple[str, str]] = []
    seen: set[str] = set()
    blocked_labels = {"理论资源导航", "【网站声明】", "网站声明", "投稿《求是》", "求是网简介"}
    for node in root.xpath(".//a[@href]"):
        article_url = article_url_from_href(issue_url, node.get("href", "").strip())
        if article_url is None or article_url in seen:
            continue
        if "/qssyggw/" in urlsplit(article_url).path:
            continue
        label = clean_text("".join(node.xpath(".//text()")))
        if not label or label in blocked_labels:
            continue
        links.append((article_url, label))
        seen.add(article_url)
    return links


def qishi_issue_payload(issue_label: str, listed_title: str, article_url: str, document) -> dict:
    payload = article_payload(
        Seed(topic="求是杂志", channel="求是杂志", url=article_url),
        article_url,
        document,
        listed_title=listed_title,
    )
    payload["era"] = payload["headline"]
    payload["extra"]["issue_label"] = issue_label
    return payload


def crawl_qishi_magazine(args: argparse.Namespace) -> tuple[dict[str, dict], dict]:
    archive_url = "https://www.qstheory.cn/qs/mulu.htm"
    failures: list[str] = []
    issue_events: dict[str, list[dict]] = defaultdict(list)
    seen_by_issue: set[tuple[str, str]] = set()
    issue_channels: dict[str, set[str]] = defaultdict(set)
    year_filters = issue_year_filters(args.magazine_year)
    try:
        archive_doc = parse_html(
            fetch_bytes(
                archive_url,
                timeout=args.timeout,
                retries=args.retries,
                delay=args.delay,
                verbose=args.verbose,
            )
        )
    except Exception as exc:  # pragma: no cover - network variance
        failures.append(f"{archive_url} :: {exc}")
        return {}, {"errors": failures, "issueCount": 0, "articleCount": 0, "channelsByIssue": issue_channels}

    year_links = extract_qishi_year_links(archive_doc, archive_url, year_filters)
    issue_count = 0
    for year, year_url in year_links:
        try:
            year_doc = parse_html(
                fetch_bytes(
                    year_url,
                    timeout=args.timeout,
                    retries=args.retries,
                    delay=args.delay,
                    verbose=args.verbose,
                )
            )
        except Exception as exc:  # pragma: no cover - network variance
            failures.append(f"{year_url} :: {exc}")
            continue
        issue_links = extract_qishi_issue_links(year_doc, year_url, year)
        for issue_label, issue_url in issue_links:
            issue_count += 1
            try:
                issue_doc = parse_html(
                    fetch_bytes(
                        issue_url,
                        timeout=args.timeout,
                        retries=args.retries,
                        delay=args.delay,
                        verbose=args.verbose,
                    )
                )
            except Exception as exc:  # pragma: no cover - network variance
                failures.append(f"{issue_url} :: {exc}")
                continue
            issue_links = extract_qishi_issue_article_links(issue_url, issue_doc)
            if args.per_seed_limit > 0:
                issue_links = issue_links[: args.per_seed_limit]
            for article_url, listed_title in issue_links:
                key = (issue_label, article_url)
                if key in seen_by_issue:
                    continue
                seen_by_issue.add(key)
                try:
                    article_doc = parse_html(
                        fetch_bytes(
                            article_url,
                            timeout=args.timeout,
                            retries=args.retries,
                            delay=args.delay,
                            verbose=args.verbose,
                        )
                    )
                    payload = qishi_issue_payload(issue_label, listed_title, article_url, article_doc)
                    issue_events[issue_label].append(payload)
                    issue_channels[issue_label].add(payload["extra"]["channel"])
                except SkipArticle:
                    continue
                except HTTPError as exc:  # pragma: no cover - network variance
                    if exc.code == 404:
                        continue
                    failures.append(f"{article_url} :: {exc}")
                except Exception as exc:  # pragma: no cover - network variance
                    failures.append(f"{article_url} :: {exc}")
    if not issue_events:
        return {}, {"errors": failures, "issueCount": issue_count, "articleCount": 0, "channelsByIssue": issue_channels}
    payloads = {
        issue_label: build_topic_payload(issue_label, args.subtitle, events)
        for issue_label, events in issue_events.items()
        if events
    }
    return payloads, {
        "errors": failures,
        "issueCount": issue_count,
        "articleCount": sum(len(events) for events in issue_events.values()),
        "channelsByIssue": issue_channels,
    }


def crawl(args: argparse.Namespace) -> tuple[dict[str, dict], dict]:
    events_by_topic: dict[str, list[dict]] = defaultdict(list)
    event_count_by_topic: dict[str, int] = defaultdict(int)
    channels_by_topic: dict[str, set[str]] = defaultdict(set)
    memberships_by_url: dict[str, dict[str, tuple[Seed, str]]] = defaultdict(dict)
    failures: list[str] = []
    seeds = configured_seeds(args.seed, args.topic)
    for seed in seeds:
        if args.verbose:
            print(f"[seed] {seed.topic}/{seed.channel} <- {seed.url}", file=sys.stderr)
        try:
            index_doc = parse_html(
                fetch_bytes(
                    seed.url,
                    timeout=args.timeout,
                    retries=args.retries,
                    delay=args.delay,
                    verbose=args.verbose,
                )
            )
        except Exception as exc:  # pragma: no cover - network variance
            failures.append(f"{seed.url} :: {exc}")
            continue
        links = extract_article_links(seed, index_doc, per_seed_limit=args.per_seed_limit)
        if not links:
            failures.append(f"{seed.url} :: no article links matched on seed page")
            continue
        for article_url, listed_title in links:
            memberships_by_url[article_url].setdefault(seed.topic, (seed, listed_title))
    for article_url, memberships in memberships_by_url.items():
        try:
            document = parse_html(
                fetch_bytes(
                    article_url,
                    timeout=args.timeout,
                    retries=args.retries,
                    delay=args.delay,
                    verbose=args.verbose,
                )
            )
            for topic, (seed, listed_title) in memberships.items():
                if args.limit > 0 and event_count_by_topic[topic] >= args.limit:
                    continue
                payload = article_payload(seed, article_url, document, listed_title=listed_title)
                events_by_topic[topic].append(payload)
                event_count_by_topic[topic] += 1
                channels_by_topic[topic].add(payload["extra"]["channel"])
        except Exception as exc:  # pragma: no cover - network variance
            failures.append(f"{article_url} :: {exc}")
    payloads = {
        topic: build_topic_payload(topic_title(topic, args.title_prefix), args.subtitle, events)
        for topic, events in events_by_topic.items()
        if events
    }
    stats = {
        "seedCount": len(seeds),
        "linkCount": len(memberships_by_url),
        "errors": failures,
        "topicOrder": ordered_topics(seeds),
        "eventCountByTopic": dict(event_count_by_topic),
        "channelsByTopic": channels_by_topic,
    }
    if should_crawl_magazine(args.seed, args.topic):
        magazine_payloads, magazine_stats = crawl_qishi_magazine(args)
        stats["errors"].extend(magazine_stats["errors"])
        stats["linkCount"] += magazine_stats["articleCount"]
        for issue_label, payload in magazine_payloads.items():
            payloads[issue_label] = payload
            if issue_label not in stats["topicOrder"]:
                stats["topicOrder"].append(issue_label)
            stats["eventCountByTopic"][issue_label] = len(payload["events"])
            stats["channelsByTopic"][issue_label] = magazine_stats["channelsByIssue"].get(issue_label) or {"求是杂志"}
    return payloads, stats


def main() -> int:
    args = parse_args()
    payloads, stats = crawl(args)
    output_dir = Path(args.output_dir)
    write_batch_output(output_dir, payloads, stats, args.manifest_name)
    total_events = sum(len(payload["events"]) for payload in payloads.values())
    print(
        json.dumps(
            {
                "outputDir": str(output_dir),
                "topicFiles": len(payloads),
                "events": total_events,
                "discoveredLinks": stats["linkCount"],
                "seedCount": stats["seedCount"],
                "errors": len(stats["errors"]),
            },
            ensure_ascii=False,
        ),
        file=sys.stderr,
    )
    for item in stats["errors"]:
        print(f"[warn] {item}", file=sys.stderr)
    return 0 if total_events else 1


if __name__ == "__main__":
    raise SystemExit(main())
