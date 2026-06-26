# 2026-06-26 Mobile Web QA

Task: implement `docs/mobile-web-design.md` mobile web shape.

URLs:
- Desktop fixture: `http://127.0.0.1:8798/?topic=1&event=1&mode=edit`
- Mobile list: `http://127.0.0.1:8798/?topic=1`

Verification:
- `cmd /c npm run agent:check`
- `cmd /c npm run build`
- `cmd /c npm run test:ui`
- `python -m pytest tests/test_timeline_api.py tests/test_date_utils.py`
- `cmd /c npm run qa:visual-fixture`
- Browser plugin: page identity, console health, drawer open, column sheet open, row tap opens full-screen detail.
- Playwright CLI + system Edge channel: exact fixed-size screenshots with `--viewport-size`.

Screenshots:
- `1920-edit-playwright.png` — exact `1920x1080`, fixed edit fixture.
- `375-list-playwright.png` — exact `375x812`, mobile list.
- `390-list-playwright.png` — exact `390x844`, mobile list.
- `375-detail-playwright.png` — exact `375x812`, mobile full-screen detail with left return.
- `375-drawer.png` — Browser plugin drawer-open pass.
- `375-columns-sheet.png` — Browser plugin bottom-sheet column settings pass.
- `375-detail.png` — Browser plugin row-tap full-screen detail pass.

Notes:
- Browser plugin viewport override reports Windows-scaled CSS viewports (`386x837`, `402x870`) when asked for `375x812` and `390x844`; Playwright CLI files above provide the exact required PNG sizes.
- Final DOM checks reported no horizontal overflow for desktop, `375` list/drawer/sheet/detail, and `390` list states.
- Review fixes verified in Browser plugin: row delete/star targets are `44x44`, settings closes the mobile drawer, and detail has a `44x44` left return button.
- Console warnings/errors were empty in Browser plugin checks.
