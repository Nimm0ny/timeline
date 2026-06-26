# P6-B Media Pipeline Visual QA

- Task: P6-B media pipeline settings and attachment lazy image path.
- URL: `http://127.0.0.1:8798/?topic=1&event=1&mode=edit`
- Viewport: `1920x1080`
- Browser path: in-app Browser plugin.
- Screenshots:
  - `1920-edit-after.png`: fixed fixture edit state after P6-B changes.
  - `1920-settings-media-after.png`: Settings -> Media / Storage controls.
- Commands:
  - `cmd /c npm run qa:visual-fixture`
  - `cmd /c npm run build`
- Checks:
  - Page title `编年 Chronicle`.
  - DOM rendered with timeline content, no framework error overlay.
  - Console `error` / `warn` logs empty.
  - Media settings controls visible: compress on, keep original off, quality 80.
  - No horizontal overflow in the media settings view.
- Known deviations: none for this P6-B surface.
