# 2026-06-29 属性 Tab 结构与样式整理

- Task: 去掉属性 Tab 内层重复“属性”层级；移除类型下拉中的“邮箱/电话”；统一属性管理卡片与下拉排版；补 `orphan option` 类型锁定前端回归测试。
- URL: `http://127.0.0.1:8798/?topic=1&event=1&mode=edit`
- Viewport: `1920×1080`
- Screenshots:
  - `1920-property-browse-after.png`
  - `1920-property-manage-after.png`
  - `1920-column-popover-after.png`
- Verification Commands:
  - `cmd /c npm run agent:check`
  - `cmd /c npm run test:ui`
  - `cmd /c npm run build`
  - `python -m pytest tests/test_timeline_api.py tests/test_date_utils.py`
  - `cmd /c npm run qa:visual-fixture`
- Notes:
  - DOM snapshot 已验证属性 Tab 浏览态只剩 1 个“属性”标题源，不再有内层重复组头。
  - 浏览态可见 DOM 中不再出现“切换到此笔记本”。
  - 管理态和中栏列设置弹层的 DOM snapshot 都已验证类型下拉不再包含“邮箱/电话”。
