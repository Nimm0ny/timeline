# Visual QA — Property Tab Type Dropdown

- Date: 2026-07-01
- Task: 验证属性 Tab 去掉重复属性头部，只保留顶部属性行；并把 `单选 / 多选` 切换从 segmented toggle 改成顶部类型 chip 的下拉菜单。
- URL:
  - App QA: `http://127.0.0.1:5173/?topic=5`
- Viewport: `1920×1080`

Commands:

```bash
cmd /c npm run agent:check
cmd /c npm run build
cmd /c npm run test:ui
python -m pytest tests/test_timeline_api.py tests/test_date_utils.py
cmd /c npm run qa:visual-fixture
```

Checks:

- 打开左栏 `属性` Tab 后，点击属性行本体时，popover 只显示内容区，不再复制第二个 `类型 / 单选 / 0 项` 头部。
- 旧的 `单选 / 多选` segmented toggle 已移除。
- 点击顶部属性行里的 `单选` chip，只弹出一个下拉菜单。
- 对 option 属性，下拉菜单只显示 `单选`、`多选` 两项。

Artifacts:

- `1920-property-popover.png` — 属性内容 popover，重复头部已消失
- `1920-property-type-dropdown.png` — 顶部 `单选` chip 打开的下拉菜单，仅含 `单选 / 多选`
