# 2026-06-29 属性 Tab 按笔记本管理

- Task: 左栏属性 Tab 改为按笔记本分组管理，补充属性类型差异化展示与标签颜色自定义入口。
- URL: `http://127.0.0.1:8798/?topic=1&event=1&mode=edit`
- Viewport: `1920×1080`
- Screenshots:
  - `1920-property-browse-after.png`
  - `1920-property-manage-after.png`
- Verification Commands:
  - `cmd /c npm run agent:check`
  - `cmd /c npm run build`
  - `cmd /c npm run test:ui`
  - `python -m pytest tests/test_timeline_api.py tests/test_date_utils.py`
  - `cmd /c npm run qa:visual-fixture`
- Notes:
  - 固定 URL 下验证了属性页浏览态和当前笔记本管理态。
  - 轻量做了移动端 reload spot check，未归档移动端截图。
