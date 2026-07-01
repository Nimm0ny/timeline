# Visual QA — Mindmap Toolbar Polish

- Date: 2026-07-01
- Task: 验证思维导图工具栏图标居中、线型菜单移除 `贝塞尔`、节点四边 `+` 改为仅 hover / 选中时显示。
- URL:
  - Fixture gate: `http://127.0.0.1:8798/?topic=1&event=1&mode=edit`
  - Mindmap QA: `http://127.0.0.1:8798/?topic=5&event=1138`
- Viewport: `1920×1080`

Commands:

```bash
cmd /c npm run agent:check
cmd /c npm run build
cmd /c npm run test:ui
python -m pytest tests/test_timeline_api.py tests/test_date_utils.py
cmd /c npm run qa:visual-fixture
cmd /c npm run qa:visual-server
```

Checks:

- 首屏打开导图时，四边 `+` 默认不显示。
- 点击根节点后，四边 `+` 全部出现。
- 连线样式菜单只剩 `直角 / 圆角 / 平滑曲线` 三项。
- 工具栏主新增按钮图标几何居中：`26×26` 热区内，`16×16` 图标偏移约 `x=5, y=5`。
- Browser console 无 error / warn。

Artifacts:

- `1920-mindmap-toolbar-default.png` — 初始态，无四边 `+`
- `1920-mindmap-toolbar-selected.png` — 选中根节点后显示四边 `+`，工具栏只保留三种线型
