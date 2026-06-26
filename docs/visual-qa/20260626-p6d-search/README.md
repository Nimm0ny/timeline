# P6-D Search Command Palette Visual QA

- URL: `http://127.0.0.1:8798/?topic=1&event=1&mode=edit`
- Search jump check: `Ctrl+K` -> query `遵义` -> `Enter` -> `http://127.0.0.1:8798/?topic=3&event=192`
- Viewport: Playwright CLI + Edge, exact `1920x1080`
- Commands:
  - `cmd /c npm run qa:visual-fixture`
  - `cmd /c npm run build`
  - `playwright-cli -s=p6d-search resize 1920 1080`

## Screenshots

- `1920-edit-fixture.png` - baseline edit fixture.
- `1920-command-search.png` - command palette opened from `Ctrl+K`, search results with notebook source and command shortcuts.
- `1920-after-enter-jump.png` - `Enter` jump result, right detail opened on the searched event.

## Checks

- `Ctrl+K` opens the palette; `Esc` closes it.
- Search input is borderless in Edge (`border: 0`, `box-shadow: none`).
- Results include event source via `NotebookChip` and date meta.
- `Enter` on the active event jumps to the correct topic and event.
- `body` remains `overflow: hidden`; no checked workspace/palette container uses `transform: scale()`.
- Only console error observed: missing `favicon.ico` 404, unrelated to this task.
