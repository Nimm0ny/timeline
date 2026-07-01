## 任务

右栏属性区分割线与属性区高度拖拽线合并为同一条视觉线。

## 固定验收环境

- URL: `http://127.0.0.1:8798/?topic=1&event=1&mode=edit`
- Viewport: `1920×1080`
- Screenshot: `1920-edit-after.png`

## 验证命令

- `cmd /c npm run agent:check`
- `cmd /c npm run build`
- `cmd /c npm run test:ui`
- `python -m pytest tests/test_timeline_api.py tests/test_date_utils.py`
- `cmd /c npm run qa:visual-fixture`

## 视觉与交互结论

- 属性区与正文区之间只保留拖拽分隔条这一条线，不再额外叠加 `.body-wrap` 的顶部分割线。
- DOM 检查：`.body-wrap` 的 `border-top-width = 0px`，`margin-top = 0px`。
- 交互检查：拖拽 `.detail-meta-divider` 后属性区 `maxHeight` 从 `266px` 变为 `306px`；双击后重置为 `176px`。

## 已知偏差

- 无。
