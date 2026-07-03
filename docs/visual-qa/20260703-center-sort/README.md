# Visual QA · 中栏排序功能

- **任务**：中栏排序（docs/center-sort-design.md）——每视图差异化排序 + 一份 `{field, dir}` 状态（方向通用·字段夹取）+ localStorage 按笔记本持久化。
- **固定 URL**：`http://127.0.0.1:8798/?topic=1`（笔记本「党史」，56 条，1840→2021）
- **视口**：`1920×1080`
- **验证命令**：
  - `node --test "ui/tests/*.test.js"` → 141 pass（含新增排序单测）
  - `node tools/qa/agent-guard.mjs` → passed (46 files)
  - `npm run build` → built，exit 0
  - `node tools/qa/visual-fixture.mjs` → fixture 有效

## 截图

| 文件 | 状态 |
|---|---|
| `1920-timeline-asc-before.png` | 时间线默认（时间正序，近代中国→…） |
| `1920-timeline-sort-popover.png` | 时间线排序 popover：仅「时间正序 / 时间倒序」两行（分组视图=方向） |
| `1920-timeline-desc-after.png` | 时间线时间倒序（新时代 2021 在顶，era 组与组内均反转） |
| `1920-table-sort-popover.png` | 表格排序 popover：时间/标题 + 全部可见自定义列（类型/标签/新属性…）；创建/更新为 list/gallery 专属，表格不列（doc §4，每列都有列头 caret） |
| `1920-table-title-desc.png` | 表格按「标题」降序（点列头翻转，与菜单同一状态） |
| `1920-list-sort-popover.png` | 列表排序 popover：仅 4 个通用字段，无自定义列 |

## 驱动验证结论（真实 DOM，非“看起来差不多”）

- **时间线倒序**：era 顺序 `近代中国/新文化运动/共产主义小组`（正序）→ `新时代/社会主义改革开放建设时期/会议`（倒序）——组序 + 组内序均反转。
- **持久化**：`localStorage.tl-sort:1 = {"field":"time","dir":-1}`；刷新后 era 顺序仍为倒序（按笔记本存，非数据契约）。
- **方向通用·字段夹取**（4 段切换全部正确）：
  - 时间线(time,-1) → 表格：保持 (time,-1)。
  - 表格选「标题」→ (title,1)；点「事件」列头翻转 → (title,-1)。
  - 表格 → 列表：保持 (title,-1)（title 在列表有效）。
  - 列表 → 时间线：title 不支持 → 夹取回 time，方向保留 (-1)（新时代仍在顶）。
- **表格列头 ↔ 排序菜单同一状态**：菜单选「标题」后「事件」列头显示 `is-sorted`+caret；点列头翻转写回同一 `tl-sort` 状态。
- **列表/画廊自定义列专属表格**：列表 popover 仅 4 通用字段，无 类型/标签。
- **标题排序本地化**：升序 `《瑷珲条约》/《中俄北京条约》/安源…`；降序 `遵义会议/中共一大/…`（localeCompare "zh"）。

## §9 不变量

- **无横向溢出**：`documentElement.scrollWidth/clientWidth = 1920/1920`。
- **行高固定**：排序只重排，不触碰任何行高 CSS。
- **单一 popover 层**：排序并入 `activePopover`，与 时间定位/列设置/视图/新建 互斥。
- **纯图标**：`arrowUpDown`（已注册），经 `TimelineLucideIcon`，无散写 svg。
- **控制台**：0 error / 0 warning。

## 已知偏差

- 排序按钮仅桌面显示（`!mobile`）；移动端排序不在本期范围（另有断点基准）。
- 跨本收藏排序跟随其生效视图（= 上一笔记本的 display_style），页面与中栏用同一列集（`feedColumns=[]`）clamp；「收藏时间」字段 v1 不做（设计文档 §11）。
- 归档结束前已清除 `tl-sort:1`，恢复默认时间正序的出厂态。

## Review 修复（本次已闭环）

独立 subagent review 报 0 P0 / 3 P1，均已修复并加锁测试：
- **P1-1** `time` 排序在「更早」桶内丢失年代序（默认行为回归）→ 沉底分区补 `dateKey` tiebreak；新增 2-更早 单测。
- **P1-2** 表格菜单误列 创建/更新时间（违 doc §4 + 列头无 caret）→ 表格=时间/标题+可见自定义列；截图已重拍。
- **P1-3** 收藏的 `favorited` 为死代码（无视图暴露）→ 删除死机件，收藏跟随生效视图，doc 收敛。
- P2：删除列 fallback 保留方向；favorites 列集统一为 `feedColumns`。
复验：`node --test` 142 pass · guard passed · build ok · 表格字段重验 = 时间/标题/类型/标签/新属性/新属性2 · 时间线正倒序回归通过 · 0 console error。
