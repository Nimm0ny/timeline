## Task

- Keep the board view header flush under the toolbar by removing top padding from `.view-board`, so board cards do not bleed into a padding band above the sticky header while scrolling.

## URL

- `http://127.0.0.1:8798/?topic=1&event=1&mode=edit`

## Viewport

- `1920×1080`

## Interaction Path

- Open the fixed fixture URL.
- Confirm the center pane is in `看板` view from the toolbar switcher. If the fixture opens in another view, use `切换视图 -> 看板` before continuing.
- Capture the top-of-board state.
- Scroll the board container downward and verify the sticky column header remains flush under the toolbar without a visible gap.
- Capture a proof state with the view switcher open and `看板` checked, so the archived evidence is self-identifying even when the fixture only renders a single board column.

## Files

- `1920-board-switcher-after.png`
- `1920-board-top-after.png`
- `1920-board-scrolled-after.png`

## Verification Commands

```bash
cmd /c npm run agent:check
cmd /c npm run build
cmd /c npm run test:ui
python -m pytest tests/test_timeline_api.py tests/test_date_utils.py
cmd /c npm run qa:visual-fixture
```

## Notes

- Local backend port `8000` was already occupied by an existing Python process before QA started, so the fixture check reused that backend instance.
- Visual server for this QA run was started separately on port `8798`.
- The current fixture data renders board view as a single `未分类` column, so the canvas can visually resemble a vertical card list. The `1920-board-switcher-after.png` capture records the view switcher with `看板` selected to remove that ambiguity.
- Browser verification also confirmed `.view-board` was the rendered container, `getComputedStyle(.view-board).paddingTop === '0px'`, and the sticky `.bd-col-head` top edge stayed flush with the toolbar before and after scroll.
- No known visual deviations in the validated board state.
