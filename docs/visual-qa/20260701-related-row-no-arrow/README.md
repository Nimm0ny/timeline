## 任务

右栏“关联事件”列表项在阅读态去掉右侧箭头，编辑态保留删除按钮。

## 验收环境

- 默认 fixture 校验：`http://127.0.0.1:8798/?topic=1&event=1&mode=edit`
- 目标 UI 状态：`http://127.0.0.1:8798/?topic=1&event=9&mode=view`
- 编辑态对照：`http://127.0.0.1:8798/?topic=1&event=9&mode=edit`
- Viewport: `1920×1080`

## Screenshot

- `1920-view-after.png`
- `1920-edit-after.png`

## 验证命令

- `cmd /c npm run qa:visual-fixture`
- `cmd /c npm run agent:check`
- `cmd /c npm run build`
- `cmd /c npm run test:ui`
- `python -m pytest tests/test_timeline_api.py tests/test_date_utils.py`

## 视觉与交互结论

- 阅读态：关联事件行仍可 hover 预览、点击跳转，但 `.lrow-act` 不再渲染，右侧箭头已移除。
- 编辑态：关联事件行的删除按钮仍保留，右侧继续显示垃圾桶。
- 这次用 `event=9` 验证，是因为默认 fixture 的 `event=1` 本身没有“关联事件”区，无法覆盖目标元素。

## 已知偏差

- 无。
