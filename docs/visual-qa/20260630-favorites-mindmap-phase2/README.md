# Visual QA — Favorites Tab + Mindmap Phase 2

- Date: 2026-06-30
- Task: 按 `docs/favorites-tab-and-mindmap-phase-2-plan.md` 验证收藏工作台、X6 连线样式分层、toolbar 新增子节点、节点侧边 `+`、以及刷新后的持久化。
- URL:
  - `http://127.0.0.1:8798/?topic=1&event=1&mode=edit`
  - `http://127.0.0.1:8798/?topic=5&event=1138`
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

- 收藏工作台在 `收藏数 = 1` 与 `当前笔记本收藏 = 0` 两种状态下都保留四段结构，不再退化成单句文案。
- 来源笔记本过滤会把中栏上下文切到 `来源笔记本 · 党史`，并显示清空筛选按钮。
- 最近收藏中出现 mindmap 行后，点击可直接回到 `event=1138` 的导图画布。
- 以同一拖拽场景对比 `圆角 / 直角 / 平滑曲线 / 贝塞尔` 四种线型，无 console error。
- `新增子节点` toolbar 按钮与节点侧边 `+` 都能创建子节点。
- 刷新后保留 `贝塞尔` 线型和新增节点。

Data discipline:

- Browser QA 复用了任务前已存在的 `127.0.0.1:8000` backend。
- 为验证“最近收藏 -> mindmap”路径，临时把 `topic=5,event=1138` 设为收藏，并在 QA 结束后恢复为未收藏。
- 同一导图上的临时拖拽与新增子节点也在 QA 结束后通过 API 恢复为原始三节点状态。

Artifacts:

- `1920-favorites-tab.png` — 收藏工作台全量状态（含来源笔记本、最近收藏与 mindmap 最近项）
- `1920-mindmap-rounded.png` — 默认圆角线型，拖拽后基准画面
- `1920-mindmap-polyline.png` — 直角线型
- `1920-mindmap-smooth.png` — 平滑曲线线型
- `1920-mindmap-bezier.png` — 贝塞尔线型
- `1920-mindmap-add-child-toolbar.png` — toolbar 新增子节点
- `1920-mindmap-add-child-side-plus.png` — 节点侧边 `+` 新增子节点
