from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time

if __package__:
    from tools.qstheory_sync import ApiClient, exclusive_lock, load_batches, sync_batches
else:
    from qstheory_sync import ApiClient, exclusive_lock, load_batches, sync_batches


SOURCE_CRAWL_ARGS = {
    "web": ["--source", "web", "--strict"],
    "magazine": ["--source", "magazine", "--latest-issue", "--strict"],
}


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than 0")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one locked, backed-up qstheory crawl and sync cycle.")
    parser.add_argument("--source", choices=tuple(SOURCE_CRAWL_ARGS), required=True)
    parser.add_argument("--app-dir", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--base-url", default="http://127.0.0.1")
    parser.add_argument("--state-dir", help="Override data/qstheory-sync for isolated verification.")
    parser.add_argument("--backup-dir", default=str(Path.home() / "timeline_backups"))
    parser.add_argument("--keep-backups", type=positive_int, default=16)
    parser.add_argument("--keep-runs", type=positive_int, default=5)
    parser.add_argument("--ready-timeout", type=positive_float, default=120.0)
    parser.add_argument("--ready-delay", type=positive_float, default=2.0)
    parser.add_argument("--dry-run", action="store_true", help="Crawl and plan without backup or API writes.")
    return parser.parse_args()


def backup_database(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"Timeline database does not exist: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.unlink(missing_ok=True)
    try:
        with closing(sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)) as source_db:
            with closing(sqlite3.connect(temporary)) as backup_db:
                source_db.backup(backup_db)
        with closing(sqlite3.connect(f"file:{temporary.as_posix()}?mode=ro", uri=True)) as backup_db:
            if backup_db.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise RuntimeError(f"SQLite backup integrity check failed: {temporary}")
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def prune_paths(paths: list[Path], keep: int) -> None:
    ordered = sorted(paths, key=lambda path: path.name, reverse=True)
    for path in ordered[max(0, keep) :]:
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()


def crawl_command(app_dir: Path, source: str, output_dir: Path) -> list[str]:
    return [
        sys.executable,
        str(app_dir / "tools" / "qstheory_batch_scraper.py"),
        *SOURCE_CRAWL_ARGS[source],
        "--output-dir",
        str(output_dir),
    ]


def wait_for_api(
    client: ApiClient,
    total_timeout: float,
    delay: float,
    *,
    clock=time.monotonic,
    sleeper=time.sleep,
) -> None:
    deadline = clock() + total_timeout
    error = None
    original_timeout = client.timeout
    try:
        while True:
            remaining = deadline - clock()
            if remaining <= 0:
                break
            client.timeout = min(2.0, remaining)
            try:
                client.request("GET", "/api/bookshelves/tree")
                return
            except Exception as exc:  # pragma: no cover - depends on service startup timing
                error = exc
                remaining = deadline - clock()
                if remaining > 0:
                    sleeper(min(delay, remaining))
        raise RuntimeError(f"Chronicle API was not ready within {total_timeout:g} seconds") from error
    finally:
        client.timeout = original_timeout


def run_cycle(args: argparse.Namespace) -> dict:
    app_dir = Path(args.app_dir).resolve()
    state_dir = Path(args.state_dir).resolve() if args.state_dir else app_dir / "data" / "qstheory-sync"
    run_root = state_dir / "runs" / args.source
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output_dir = run_root / stamp
    lock_path = state_dir / f"{args.source}.lock"
    backup_dir = Path(args.backup_dir).expanduser().resolve()
    database_path = app_dir / "data" / "timeline.db"

    with exclusive_lock(lock_path):
        output_dir.mkdir(parents=True, exist_ok=False)
        cycle_error = None
        try:
            client = ApiClient(args.base_url)
            wait_for_api(client, args.ready_timeout, args.ready_delay)
            subprocess.run(crawl_command(app_dir, args.source, output_dir), cwd=app_dir, check=True)
            batches = load_batches(output_dir, args.source)
            plan = sync_batches(client, batches, args.source, dry_run=True)
            backup_path = None
            if plan["added"] > 0 and not args.dry_run:
                backup_path = backup_dir / f"timeline_db_preqstheory_{args.source}_{stamp}.db"
                backup_database(database_path, backup_path)
                sync_result = sync_batches(client, batches, args.source, dry_run=False)
            else:
                sync_result = plan if args.dry_run else {**plan, "dryRun": False}
            if not args.dry_run:
                prune_paths(list(backup_dir.glob(f"timeline_db_preqstheory_{args.source}_*.db")), args.keep_backups)
            return {
                "source": args.source,
                "outputDir": str(output_dir),
                "backup": str(backup_path) if backup_path else None,
                "plan": plan,
                "sync": sync_result,
            }
        except BaseException as exc:
            cycle_error = exc
            raise
        finally:
            try:
                prune_paths(list(run_root.iterdir()), args.keep_runs)
            except Exception:
                if cycle_error is None:
                    raise


def main() -> int:
    result = run_cycle(parse_args())
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
