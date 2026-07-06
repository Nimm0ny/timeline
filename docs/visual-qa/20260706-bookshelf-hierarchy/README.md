Task: bookshelf hierarchy left sidebar

URL:
- `http://127.0.0.1:8798/?topic=1&event=1&mode=edit`

Viewport:
- `1920x1080`

Commands:
- `cmd /c npm run qa:visual-fixture`
- `cmd /c npm run build`
- `cmd /c npm run agent:check`
- `cmd /c npm run test:ui`
- `python -m pytest tests/test_timeline_api.py tests/test_date_utils.py`

Screenshots:
- `1920-edit-after.png`
- `1920-bookshelf-collapse-after.png`

Checks:
- Fixed fixture opens with `topic=1` and `event=1`
- Left sidebar renders `书架 > 笔记本 > 分组`
- Clicking a bookshelf only collapses/expands the tree and does not switch the middle column topic

Known deviations:
- In-app browser `domSnapshot()` failed with `incrementalAriaSnapshot is not a function`, so DOM proof used `dom_cua.get_visible_dom()` plus screenshots
- Mobile viewport screenshot retry timed out in the in-app browser, so this archive only contains the required desktop `1920x1080` evidence
