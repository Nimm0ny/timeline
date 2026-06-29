# Visual QA — W2 display-style view switcher (timeline / table / list)

- **Task**: SIK/编年 W2 — add a Notion-style view switcher (single button + popover in the
  middle-column action cluster) and the `table` + `list` views, capability-gated, persisting
  to `Topic.display_style`. See `docs/note-types-and-views-design.md`.
- **Fixed URL**: `http://localhost:5174/?topic=1` (notebook 党史, 56 events, real data).
- **Viewport**: `1920×1080`, deviceScaleFactor 1.
- **Capture**: headless Chromium via Playwright (borrowed from `D:/py_pj/sikao/node_modules`,
  not added as a dependency here). Script was a throwaway under the session scratchpad.

## Screenshots

| File | State |
|---|---|
| `1920-timeline.png` | Timeline view (unchanged baseline) |
| `1920-switcher-popover.png` | View switcher popover open — 时间线 (active ✓) / 表格 / 列表 |
| `1920-table.png` | Table view — flat, sortable headers, 时间 sorted asc |
| `1920-table-sorted-by-title.png` | Table sorted by 事件 (caret moved, rows re-ordered) |
| `1920-list.png` | List view — title + muted preview + date |
| `1920-timeline-regression.png` | Back to timeline after switching (no regression) |

## Verified

- Switcher popover lists only implemented + capable views (timeline/table/list all enabled here;
  board/gallery/outline correctly absent — W3). Capability gating driven by the W1 backend DTO.
- Table reuses `.row` + every `.c-*` cell and the same `--rowgrid` (column-aligned headers/rows);
  drops the era spine; click-to-sort headers; default time-asc; star + row-action + chip `+N` work.
- List one line per note; star reveals on hover/active.
- `displayStyle` persists to the backend (`GET /meta` confirmed `table`, then reset to `timeline`).
- Rapid table→list→timeline switching ends on the final pick (rendered + persisted) — the meta-write
  race fix (serialize through the shared meta-save chain) holds.
- Row height fixed `min-height:33px` in all views; no horizontal overflow; tokens only
  (caret `--accent` violet); **0 console errors** across all transitions.
- Preview toggle (显示预览) is hidden outside the timeline view (it only affects `.ev-sum`).

## Commands

```
npm run agent:check && npm run build && npm run test:ui   # all pass (test:ui 89)
python -m pytest tests/test_timeline_api.py tests/test_date_utils.py tests/test_note_types_capabilities.py
```

## Known deviations / notes

- The raster screenshot tool of the built-in preview MCP times out on this Windows setup
  (window-occlusion issue); these shots were taken via Playwright with a fresh process instead.
- Table per-column cell template is duplicated from the timeline render (minus preview/notebook
  chip) — a deliberate low-risk tradeoff to avoid refactoring the polished timeline render; a
  shared sub-component is a candidate for a later DRY pass.
- Custom `date`-type column sort is lexical (ISO sorts chronologically; mixed-precision/BC edge
  cases may misorder) — deferred, low impact.
