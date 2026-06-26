# Favorites Tab Visual QA

- URL: `http://127.0.0.1:8798/?topic=1`
- Flow: open topic 1 -> click the left ribbon `收藏` icon -> verify the favorites pane.
- Viewport: Playwright CLI + Edge, exact `1920x1080`
- Browser path: in-app Browser was attempted first, but local page navigation timed out twice and reset the browser-control session; Playwright CLI was used as fallback.
- Commands:
  - `cmd /c npm run qa:visual-fixture`
  - `playwright-cli -s=favorites-tab-qa resize 1920 1080`

## Screenshots

- `1920-favorites-tab-after.png` - left favorites pane only shows the status copy; the old `跨笔记本收藏` entry is absent.

## Checks

- `.global-favorite-entry` is absent.
- Left pane text does not include `跨笔记本收藏`.
- Left pane shows `暂无收藏。` when the global favorite count is zero.
- Middle feed still enters `收藏（跨本）` mode.
- `body` remains `overflow: hidden`; no checked runtime element uses `transform: scale()`.
- Only console error observed: missing `favicon.ico` 404, unrelated to this task.
