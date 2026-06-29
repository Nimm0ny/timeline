# Visual QA — W3 display-style views (board / gallery / outline)

- **Task**: 编年 W3 — add the `board` (option-grouped kanban), `gallery` (image card
  grid), and `outline` (collapsible era tree) display styles, capability-gated, and
  list all six views in the switcher. See `docs/note-types-and-views-design.md`.
- **Viewport**: `1920×1080`, deviceScaleFactor 1.
- **Capture**: headless Chromium via Playwright (borrowed from `D:/py_pj/sikao/node_modules`,
  not added as a dependency here). Throwaway scripts under the session scratchpad.
- **Fixture notebook**: a temporary fully-capable notebook (`zzW3GalleryQA`, 6 dated
  events, a `type` select with 3 valued options, 4 of 6 events carrying an image) was
  built via the API so every view — gallery included — unlocks. It was **deleted after
  capture**; `delete_topic` purged its 4 orphan images (8 files) from `data/images`,
  leaving the user's notebooks (ids 1–4) and image store untouched.

## Screenshots

| File | State |
|---|---|
| `1920-board.png` | Board — grouped by 类型 (战役 4 / 人物 1 / 条约 1), color-dot headers, cards = headline + 2-line summary + date; active card highlighted |
| `1920-gallery.png` | Gallery — 4 image thumbnails + 2 placeholder cards (金田起义 / 中华民国成立), floating star on the active card |
| `1920-outline.png` | Outline — collapsible era groups (晚清 1839–1894 · 5条 / 民国 1912 · 1条), indented bullet rows + date, indent guide |
| `1920-outline-collapsed.png` | Outline with 民国 collapsed (chevron-right, children hidden) while 晚清 stays expanded |
| `1920-switcher-all-views.png` | Switcher popover on the fully-capable notebook → all six views listed (时间线 ✓ / 表格 / 看板 / 画廊 / 列表 / 大纲), each a distinct Lucide icon |
| `1920-switcher-hover-fixed.png` | Switcher hover state after the popover-width fix — highlight fills the box (画廊 correctly greyed/disabled on an imageless notebook) |

## Verified

- All three new views render with real data; selection (active), favorite star reveal,
  and select-mode highlight behave consistently with timeline/table/list.
- **Board** auto-groups by the first select column (`pickBoardColumn`); option columns
  always render (stable shape), empty/cleared values collapse into a trailing 未分类
  bucket, and cards sort chronologically within a column.
- **Gallery** reads the image off the index DTO (new `image`/`imageUrl`/`thumbUrl`
  fields, joinedload — no N+1); imageless entries show the placeholder glyph, not a
  broken image.
- **Outline** reuses the page's existing era grouping (`props.groups`); collapse state
  is component-local and resets per notebook.
- Capability gating is the W1 backend SSOT: gallery only appeared once the notebook had
  an image; board only with an option column; the switcher lists exactly the capable
  implemented views.
- **0 console errors/warnings** across board/gallery/outline/table/list/timeline
  transitions; fixed row heights, tokens only, no `transform: scale`.
- **Switcher popover width fix**: the `.tl-pop-views` class was applied to two nested
  elements (the outer popover via the dynamic `:class`, plus the inner wrapper div), so
  `width: min(220px, calc(100% - 24px))` under-sized the inner content — the hover
  highlight left ~40px dead space on the right (measured: item 178px in a 218px box).
  Collapsing the redundant inner `<div>` to a `<template>` lets items fill the box
  (item now 202px, the residual 16px is the popover's symmetric 8px padding).

## Commands

```
npm run agent:check && npm run build && npm run test:ui   # all pass (test:ui 96)
python -m pytest tests/test_note_types_capabilities.py tests/test_timeline_api.py   # 21 passed
```

## Known deviations / notes

- The built-in preview MCP raster screenshot tool times out on this Windows setup
  (window-occlusion); shots were taken via Playwright in a fresh process instead.
- Board groups by the *first* select column automatically — no per-view group-by picker
  yet (a later polish; matches the W3 scope "board = 按 select 列分组").
- Board/gallery/outline reuse the timeline/table cell helpers via small per-view
  templates rather than a shared sub-component — the same deliberate low-risk tradeoff
  noted for the table view; a shared card sub-component is a later DRY candidate.
