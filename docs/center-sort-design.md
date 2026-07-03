---
type: plan
status: define-first
owner: lhr
created: 2026-07-03
source: 用户 2026-07-03 会话拍板（中栏排序功能：localStorage 按笔记本持久化 + 默认保持正序 + 每视图差异化排序 + 自定义列排序=表格专属）
参考: docs/note-types-and-views-design.md（轴一展示视图定义）；docs/obsidian-minimal-implementation-spec.md + prototypes/timeline-obsidian-minimal.html（视觉/交互真相）；AGENTS.md §9（前端落地硬约束）
---

# 编年 · 中栏排序功能 设计（Define-First）

> 本文件只定义**中栏排序的数据边界、每视图行为与落地方向**。视觉/交互像素真相仍以 `prototypes/timeline-obsidian-minimal.html` 为准；轴一视图能力（capability）仍以 `backend/app/services/timeline.py` 为 SSOT。

---

## 0. 背景与目标

- **现状痛点**：中栏一切内容都锁死在「时间正序」（最老在上）。用户无法反转时间线（最新在上），也无法在列表/画廊里按标题、创建时间等维度重排。
- **Goal**：给中栏各视图一个排序入口，且**按视图的心智差异化设计排序功能与逻辑**（时间线只给方向、表格给列排序、列表/画廊给通用字段菜单），底层由**一份 `{field, dir}` 状态**统一驱动，按笔记本持久化到 localStorage。
- **Non-goals**：
  - ① 不改数据契约、不动后端、不加迁移（排序纯前端 + localStorage）。
  - ② 不引入"分组维度切换"（era/year/month）——那是 group-by，不是 sort，另议（§11）。
  - ③ 不做多级排序（primary + secondary）；v1 单键排序。
  - ④ 不改行高、不改视图切换器、不新增依赖、不新增图标。

---

## 1. 现状基线（约束）

已现场核实（2026-07-03）：

- **排序在三处各硬编码了一次 `compareTimelineEvents`（升序）**：
  1. `useTimelineStore.js` `replaceEvents/upsertEvent`（索引层基线序）。
  2. `TimelinePage.vue:filterEvents()` 末尾 `.sort(compareTimelineEvents)` → `visibleEvents`。
  3. `timelineNotes.js:groupTimelineEvents()` 内部 `.sort(compareTimelineEvents)` 再按 era 分桶。
- **表格视图早已有排序，但是个孤岛**：`TimelineFeed.vue` 组件内私有 `tableSort={key,dir}` + `setTableSort()` + `tableSortedEvents()`，点列头即排、再点翻方向。**不持久化、切笔记本 watch 重置、与其它视图完全割裂**，且它的"时间"排序用裸 `dateKey`，与 `compareTimelineEvents`（未定日期沉底 / 「更早」特殊位）**语义不一致**。
- **其余视图无排序入口**：timeline/outline 读 `props.groups`（era 分组）；list/gallery/board 读 `flatEvents()`（= 拍平 groups），全部继承升序。
- **已具备的地基（零成本复用）**：
  - `timelineNotes.js:compareEventsByColumn(column, dir)` 已处理 time / checkbox / 本地化文本值，泛化即可。
  - 索引事件**已携带** `createdAt / updatedAt / favoriteAt`（`backend/.../timeline.py:event_to_index_dict` → 序列化；`store.normalizeIndexEvent` 用 `...event` 透传）→ **按创建/更新/收藏时间排序零后端成本**。
  - localStorage 按笔记本持久化已有先例：`TimelineFeed.vue` 内置列宽 `COLUMN_WIDTH_STORAGE_PREFIX = "tl-colw:"`。
  - 工具栏单一互斥 popover 层 `activePopover`（''|locator|columns|views|newtype）可直接扩 `sort`。
  - 图标 `arrowUpDown / chevronUp / chevronDown / check` 均已注册。

---

## 2. 已拍板决策（本文件即决策记录）

| # | 决策 | 结论 |
|---|---|---|
| A | 持久化 | **localStorage 按笔记本**，key `tl-sort:{topicId}`，照搬 `tl-colw:` 套路；不进后端、不改数据契约 |
| B | 默认方向 | **保持时间正序**（`{field:'time', dir:1}`）= 今日行为；不悄悄反转任何人的时间线 |
| C | 每视图差异 | **入口、字段、逻辑三档分叉**（§4），非"分组 vs 扁平"两档 |
| D | 自定义列排序 | **表格专属**；list/gallery/board 只给 时间/标题/创建/更新 四个通用维度 |
| E | 状态统一 | 一份 `{field, dir}` 走全局；**方向通用、字段按视图夹取**（§3） |
| F | 收编表格 | 新控件与表格列头点击**读写同一份状态**，两者永不打架；顺带修 A/1 的时间语义不一致 |

