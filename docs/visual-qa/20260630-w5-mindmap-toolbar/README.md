# Visual QA — W5 mindmap editing toolbar + snapshot persistence

- **Task**: 编年 W5 — give the `mindmap` note type an editing toolbar and make the
  whole canvas state durable. The center-column surface now carries a toolbar:
  **undo/redo**, a **layout/direction** menu (逻辑结构右/左 · 思维导图 · 组织结构 · 目录组织 ·
  鱼骨), a **background** menu (跟随主题 + 纸白/纯白/米色/冷灰/深色), and **font size −/+ ·
  bold · text colour** (icon buttons) that act on the selected node (XMind-style
  select-then-style). The mindmap persists the **full simple-mind-map snapshot**
  (`getData(true)` = `{ root, layout, theme, view }`) in `body_json`, so layout,
  background, per-node font/colour, and pan/zoom survive a reload. Node colours are
  re-derived from the app's CSS tokens each load and **adapt to the background's
  luminance** (a dark canvas gets light text); a fresh map keeps the canvas
  transparent so it **follows the app's light/dark theme** unless a swatch is picked.
  Feed rows show a **mindmap badge** so a mixed notebook reads at a glance.
  See `docs/note-types-and-views-design.md`.
- **Viewport**: `1920×1080`, deviceScaleFactor 1.
- **Capture**: Playwright (borrowed from `D:/py_pj/sikao/node_modules`) driving the
  **production build served by the backend at `:8000`** — deterministic, avoiding the
  vite dev-server dynamic-chunk HMR cache (see `dev-workflow-gotchas`). Throwaway
  scripts under the session scratchpad.
- **QA data discipline**: every check ran in a temporary notebook (`zzW5*QA`) created
  via the API and **deleted afterward** (topics back to the user's own ids, zero stray
  `note_type=mindmap` events). The user's notebooks were untouched.

## Screenshots

| File | State |
|---|---|
| `1920-toolbar-canvas.png` | Toolbar + a follow-theme (transparent → light app) map, `mindMap` layout, accent root, a selected node (font/colour enabled) |
| `1920-dark-background.png` | Explicit 深色 background — node text flips to light (the contrast fix) |
| `1920-reload-canvas.png` | After a full reload — layout, background, tree, and reparent all persisted; status 已保存 |
| `1920-feed-badge.png` | Feed list showing the per-row mindmap badge |

> **Note on node text in these PNGs.** simple-mind-map draws node text inside an SVG
> `<foreignObject>`, which Playwright (headless *and* headed) renders faintly — the W4
> mindmap shot has the identical faintness. DOM inspection confirms each node's text is
> correct (right content, adaptive colour, `18px`, Noto Sans SC), and ordinary DOM text
> (sidebar, toolbar labels) renders crisp in the same captures. In a real browser the
> node text renders normally; the screenshots are reliable for layout/theme/toolbar,
> not for judging glyph legibility.

## Verified end-to-end (via Playwright + DOM inspection, against the build)

- **Toolbar** renders all controls; node-style buttons (font/bold/colour) disable with
  a hint until a node is selected, then enable (`node_active`). Font buttons are icons.
- **Drag-to-reparent works** (the `Drag` plugin ships in `full.js`): dragging a node
  onto another moved it (`root.children` 2→1, child gains the dragged node) and the new
  structure **persisted** through a reload.
- **Font** +2 ×2 on a second-level node → `fontSize: 19` (depth-aware baseline 15→17→19),
  stored on the node and re-applied on reload.
- **Background contrast** — DOM colours: light/follow canvas → leaf text `rgb(29,27,24)`;
  dark canvas → leaf text `rgb(255,255,255)`. Always legible.
- **Follow-theme default** — a new map saves `backgroundColor: "transparent"`, so the
  canvas tracks the app theme; an explicit swatch pins that colour.
- **Layout/direction** → `思维导图` persists as `layout: "mindMap"`.
- **Token theme persists** — root fill equals the `--accent` token (`#7b68d9`) after
  reload, not the library default.
- **Feed badge** present; **0 console errors** across create / drag / style / reload.

## Bugs found and fixed during QA + review

1. **Theme reverted to the library default on reload.** Init applied the token theme then
   a separate `setThemeConfig({ backgroundColor })`; the second lone call dropped the
   node-level token colours. Fixed by folding background into the token theme in one
   `applyTheme()` call.
2. **`lineColor` set to a size token** (`--icon-bar` → `--border-strong`).
3. **[review P1] Dark-on-dark node text + theme desync.** Node text was fixed-dark → on a
   dark canvas it vanished; and the snapshot always pinned the at-save background, so a
   map showed a mismatched canvas when reopened under the other app theme. Fixed:
   luminance-adaptive text, and a transparent (follow-theme) default with only explicit
   picks persisted.
4. **[review P2]** `A−/A+` text buttons → `A↓/A↑` icons (§9); depth-aware font baseline;
   raw-hex canvas palette documented (written into the library snapshot, not app CSS);
   stale token fallbacks corrected.

## Performance

- `simple-mind-map/full.js` stays **dynamically imported** → lazy `full-*.js` chunk
  (≈1.59 MB) loaded only when a mindmap opens; the main bundle is unaffected.
- Viewport culling (`openPerformance`) enabled only for maps with **> 60 nodes**;
  no-op autosaves suppressed via a `getData(true)` baseline so opening without editing
  never writes.

## Commands

```
npm run agent:check && npm run build && npm run test:ui   # guard 45, build ✓ (lazy chunk), test:ui 102
python -m pytest tests/test_note_types_capabilities.py tests/test_timeline_api.py   # 23 passed
```

## Deferred to the next wave (W5-interop)

`.xmind` import/export, markdown↔mindmap bridge, cross-type search/favorite/trash
consistency, undated mindmaps, type pickers on the secondary create paths (sidebar ⊕ /
mobile +).
