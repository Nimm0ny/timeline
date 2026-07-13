from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import shutil
import time

if __package__:
    from tools.political_ingestion import cli
else:
    from political_ingestion import cli


def wait_for_api(base_url: str, timeout: float, delay: float) -> None:
    client = cli.ApiClient(base_url, min(2.0, timeout))
    deadline = time.monotonic() + timeout
    error = None
    while time.monotonic() < deadline:
        try:
            client.request("GET", "/api/bookshelves/tree")
            return
        except Exception as exc:  # pragma: no cover - service timing is environment-dependent
            error = exc
            time.sleep(min(delay, max(0.0, deadline - time.monotonic())))
    raise RuntimeError(f"Chronicle API was not ready within {timeout:g} seconds") from error


def prune_runs(run_root: Path, keep: int) -> None:
    if not run_root.is_dir():
        return
    for path in sorted(run_root.iterdir(), key=lambda item: item.name, reverse=True)[keep:]:
        if path.is_dir():
            shutil.rmtree(path)


def prune_backups(backup_dir: Path, keep: int) -> None:
    if not backup_dir.is_dir():
        return
    backups = sorted(backup_dir.glob("timeline_db_prepolitics_*.db"), key=lambda item: item.name, reverse=True)
    for path in backups[keep:]:
        path.unlink()


def run_cycle(args: argparse.Namespace) -> dict:
    registry_path = Path(args.registry).resolve()
    registry = cli.load_registry(registry_path)
    sources = cli.selected_sources(registry, [], args.set_name)
    state_dir = Path(args.state_dir).resolve()
    database = Path(args.database).resolve()
    run_args = argparse.Namespace(
        state_dir=str(state_dir), base_url=args.base_url, timeout=args.timeout,
        retries=args.retries, limit=args.limit,
    )
    with cli.exclusive_lock(state_dir / "scheduled.lock"):
        cycle_error = None
        try:
            wait_for_api(args.base_url, args.ready_timeout, args.ready_delay)
            result = cli.run_workflow(
                run_args,
                sources,
                {source["bookshelf"]["name"] for source in registry["sources"]},
            )
            apply_result = None
            if not args.dry_run:
                apply_args = argparse.Namespace(
                    manifest=result["manifest"], base_url=args.base_url, database=str(database),
                    backup_dir=args.backup_dir, timeout=args.timeout,
                )
                with cli.exclusive_lock(database.with_suffix(".political-ingestion.lock")):
                    apply_result = cli.apply_manifest(apply_args, registry)
            return {"set": args.set_name, **result, "apply": apply_result}
        except BaseException as exc:
            cycle_error = exc
            raise
        finally:
            try:
                prune_runs(state_dir / "runs", args.keep_runs)
                if not args.dry_run:
                    prune_backups(Path(args.backup_dir).expanduser().resolve(), args.keep_backups)
            except Exception:
                if cycle_error is None:
                    raise


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
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Run one locked political document crawl and sync cycle.")
    parser.add_argument("--set", dest="set_name", default="weekly")
    parser.add_argument("--registry", default=str(cli.DEFAULT_REGISTRY))
    parser.add_argument("--base-url", default="http://127.0.0.1")
    parser.add_argument("--database", default=str(root / "data" / "timeline.db"))
    parser.add_argument("--state-dir", default=str(root / "data" / "political-ingestion"))
    parser.add_argument("--backup-dir", default=str(Path.home() / "timeline_backups"))
    parser.add_argument("--timeout", type=positive_float, default=20.0)
    parser.add_argument("--retries", type=positive_int, default=3)
    parser.add_argument("--limit", type=cli.nonnegative_int, default=0)
    parser.add_argument("--keep-runs", type=positive_int, default=8)
    parser.add_argument("--keep-backups", type=positive_int, default=16)
    parser.add_argument("--ready-timeout", type=positive_float, default=120.0)
    parser.add_argument("--ready-delay", type=positive_float, default=2.0)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    result = run_cycle(parse_args())
    result["completedAt"] = datetime.now().astimezone().isoformat()
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
