# Frontend Visual Redesign Prototype Plan

Status: visual exploration, not implementation baseline.

## Define-First

Goal:

- Produce several desktop light-mode visual prototype files for the three-column timeline notes app.
- Base the prototypes on the current Vue implementation and the frozen 1920x1080 one-view constraints.
- Give the next implementation pass clear visual options without changing production code yet.
- Explore a non-red primary accent direction because the latest user requirement explicitly rejects the current red style.
- Reduce duplicated creation affordances to one new timeline-node entry.
- Make command buttons icon-only and aligned with the Lucide visual system.

Non-goals:

- Do not modify `ui/src/**`, backend code, API contracts, database seed data, package files, or frozen design documents.
- Do not replace the current pixel-perfect baseline in production code.
- Do not introduce dark mode, mobile layout, new navigation architecture, marketing hero surfaces, or image-background UI.

Scope:

- Add standalone HTML prototype files under `prototypes/`.
- Add this plan/audit document.
- Keep the visual structure: left topic/filter sidebar, center timeline feed, right detail/edit pane.
- Remove repeated new-entry surfaces from the prototype pass: no left quick-record button and no bottom composer-as-new-entry.

Acceptance:

- Each prototype opens as a standalone HTML page.
- Each prototype preserves the required functional areas and 1920x1080 desktop frame.
- Each option has a distinct visual decision, not just a token recolor.
- Each option has exactly one visible new timeline-node entry, represented by an icon-only Lucide-style create control.
- Command buttons are icon-only in the prototype surface.
- Production implementation remains untouched until a direction is approved.

Verification:

- Inspect the static files for forbidden production-side changes.
- Render the prototype pages at 1920x1080 where tooling permits.
- Re-run `git status --short` and confirm only intended prototype/plan files are added, plus pre-existing user changes remain separate.

## Existing Implementation Map

- `ui/src/pages/TimelinePage.vue` owns app state, route query sync, filtering, dirty-draft confirmation flow, topic/event CRUD orchestration, responsive CSS variable calculation, and the three-column composition.
- `ui/src/components/timeline-notes/TopicSidebar.vue` renders the brand, quick record button, main filters, topic list, tag list, and settings entry. Counts are derived from the current topic and active main filter.
- `ui/src/components/timeline-notes/TimelineFeed.vue` renders search, date locator, year/month rail, event card stack, and composer. It uses Pretext-derived card layouts but keeps visible UI as DOM/CSS.
- `ui/src/components/timeline-notes/TimelineEventCard.vue` is intentionally small: title, favorite/more actions, preview, and chips.
- `ui/src/components/timeline-notes/EventDetailPane.vue` renders actionbar, read/edit states, Markdown body/editor, tags, attachments, and related events. Current uncommitted user work adds edit-mode date/topic fields and Markdown editor border treatment.
- `ui/src/styles/timeline-notes.css` is the real visual control plane: tokens, three-column sizing, sidebar density, timeline rail/card geometry, composer, and detail pane styling.
- `ui/src/components/timeline-notes/TimelineLucideIcon.vue` is the only production runtime Lucide icon gateway.

## Constraints Carried Into Prototypes

- Desktop, light mode, 1920x1080.
- Left / center / right structure remains approximately `293 / 1075 / 552`.
- The current frozen implementation uses red as the primary accent. The latest user requirement says red is not acceptable, so this prototype pass intentionally explores non-red palettes. Production adoption requires updating the visual baseline before implementation.
- No dark theme, glassmorphism, glow/orb decoration, marketing hero, large illustration background, nested cards, or screenshot-backed UI.
- Typography should feel like the project font: compact Chinese workbench text with normal letter spacing.
- Cards stay low-radius and dense enough for a one-view timeline.
- Right pane keeps explicit edit affordances: actionbar, icon-only save, title, date/topic fields, bordered Markdown editor, tags, attachments, related events.
- Static HTML prototypes use local Lucide-style SVG sprites for offline review. Production implementation must use `TimelineLucideIcon.vue`.

## Prototype Directions

1. Sage Archive
   - File: `prototypes/timeline-visual-redesign-calm-paper.html`
   - Decision: move from red to sage/ink accents while keeping a warm paper workbench. Best when the product should feel calm and self-use oriented.

2. Cobalt Ledger
   - File: `prototypes/timeline-visual-redesign-research-ledger.html`
   - Decision: use cobalt/brass accents and a stronger axis for research precision. Best when the product should feel like a serious historical database.

3. Graphite Focus
   - File: `prototypes/timeline-visual-redesign-focus-editor.html`
   - Decision: use graphite/teal accents and give the editor more calm visual priority. Best when the main workflow is writing and refining a selected note.

## Element-Level UX Decisions

| Element | Why here | Duplicate function check | Simplification choice |
| --- | --- | --- | --- |
| Left brand | Left edge anchors app identity before navigation. | No duplicate brand elsewhere. | Keep brand text; menu is icon-only. |
| Main filters | Sidebar is the persistent scope/filter area, matching current implementation. | Not repeated in center or right pane. | Keep labels because filter names are content, not command buttons. |
| Topic list | Topic is the outer data scope, so it stays above tags. | Not repeated as a top switcher. | Rows expose only title/range/count; no secondary action buttons per row. |
| Tag list | Tags are secondary filters under the selected topic and main filter. | Not repeated in top search. | Small color dots and counts are enough; no tag management buttons. |
| Settings | Utility action belongs at the sidebar bottom, away from note creation. | No header settings duplicate. | Icon-only footer utility with accessible label in production. |
| Search | Center top because it filters the visible timeline, not global app state. | No secondary search in right pane. | Search field keeps text placeholder; it is an input, not a command button. |
| Date locator | Beside search because it navigates the same timeline surface. | Not repeated in cards or sidebar. | Icon-only calendar/search control opens detail picker later. |
| New timeline node | Center top, adjacent to timeline search/date controls, because the new item enters the timeline. | Replaces left quick-record and bottom composer entry. | One icon-only PlusCircle button. |
| Timeline rail | Left of cards because dates belong to chronology, not inside card bodies. | Date labels are not repeated in cards. | Keep year/month only; card copy stays about content. |
| Event cards | Center column remains the primary browse surface. | Details are not duplicated beyond title/summary/tags. | Card actions are only favorite and more, both icon-only. |
| Right actionbar | Top of detail pane because actions affect the selected event. | Save/edit/close are not repeated in editor body. | All command buttons are icon-only Lucide-style controls. |
| Metadata fields | Directly under title because date/topic defines the event identity. | Date is not repeated in card body. | Four compact fields; no extra helper copy. |
| Markdown editor | Main right-pane body because editing is the selected-event workflow. | No split preview duplicate in this phase. | One bordered editor with an icon-only toolbar. |
| Tags/attachments/related | Below editor because they support the note instead of interrupting writing. | Related cards are not repeated in the timeline. | Rows use one icon action each and short metadata. |

## Approval Gate

These prototypes are comparison artifacts. The next production task must first pick or merge a direction, then translate the accepted option into `timeline-notes.css` and the existing Vue components under the normal visual QA fixture.
