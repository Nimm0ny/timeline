---
name: chronicle-political-ingestion
description: Audit, crawl, deduplicate, preview, and import official Chinese political documents into Chronicle. Use when asked to manage 党中央、国务院、人大、部委或省级政府信息源，抓取工作报告、政策文件、公告、意见征集和政策解读，检查来源健康状态，执行时政增量同步，或排查重复与抓取失败。
---

# Chronicle Political Ingestion

Use the repository workflow as the only implementation. Do not reproduce scraper logic inside the skill.

## Workflow

1. Read `AGENTS.md` and `docs/political-ingestion-workflow.md`.
2. Inspect the registry with `python -m tools.political_ingestion.cli sources`.
3. Validate the complete planning matrix before source work. `sources.yaml` is inventory; only production mappings in `sources.json` are runnable:

```powershell
python -m tools.political_ingestion.source_matrix
```

4. Audit requested sources before crawling:

```powershell
python -m tools.political_ingestion.cli audit --set central-core
```

5. Run a bounded dry-run first. Omit `--limit` only after the bounded run succeeds.

```powershell
python -m tools.political_ingestion.cli run --set central-core --limit 3
```

6. Inspect `plan`, `errors`, target shelves/notebooks, and the generated manifest. Never apply a manifest containing errors.
7. Apply the exact reviewed manifest only when the user explicitly requests import or synchronization. Run the command on the target host; the CLI rejects non-loopback APIs.

```powershell
python -m tools.political_ingestion.cli apply --manifest data/political-ingestion/runs/<run>/manifest.json
```

8. Report added, duplicate and failed counts, backup path, output directory, and any disabled sources.

For the verified weekly source set, use the shared scheduled entry point. Keep `--dry-run` for local validation:

```powershell
python tools/political_ingestion_scheduled_run.py --set weekly --dry-run --limit 3
```

## Guardrails

- Keep the existing `qstheory_*` workflow independent.
- Never treat a `planned` matrix entry as runnable or add it to a scheduled set before its rules, adapter, and tests are verified.
- Treat the official source registry and canonical URLs as source-of-truth metadata.
- Do not enable a disabled dynamic source until its dedicated adapter and tests exist.
- Do not bypass dry-run, exclusive locking, strict crawl failure, or SQLite backup.
- Do not overwrite existing notes or synchronize deletions.
- Keep official attachments as clickable Markdown links; do not download or parse attachment files.
- Use the same CLI for manual runs, Agent runs, and scheduled services.
