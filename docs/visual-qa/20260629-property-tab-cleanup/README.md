# 2026-06-29 属性 Tab 单职责清理

- Task: 左栏属性 Tab 去掉“跳转到笔记本”按钮，并在折叠态隐藏编辑按钮。
- URL: `http://127.0.0.1:8798/?topic=1&event=1&mode=edit`
- Viewport: `1920×1080`
- Screenshots:
  - `1920-property-tab-after.png`
- Verification Commands:
  - `cmd /c npm run agent:check`
  - `cmd /c npm run build`
  - `cmd /c npm run test:ui`
  - `python -m pytest tests/test_timeline_api.py tests/test_date_utils.py`
  - `cmd /c npm run qa:visual-fixture`
- Notes:
  - 属性 Tab 可见 DOM 中已不再出现“切换到此笔记本”按钮。
  - 默认折叠的其他笔记本条目不再显示编辑按钮；当前展开项保留一个管理按钮。
