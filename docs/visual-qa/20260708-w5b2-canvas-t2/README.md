# W5b-2 QA — 画布嵌笔记 T2 zoom-全文档 + 并发预算闸

Date: 2026-07-08 · frontend `npm run dev` @ 1440×900 · timeline backend (3 topics / 208 notes).

> Environment note: port :8000 was held by an unrelated project on this machine, so the timeline
> backend ran on **:8001** and the vite proxy target was temporarily repointed `8000→8001` for QA
> **(reverted before commit)**. All fixtures below are temp notes, permanently deleted after QA.

## Fixtures

| id | name | shape | purpose |
|----|------|-------|---------|
| 209 | QA-200-embeds | 20×10 grid, 200 embed cards / 60 notes | N=200 hero (reuses W5b-1 `make_qa_canvas.py`) |
| 210 | QA-cap-40 | 8×5 tight grid, 40 cards | force >budget simultaneous candidates → `make_cap_canvas.py` |
| 211/212 | QA-rich | one rich-markdown note (h1/list/quote/code) in a 1-card canvas | in-card markdown fidelity → `make_rich_canvas.py` |

## Results

### 1. T2 triggers by on-screen size (§7.2/§7.3) — canvas 209, host 1172×804
| zoom | full | preview | hidden | shell | note |
|------|------|---------|--------|-------|------|
| 1.0 | 0 | 70 | 130 | 0 | 240px < 360 fullPx → no T2; W5b-1 culling intact |
| 1.6 | 20 | 0 | 180 | 0 | on-screen cards ≥384px → full |

At 1.6× each full card renders `<div class="cv-embed-body markdown-body"><p>…full body…</p></div>` (20/20 bodies present).

### 2. Budget cap enforced (§7.3, `EMBED_FULL_BUDGET = 24`) — canvas 210
40 cards all on-screen at zoom 1.6 → 40 full candidates → **24 full + 16 demoted to preview** (0 hidden/shell); 24 markdown bodies rendered. Console:
```
[canvas] T2 over budget: 40 candidates → 24
```
With the realistic 200-grid the cap never engages (fullPx=360 ⇒ zoom ≥1.5 ⇒ ≤ ~20 large cards fit the viewport at once), so it is a **backstop that rarely bites** — matching the design premise ("主策略是让 T1 够便宜使预算极少触发"). It is only provable with a deliberately dense fixture.

### 3. In-card markdown fidelity — canvas 212 (rich note 211) at zoom 2.2
Full card body DOM = `[H1, P, UL(3×LI), BLOCKQUOTE, P(+inline code)]`, and `scrollHeight > clientHeight` (scrolls within the fixed 240×120 box — the box is not resized; the graph zoom enlarges it). This is the read-mode renderer's exact output, in-card.

### 4. Data contract (§7.4) — off-snapshot, O(1) open
- **Open (209): exactly 1× `POST /api/events/batch-preview`** for all 200 cards' T0/T1.
- **T2 promotion: per-full-card `GET /api/events/<id>`** via `ensureEventDetail` (shared LRU-40 detail cache) — one fetch per full card (57, 59-63, 79-83, 99-103…), bounded by the budget.
- **Zero `PUT` across all pan / zoom / T2 promotion** → tier + rendered HTML ride reactive stores (`canvasTierStore` / `embedDetailStore`) **off the X6 snapshot**: no `history:change`, no save, `updated_at` never bumped (§5.5 / §7.8).

## Screenshot note
`preview_screenshot` images (T2 rich card showing `# 秦朝统一` + bullet list; the 24-full cap grid) were captured inline in the session; the tool cannot write PNGs to disk, so the quantitative DOM / network / console evidence above is the substantive record (same convention as W5b-1's README).
