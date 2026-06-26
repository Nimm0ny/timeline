# Sidebar Notebook Expand Visual QA

- URL: `http://127.0.0.1:8798/?topic=3&event=192`
- Fixture: `topic=3`, `event=192`, headline `遵义会议召开`
- Viewport: in-app Browser interaction checks + Playwright CLI exact `1920x1080` screenshots
- Commands:
  - `cmd /c npm run qa:visual-fixture`
  - `TIMELINE_VISUAL_TOPIC_ID=3 TIMELINE_VISUAL_EVENT_ID=192 TIMELINE_VISUAL_EVENT_HEADLINE=遵义会议召开 cmd /c npm run qa:visual-fixture`

## Screenshots

- `1920-topic3-expanded.png` - `近代史` is active, expanded, and shows era rows.
- `1920-after-click-dangshi-expanded.png` - clicking `党史` selects it, expands its era rows, and collapses `近代史`.
- `1920-active-collapsed.png` - clicking the active `党史` row collapses its children while keeping the row selected.

## Checks

- Active notebook chevron matches child visibility.
- Clicking another notebook expands that notebook immediately.
- Previously active notebook collapses after switching.
- Child list uses stacked enter/leave animation without `transform: scale()`.
- Page title is `编年 Chronicle`; in-app Browser reported no console warn/error.
- Only Playwright console error observed: missing `favicon.ico` 404, unrelated to this task.
