Task: lazy topic loading and bookshelf tree smoke

URL:
- `http://127.0.0.1:8798/?topic=1&event=1&mode=edit`
- `http://127.0.0.1:8798/?topic=4&mode=view`

Viewport:
- `1920x1080`

Commands:
- `cmd /c npm run agent:check`
- `cmd /c npm run build`
- `cmd /c npm run test:ui`
- `python -m pytest tests/test_timeline_api.py tests/test_date_utils.py tests/test_note_types_capabilities.py`
- `cmd /c npm run qa:visual-fixture`

Screenshots:
- `1920-fixture-after.png`
- `1920-topic4-after.png`

Checks:
- Fixed fixture still opens with `topic=1` and `event=1`
- Left sidebar still renders `书架 > 笔记本 > 分组`
- Large notebook `topic=4` opens without blanking the sidebar and visibly renders only the first page (`中国历史 · 共 100 条`) instead of all `929` rows at once
- No relevant browser console errors/warnings were observed during the smoke run

Known deviations:
- In-app browser `domSnapshot()` failed on these pages with `incrementalAriaSnapshot is not a function`, so DOM proof used `playwright.evaluate()` and screenshots
- Scroll-driven auto-append for the next page was not conclusively reproduced in the in-app browser during this QA run, although backend pagination and pure unit tests for merge/fetch/scroll guards all passed
