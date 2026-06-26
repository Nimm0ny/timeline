# P6-E Related Event Preview Popover Visual QA

- Task: P6-E related event preview changed from direct detail replacement to a hover/click-pinned annotation popover.
- Fixed fixture URL: `http://127.0.0.1:8798/?topic=1&event=1&mode=edit`
- Fixed fixture viewport: CSS `1920x1080`; screenshot captured with system Chrome channel at `1920x1080`.
- Interaction QA URL: `http://127.0.0.1:8799/?topic=1&event=1`
- Interaction fixture: temporary mock backend with one related event, used because the current local real database has no `relatedEvents`.

## Screenshots

- `1920-edit-after.png`: real backend fixed fixture at `1920x1080`.
- `1920-related-popover-browser.png`: in-app Browser proof of the pinned annotation popover at CSS `1920x1080` on the interaction fixture. The file is `1979x1113` because the in-app Browser exports device pixels at its current DPR.

## Verified

- `cmd /c npm run qa:visual-fixture` passed for topic `1`, event `1`.
- In-app Browser: hover path was implemented on the related row; Browser CUA hover coordinates were inconsistent in hidden mode, but click-pinned behavior was verified against the same row.
- Click related row: popover remains pinned, original detail stays on `鸦片战争`, URL stays `?topic=1&event=1`.
- Click popover open icon: detail switches to `《南京条约》签订`, URL becomes `?topic=1&event=2`, popover closes.
- Markdown images in preview text are represented as `[图片]`; the popover does not load inline images, and full image rendering remains in the detail pane.
- Browser console after interaction: no warnings or errors.

## Known Deviations

- The real fixture has no related events, so the popover interaction screenshot uses a temporary mock backend rather than mutating real `data/`.
- The fixed real-backend page still reports a pre-existing 1px `body.scrollWidth` rounding overflow under Browser DPR calibration; no visible horizontal scrollbar appeared.
