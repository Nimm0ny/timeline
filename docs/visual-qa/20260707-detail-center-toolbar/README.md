# 视觉 QA · 2026-07-07 · 中栏/右栏互换 + 右栏加宽 + 工具条图标分组 + 拖拽互换手势

## 任务

用户 2026-07-07 请求：①中栏/右栏可自由切换位置；②右栏可调宽度上限放大；③各功能 SVG 图标分组避免混乱；④（追加）鼠标按住工具条空白区拖拽即可互换中/右栏。

对应设计：`docs/layout-swap-design.md` §7（detailPosition 旋钮）、`docs/pane-swap-drag-design.md`（拖拽手势）。

## 固定 URL / 视口

- URL：`http://127.0.0.1:8798/?topic=1&event=1&mode=edit`
- 视口：`1920×1080`
- 后端：`python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8010`（用户 :8000 被占用，改 :8010）
- QA server：`TIMELINE_BACKEND_URL=http://127.0.0.1:8010 npm run qa:visual-server`

## 截图

| 文件 | 状态 |
|---|---|
| `1920-edge-edit-after.png` | 贴边（edge）默认布局 · 编辑态基线（功能栏｜列表｜详情） |
| `1920-drag-ghost.png` | 拖拽中 · 未 armed（ghost「笔记详情」跟手，目标高亮未亮） |
| `1920-drag-armed.png` | 拖拽越过 feed 中线 · armed（feed 区淡紫落点高亮 + 内描边） |
| `1920-center-after.png` | 松手提交后 · 居中（center）布局（功能栏｜详情｜列表） |
| `1920-edge-after.png` | 反向拖拽回贴边（edge），与基线一致 |

## 验证命令（全过）

- `npm run agent:check` → AGENTS guard passed (47 files)
- `npm run build` → 构建通过
- `npm run test:ui` → 179 tests pass（含新增 `paneSwapDrag.test.js` 17 条）
- `python -m pytest tests/test_timeline_api.py tests/test_date_utils.py` → 20 passed

## 交互验收（playwright-cli，真实 pointer 事件，全过）

- 提交路径：按住 `.actionbar` 空白 → 越 feed 中线松手 → `detail-center` 类 + grid `268/412/1240` + localStorage=`center` + 后端 `PUT /api/config` 持久化（刷新保持）。
- 取消路径：未过中线松手 → 布局与持久化零变化（armed=false）。
- Esc 取消：armed 后按 Esc → 不提交、ghost 消失。
- 竖向意图：按下后竖移 → 不起手（`pane-dragging`=false）。
- 按钮不受扰：点右栏收藏星标正常切换 favorite、不起手。
- 反向：center 态拖中栏空白回中线 → 翻回 `edge`。
- 右栏收起：`right-closed` 时按住中栏空白拖动 → 不起手（手势禁用）。
- 右栏加宽：右 resizer 拖到极限 → 详情宽 960px（旧上限 560），feed 保底 692px。
- console：0 error / 0 warning。

## 已知偏差 / 说明

- armed 落点高亮填充由 `--accent-soft`(10%) 调为 `--accent-soft-2`(16%)：QA 发现大面积落点在浅底上 10% 偏弱，16% 仍为既有 active 态令牌、非新造色（已同步 `docs/pane-swap-drag-design.md` §2.2）。
- `1920-drag-*` 截图为真实拖拽中间态，非稳态；ghost chip 跟手位置 = 指针 +14/+14。
- 手势仅桌面 + 鼠标 + 右栏展开时启用；移动端/触摸不加载，零影响。
- 关联预览锚点在四种 2×2 形态下按详情实际 span 计算（`relatedPreviewPosition`），本次未逐一截图，靠单测几何覆盖。