---

## 3. 核心模型：有序 level 列表 + 方向通用·字段夹取

**状态**（页面所有，见 §6）—— Phase 2 后 `sort` 由单键升级为**有序 level 数组**（多级排序），并新增 `groupBy`：

```
sort = [{ field, dir }, …]                 // 有序 level：首个=主排序，其余=次级 tiebreaker
  field: 'time' | 'title' | 'created' | 'updated' | 'favorited' | '<自定义列 key>'
  dir:   1 (升序 / 正序) | -1 (降序 / 倒序)
  默认:  [{ field: 'time', dir: 1 }]        // 单级时间升序 = 与今日一致，零行为变化
groupBy: 'era' | 'year' | 'month'          // 时间线/大纲的分组维度（默认 era，仅分组视图用）
```

- 兼容：`normalizeSortLevels` 读取旧的单对象 `{field,dir}`（Phase 1 的 `tl-sort:` 值）自动包成单级数组，零迁移。
- `field` 在整串 level 里唯一（去重）；至少 1 级。

**方向通用、字段夹取**——切视图永不丢方向，每个 level 的字段能用则用、不能用则回落 `time`：

- 在**表格**里「类型 ↓, 时间 ↑」两级 → 切到**时间线** → 类型→time（主级方向 ↓ 胜出）、原 time 级去重，落成单级「时间降序」。
- 在**时间线**设「倒序」→ 切到**列表** → 列表继承「时间降序」。

由 `clampSortForView(sort, view, columns, favorites)` 纯函数逐 level 裁决：视图不支持的 `field → 'time'`、`dir` 原样保留；折叠后去重；已删除自定义列同样回落 `time`。

---

## 4. 每视图规格（入口 × 字段 × 逻辑）

| 视图 | 排序入口 | 可排字段 | 底层逻辑 |
|---|---|---|---|
| **timeline 时间线** | 工具栏 popover：**分组**[期/年/月] + **方向**[正序/倒序] | **仅 time**（+ groupBy） | 倒序 = **反转 era/年/月 组序 + 组内序**，分组结构不变（§5 沉底规则仍生效） |
| **outline 大纲** | 同时间线 | 仅 time（+ groupBy） | 同上（分组→event 两层整体翻转） |
| **table 表格** | **点列头**（主）+ 工具栏多级编辑器 | time / title / **所有可见自定义列** | 去分组，扁平按 comparator 排；**点列头=设为单一主排序（替换整串）**，点当前唯一排序则翻向（fork A） |
| **list 列表** | 工具栏多级编辑器 | time / title / created / updated | 去分组，扁平排（**不走 era 分桶**） |
| **gallery 画廊** | 工具栏多级编辑器 | time / title / created / updated | 同 list |
| **board 看板** | 工具栏多级编辑器 | time / title / created / updated | **桶内**按 comparator 排，**桶序（按选项）不动** |
| **跨本收藏（favorites）** | 工具栏多级编辑器（**恒扁平 list**） | time / title / **收藏时间** | Phase 2：收藏恒渲染成扁平 `list`；默认**收藏时间倒序**（最近收藏在顶）；持久化到 sentinel owner `tl-sort:favorites` |

> **多级排序（Phase 2）**：扁平视图的工具栏菜单是有序 level 编辑器——每级 `字段 + 方向 caret + 移除(>1 级时)`，底部「添加排序层」列未用字段。comparator 链式判定（主级先排，平手交次级），末尾统一 id tiebreak。列头 caret 对每个作为 level 的列都显示（多级在表头可见）。分组维度 `groupBy` 仅时间线/大纲可见。

三档差异的理由（= 用户"不同视图不同逻辑"的落点）：

1. **表格的排序入口天然是列头**（列都摆着，Notion 式肌肉记忆），菜单只是镜像；**列表/画廊没有列头可点**，必须靠工具栏菜单；**时间线/大纲连字段都不给**，只给方向。
2. **逻辑真的分叉**：分组视图是"反转分桶"、扁平视图是"绕开 era 分桶直接排"、看板是"只排桶内"——不是同一函数换参数。
3. **自定义列排序=表格专属**：list/gallery 里自定义列不作为列显示（只聚合成标签 chip + 日期），给"按类型排"却看不到"类型"列 = 按隐藏维度排序，迷惑。每个视图的排序菜单只承诺它自己看得见的维度。

