# Visual QA — X6 Mindmap Drag

- Task: verify the AntV X6 mindmap editor can drag nodes to arbitrary coordinates with edges following, and check node text clarity / occlusion.
- Date: 2026-06-30
- URL(s):
  - `http://127.0.0.1:8798/?topic=5&event=1138`
  - Row click from the above URL enters the mindmap canvas for note `1138`.
- Viewport: `1920×1080`

Verification:

```bash
cmd /c npm run agent:check
cmd /c npm run test:ui
cmd /c npm run build
python -m pytest tests/test_timeline_api.py tests/test_date_utils.py
```

Checks:

- Direct URL `?topic=5&event=1138` lands on the feed/detail state first; it does not auto-open the mindmap canvas.
- Clicking the single mindmap row opens the X6 canvas successfully.
- Dragging child node `12312` changed its screen position from roughly `(960,550)` to `(1130,448)`.
- The corresponding edge path updated immediately after drag; no console errors were emitted.
- Text audit after drag:
  - all three labels stayed inside their node bounds
  - no node-node overlap was detected
  - label opacity stayed `1`
  - root label fill stayed white on the accent node; child labels stayed dark on light nodes

Artifacts:

- `1920-direct-url-feed-state.png`: direct URL state before clicking into canvas
- `1920-canvas-after-drag.png`: canvas state after dragging a child node and observing edge follow

Cleanup note:

- The dragged node was moved back to its original position after QA so the database state was restored.
