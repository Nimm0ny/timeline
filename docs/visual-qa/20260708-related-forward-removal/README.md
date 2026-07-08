# Visual QA — 去掉右栏「关联事件」正向手动关联（§6.4 bullet 3 / §6.5）

Date: 2026-07-08 · viewport **1920×1080** · frontend `npm run dev`.

> Env note: `:8000` held by an unrelated project (sikao); timeline backend ran on **:8001** with the
> vite proxy temporarily repointed `8000→8001` **(reverted before commit)**. Fixture note deleted after QA.

## What changed
`EventDetailPane.vue` no longer renders/edits the forward「关联事件」section (read display + edit-mode
manual-relate picker + kebab「关联事件」entry). Relationships are now: forward = body `[[wikilink]]`
(inline), backward = the existing `BacklinkPanel`. **Frontend-only** — backend DTO
(`relatedEventIds`/`relatedEvents`) + column kept until W6; `submit()` still sends `relatedEventIds`
so existing relations round-trip unharmed.

## Fixed-URL checks (`?topic=1&event=1&…`, 1920×1080)

| Check | Result |
|---|---|
| **Read (`mode=view`, event 1)** | pane section heads = `["属性","反向链接"]` — **no「关联事件」**; `BacklinkPanel` present; forward-section nodes (`.related-results/.related-result/.detail-inline-search`) = **0**; **no console errors** |
| **Edit (`mode=edit`, event 1)** | section heads = `["属性"]`; forward nodes = 0; **kebab menu = 添加附件 / 详情居中显示 / 回收站 — no「关联事件」item** (`has关联事件:false`, `has添加附件:true`) |
| **Read↔edit zero-shift** | 属性/标题/正文 unchanged between modes; the removed section was already conditionally-hidden (event 1 has 0 relations) so no block shifts; `BacklinkPanel` is read-only (pre-existing `v-if="!inEditMode"`, not this cut) |

## End-to-end §6.4 chain (browser + API)
Created note **A (id 209)** with `relatedEventIds:[1]` via `POST /api/topics/1/events`:
- A's DTO round-trips `relatedEventIds:[1]` + `relatedEvents:[1]` (data preserved — `submit` still sends it).
- **Open A (which HAS a relation) → still NO forward「关联事件」section** (heads = `["属性","反向链接"]`) — proves the forward display is gone even for notes that carry relations.
- **Event 1's `BacklinkPanel` (expanded) shows A**: `反向链接 1 · QA-A relates to 1 · 手动关联 · 党史` — i.e. `GET /api/events/1/backlinks` → `[{sourceId:209, anchorType:"manual", contextText:"手动关联"}]`.

This closes the loop with the prior backend cut (`9ff21e5`): a forward "关联事件" relation, now managed only via the removed editor's residual data, remains visible as an **incoming manual backlink** on the target.

## Automated
`node --test ui/tests/*.test.js` → **215/215** (unchanged — `timelineNotes.js` utils untouched, so `buildEditorDraft`/`buildReadableDetailGroups` tests stay green) · `npm run build` ✓ · `npm run agent:check` ✓ 59.

## Screenshot note
Four 1920×1080 frames were captured inline via the preview tool and visually verified (read-mode event 1
with 属性+反向链接; edit-mode kebab open showing no「关联事件」; A with no forward section; event 1
backlink panel expanded showing A「手动关联」). The harness cannot write these PNGs to the repo
filesystem, so this README carries the quantitative DOM/API evidence instead — same convention as
`20260708-w5b-canvas-culling/` and `20260708-w5b2-canvas-t2/`.