---

## 5. Comparator 复用与泛化（`timelineNotes.js`）

新增/泛化三个纯函数，全部单测覆盖：

- **`compareEventsBySort(sort, columns)` → comparator**（泛化现有 `compareEventsByColumn`，不重写）：
  - `field='time'` → **走 `compareTimelineEvents` 的方向感知版本**（保留未定日期沉底 / 「更早」桶沉底语义，同时修掉表格裸 `dateKey` 的历史不一致）。
  - `field='title'` → `localeCompare(headline, 'zh')`。
  - `field='created'|'updated'` → `Date.parse` 时间戳。
  - `field=自定义列 key` → 复用 `compareEventsByColumn` 既有分型（checkbox 已选优先 / option 取 label / 文本数字取本地化值）。
  - 始终 `id` 兜底 tiebreak，保证等值行不抖动。
- **`sortFieldsForView(view, columns)` → 字段清单**：按 §4 表产出该视图可选字段（含 label/icon），驱动 popover 内容。
- **`clampSortForView(sort, view, columns)`**：§3 的方向通用·字段夹取裁决。

**⚠ 非显然的正确性要求（禁止 naive `* -1`）：**

> **空值与未定日期永远沉底，方向只作用于"有值区间"。** `time` 降序时，未定日期事件不得浮到顶部——它们没有时间，不是"最新"；应保持 `compareTimelineEvents` 的沉底语义（含「更早」桶仍在正常日期之后、未定日期之前）。`created/updated/favorited` 缺失时同样沉底，不随方向翻转。实现方式：先按 `hasValue` 分区（有值组恒在无值组之前），方向仅在有值组内套用。

---

## 6. 状态归属与数据流

- **页面所有** `state.sort`（`filterEvents`/`groupedEvents` 都在页面、都要 comparator，故状态必须上移到页面）。
- **数据流**：
  - 页面：`activeComparator = compareEventsBySort(clampSortForView(state.sort, feedDisplayStyle, columns), columns)` →
    `filterEvents()` 末尾 `.sort(activeComparator)`；`groupedEvents` 把 `dir`（或 comparator）传入 `groupTimelineEvents`，令 era 分桶按方向排（升序=最老 era 在上，降序=最新 era 在上）。
  - 传 `:sort` prop 给 `TimelineFeed`；`TimelineFeed` 扁平视图（table/list/gallery）用它对 `flatEvents()` 排、看板用它排桶内。
  - `TimelineFeed` 的**表格列头点击**与**排序 popover**都 `emit('change-sort', {field, dir})`；页面统一落 `state.sort` + 存 localStorage。
- **拆掉孤岛**：删除 `TimelineFeed` 内私有 `tableSort/setTableSort/tableSortedEvents` 与其 `watch(topicId)` 重置逻辑，改为纯 `props.sort` + `emit`。表格排序自此与全局同源（决策 F）。
- **组件分层合规**（spec §9）：业务判断（comparator/clamp/持久化）在页面/utils，`TimelineFeed` 只收 prop / emit。

---

## 7. localStorage 持久化契约

- key：`tl-sort:{topicId}`（前缀 `SORT_STORAGE_PREFIX = "tl-sort:"`，与 `tl-colw:` 并列）。
- value：`JSON.stringify({ field, dir })`。
- **读**：切笔记本（`watch(activeTopicId)`）时载入；解析失败 / 无记录 → 默认 `{time,1}`；`field` 引用已删除自定义列 → `clampSortForView` 回落 `time`。
- **写**：每次 `change-sort` 落 `state.sort` 后写入；存储禁用/满时静默降级（本会话仍生效），照抄 `saveBuiltinWidth` 的 try/catch。
- 单用户本地应用，无需跨设备同步；如日后要同步再走后端加列（§11），当前刻意不做。

---

## 8. 工具栏控件（UI）

