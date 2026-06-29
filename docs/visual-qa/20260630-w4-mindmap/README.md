# Visual QA — W4 mindmap note type (axis 2)

- **Task**: 编年 W4 — add the `mindmap` note type (axis 2). The 新建 button now offers a
  note-type picker (条目 / 思维导图); a mindmap is authored on its own canvas
  (`simple-mind-map`, the second registered dependency exception), embedded in the
  center column with a fullscreen toggle (D-2: 中栏内嵌 + 可全屏). The tree persists in
  `TimelineEvent.body_json`. See `docs/note-types-and-views-design.md`.
- **Viewport**: `1920×1080`, deviceScaleFactor 1.
- **Capture**: headless Chromium via Playwright (borrowed from `D:/py_pj/sikao/node_modules`,
  not added here). Throwaway scripts under the session scratchpad.
- **QA data discipline**: the create→edit→reload round-trip ran in a temporary notebook
  (`zzW4MindmapQA`); it and every test mindmap were **purged afterward** (topics back to
  ids 1–4, zero stray `note_type=mindmap` events). The user's notebooks were untouched.

## Screenshots

| File | State |
|---|---|
| `1920-newtype-picker.png` | 新建 type picker — 条目 (note glyph) / 思维导图 (network glyph) |
| `1920-mindmap-roundtrip.png` | Mindmap canvas after add-child + reload — root 中心主题 → child 分支一, header bar (back / icon / title / 已保存 / fullscreen) |

## Verified (end-to-end via Playwright)

- **Create**: 新建 → 思维导图 creates a today-dated `note_type=mindmap` note seeded with a
  single root and opens the canvas; `simple-mind-map` renders an SVG (~1652×1028 fill).
- **Author**: selecting the root + Tab + typing adds a child node on the canvas.
- **Persist + reload**: after a full page reload and reopening the note, the canvas
  re-renders `["中心主题","分支一"]` — the tree round-trips through `body_json`. The API
  confirms `bodyJson.children = ["分支一"]`.
- **Headline tracking**: the note's headline follows the root node text, with the
  rich-text HTML (`<p>…</p>`) stripped to plain text (`中心主题`) for the list label.
- **0 console errors** across create / author / reload.
- Backend relaxations (note_type=mindmap may omit items + era; entries still require
  body) and the 5 MB `body_json` guard are covered by pytest.
- **Robustness (post-review fixes, verified):** switching notebooks in-app while a
  canvas is open returns to the feed — no stale surface (a `mindmapNote` topic+selection
  guard); the command palette routes a mindmap to the canvas, not the markdown pane; the
  save carries the bound note id so a flush during a note-switch or after close writes to
  the right note; an autosave forwards the note's `attachments`/`relatedEventIds` (the
  `updateEvent` full-replace would otherwise blank them); the headline decodes rich-text
  HTML + entities.

## Bundle

- `simple-mind-map/full.js` is **dynamically imported** in `MindmapEditor.vue`, so it
  builds as a lazy async chunk (`full-*.js` ≈ 1.59 MB / 514 kB gzip, plus `full-*.css`
  24 kB) loaded only when a mindmap note is opened. The main bundle is unaffected
  (index ≈ 339 kB, +5 kB vs pre-W4).

## Commands

```
npm run agent:check && npm run build && npm run test:ui   # all pass (test:ui 97)
python -m pytest tests/test_note_types_capabilities.py tests/test_timeline_api.py   # 23 passed
```

## Known deviations / notes

- The built-in preview MCP raster screenshot tool times out on this Windows setup; shots
  were taken via Playwright in a fresh process.
- v1 scope: the note-type picker lives on the main feed `+`; secondary create paths
  (row ⊕, command palette) still default to `entry`. The feed rows do not yet show a
  per-note mindmap badge. The mindmap stores only the node tree (`getData(false)`), so a
  changed layout/theme defaults on reload. All deferred to a later polish pass (W5).
- `simple-mind-map` ships with its own default node theme (green root); matching it to the
  app's tokens is a later theming pass.
