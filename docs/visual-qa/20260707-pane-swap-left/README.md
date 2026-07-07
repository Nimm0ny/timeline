# 视觉 QA · 2026-07-07 · 拖拽互换 v2（左栏加入 + 阈值微调 + P2-2）

## 任务

在 v1（中/右栏拖拽互换 = `detailPosition`）基础上：①给左栏（功能栏）也加拖拽互换 = 切 `navPosition`；②微调提交阈值手感；③修复 P2-2（compact 桌面下 `rightWidth` 存储值可略超绘制值）。

设计：`docs/pane-swap-drag-design.md`（§1.1 v2 三栏模型、§3.2 分手势阈值）。

## 固定 URL / 视口

- URL：`http://127.0.0.1:8798/?topic=1&event=1&mode=edit`
- 视口：`1920×1080`
- 后端：`uvicorn backend.app.main:app --port 8010`（用户 :8000 占用）
- QA server：`TIMELINE_BACKEND_URL=http://127.0.0.1:8010 npm run qa:visual-server`

## 截图

| 文件 | 状态 |
|---|---|
| `1920-nav-left-baseline.png` | 功能栏靠左默认基线（功能栏｜列表｜详情） |
| `1920-sidebar-drag-armed.png` | 拖左栏「功能栏」越过视口中线 · armed（右缘落点条高亮 + ghost「功能栏」） |
| `1920-nav-right-after.png` | 松手提交后 · 功能栏靠右（详情｜列表｜功能栏） |

## 交互验收（playwright-cli 真实 pointer 事件，全过）

- **左栏拖拽提交**：抓 `.ph-title` 向右拖过视口中线(960)松手 → `nav-right` 类 + grid `412/1240/268` + localStorage `nav=right` + 后端 `PUT /api/config` 持久化。ghost「功能栏」跟手，落点条 `left:1652 width:268`（对侧外缘一条功能栏宽）。
- **未过中线不 armed**：x=600 时 armed=false；x=1000（>960）armed=true。
- **反向**：nav-right 态抓右侧 `.ph-title` 向左拖过中线 → 回 `nav=left`。
- **右栏收起仍可拖**：关详情后 `right-closed` 态，拖左栏 → 仍切 `nav-right`（grid `0/1652/268`）；`.ph-title` 光标恒为 grab（左栏互换不依赖右栏开合）。
- **右栏收起时中栏禁用**：`right-closed` 时 `.tl-bar .spacer` 光标 = auto（非 grab），feed 拖拽不启用。
- **阈值微调（中/右栏）**：拖详情到 x=1350 armed=false、x=1250 armed=true（旧「过对面中线」需拖到 x<888，现进入 feed 200px 即提交，少拖 ~360px）。
- console：0 error / 0 warning。

## 验证命令（全过）

- `npm run agent:check` → passed (47 files)
- `npm run build` → 构建通过
- `npm run test:ui` → 181 tests pass（`paneSwapDrag.test.js` 19 条：三栏 span、swapTarget、分手势 isArmed、gating）
- `python -m pytest tests/test_timeline_api.py tests/test_date_utils.py` → 20 passed

## P2-2 修复

`startResize` 在 `isCompactDesktop` 下把 `leftMax`/`maxRight` 收敛到与 `workspaceStyle` 绘制一致（左 240 / 右 380），存储值不再超过绘制值；宽桌面（无 compact clamp）仍走加宽公式 `max(560, min(960, 视口-左栏-480))`，无分歧。

## 已知偏差

- v2 沿用 v1 的 ghost/落点高亮令牌（`--accent-soft-2` 16% + `--accent-line` 内描边、28px 纸片、`--icon-menu` 图标）。
- 左栏 ghost 落点条只高亮「功能栏将去的对侧外缘」一条竖条（navPosition 提交会整屏镜像，但落点条传达关键信息「功能栏去这边」足矣）。
- 左栏抓手 = `.pane-head`/`.ph-title`（非交互标题标签），不夺排序/折叠/多选钮的既有交互。