- **一个纯图标按钮**（`arrowUpDown`，`stroke-width=1.5`）落在 `tl-bar` 的 `tl-actions` 内，紧邻视图切换器（同属"排列"控件族）；走现有单一互斥 popover 层 `activePopover='sort'`。
- **非默认排序时按钮点亮**（复用现有 `.on` 态）：即 `sort ≠ {time,1}` 时提示"当前不是时间正序"。
- **popover 内容随视图变**（`sortFieldsForView` 驱动）：
  - timeline/outline：两行方向项（`时间正序 ↑` / `时间倒序 ↓`），当前项打 `check`。
  - table/list/gallery/board：字段清单，每行 `字段名 + 方向 caret`；点非激活字段→按该字段排（默认升序），点激活字段→翻方向；激活行 `chevronUp/Down` 显示方向。（收藏跟随其生效视图，落入上述某一分支。）
- **表格列头**保留 caret（现已用 `chevronUp/Down`），点击改为 `emit('change-sort')`——与 popover 同一状态。
- **合规**：纯图标（§9 图标纪律）、令牌取色（§9 令牌纪律）、不改行高（§9 不变量）、mindmap 画布占中栏时整个 feed 被替换 → 排序按钮自然不在，无需特判。

---

## 9. 不变量与边界情形

- **无感编辑实时重排**：`applyPreviewOverlay` 后的行按 `activeComparator` 重排（今日按 `compareTimelineEvents`）；日期非法时不写排序键（现有保护保留），mid-typing 不乱序。
- **切笔记本**：`state.sort` 从 localStorage 重载并 clamp；表格不再自持状态，故不需要旧的 `tableSort` 重置。
- **视图切换**：`dir` 恒保留，`field` clamp（§3）。
- **跨本收藏模式**（`isGlobalFavoritesMode`）：排序跟随其生效视图（= 上一笔记本的 display_style；收藏无自定义列，故 `feedColumns=[]`，页面与中栏用同一列集 clamp/比较）；不持久化（无单一 owner 笔记本）。「收藏时间」排序 v1 不做（见 §11）。
- **§9 硬不变量**：自适应无 `scale`、全局禁滚动条、两栏默认、行高固定、右栏零位移——排序均不触碰。
- **能力门**：排序按钮对"条目类"视图恒显示；mindmap 画布态不显示（feed 被替换）。

---

## 10. 分波落地 + 验收 / Review

体量小（预计 3 文件、150–250 行含测试），三波可分可合，但**逐波对照原型验证，禁带病推进**：

- **W-sort-1 · comparator 地基**（`timelineNotes.js` + `ui/tests/timelineNotes.test.js`）：`compareEventsBySort` / `sortFieldsForView` / `clampSortForView`；单测覆盖 空值沉底·方向仅作用有值区·字段夹取·「更早」语义·自定义列分型。纯函数，先绿。
- **W-sort-2 · 状态与数据流**（`TimelinePage.vue`）：`state.sort` + localStorage 读写 + `activeComparator` + `filterEvents`/`groupedEvents` 接入 + `:sort`/`@change-sort` 布线 + 拆表格孤岛。
- **W-sort-3 · 工具栏控件**（`TimelineFeed.vue`）：排序按钮 + view-aware popover + 表格列头收编 + 非默认点亮态 + 扁平/看板套用 `props.sort`。视觉 QA 按 `docs/agent-frontend-hardness.md` 做 1920×1080 各视图截图并归档 `docs/visual-qa/`。

**验收**（AGENTS §5）：`npm run agent:check` / `build` / `test:ui`；后端未触碰，`pytest` 作回归 sanity。
**Review gate**：触发（改既有行为线=表格排序孤岛拆除 + 视觉基准）→ 起**独立 subagent review**，非自检。

---

## 11. 已落地（Phase 2）与未来

**Phase 2 已落地**（本文件 §3/§4/§5 已并入为准）：

- **分组维度切换 era/year/month** ✅：时间线/大纲 popover 的「分组」段；`groupBy` 状态 + `tl-groupby:{topicId}` 持久化；year/month 的 undated 归「未定时间」桶。
- **多级排序** ✅：`sort` = 有序 level 数组；链式 comparator + 单次末尾 tiebreak；扁平视图多级编辑器；列头点击=替换主排序（fork A）。
- **收藏时间排序 + 收藏恒扁平** ✅：收藏恒渲染 `list`，按 time/title/**收藏时间** 排，默认收藏时间倒序，落 `tl-sort:favorites`。

**仍未做**：

- **后端持久化 / 跨设备同步**：如日后要让 sort/groupBy 像 `display_style` 那样进 `Topic` 列，再走幂等 ALTER；当前 localStorage 足够且可逆。
- **拖拽重排 level / shift-click 追加**：多级顺序目前靠「移除+重加」，无拖拽；列头 shift-click 追加次级也未做（fork A 明确取舍为不做）。
