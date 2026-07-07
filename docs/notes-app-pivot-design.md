---
type: plan
status: implementing
owner: lhr
created: 2026-07-07
source: 用户 2026-07-07 会话（编年 pivot 成通用 markdown 笔记软件；模型 A；架构重定义为「数字图书馆」= 书架/容器(书·笔记本·相册)/笔记，容器类型定视图预设；W1 后端排序分页已落 `24a97ad`）
参考: docs/note-types-and-views-design.md（两轴模型）、docs/center-sort-design.md（排序语义 SSOT）、docs/loading-performance-design.md（虚拟化专项）、AGENTS.md §9（前端硬约束）
---

# 编年 · 通用笔记软件 Pivot 设计（Define-First）

> 本文件是「编年从时间线软件转向通用 markdown 笔记软件」的方向锚点与波次拆分。**timeline 从产品本体降级为视图之一。** 排序语义仍以 `docs/center-sort-design.md` 为 SSOT，两轴定义仍以 `docs/note-types-and-views-design.md` 为准，本文件只定方向 + 逐波边界。

---

## 0. 背景与拍板

- **现状**：编年是时间线优先形态——`Topic`（笔记本）容器 + `TimelineEvent`（条目，日期为身份核心），中栏默认时间线，左栏第三级是「分期(era)」。
- **2026-07-07 用户拍板 6 条方向**：
  1. **去时间化**：笔记不再以日期为身份核心；timeline 只是众多视图之一。
  2. **排序/分页后端化**：修掉倒序失效（现纯前端排序 + 后端只升序游标）并支撑规模化。
  3. **补链接系统**：`[[wikilink]]` + backlink + 悬浮预览，卡加载性能。
  4. **canvas 可嵌笔记**（Obsidian canvas 式），可加依赖、硬要求性能。
  5. **组织架构改 → 见下方「数字图书馆」重定义**（推翻早先「左栏文件夹树下钻到笔记」的想法）。
  6. **改表名**：`timeline_events`→`notes` 等全栈重命名（单独一波纯机械 rename）。
- **建模决策（已拍板）**：
  - **模型 A（Obsidian 式）**：`note_type` = 文档型 `{doc(markdown)、mindmap、canvas}`；集合视图 timeline/table/board/gallery/list/outline 是**容器级的视图镜头**（非可创建的笔记类型）。**保留现有两轴**，改动最小。（否决模型 B·Notion 式「视图也是笔记类型」。）
  - **「数字图书馆」架构重定义（2026-07-07，推翻早先「文件夹树下钻到笔记」）**：概念仍三级，但**左栏只显两级**，笔记（内容）落中栏——
    1. **书架**：整理容器，作用同文件夹。
    2. **容器**（level 2，有类型）：**笔记本 / 书籍 / 相册**，每种 = 一套**预设视图 + 默认视图**（§4 表）。左栏树到此为止。
    3. **笔记**（内容，level 3）：**不进左栏树**，在**中栏**按容器视图渲染集合；点开单条仍 doc→右栏无感编辑、mindmap/canvas→顶中栏。
  - **视图门控换血**：视图集由**容器类型硬定**（§4），**废除现有数据能力 gate**（`topic_capabilities`）——某视图暂无数据显空态提示而非隐藏；逃生口＝**容器类型可转换**（相册↔书↔笔记本）。
  - **不按容器约束笔记类型**：任何 `note_type` 可进任何容器；容器类型只管**集合怎么显示**。
  - 副产品：早先纠结的「929 笔记塞左栏树」「文件夹 vs 分组镜头」**自然消解**（笔记不进树）；左栏读模型反而变简单（去掉 era 第三级）。
- **Non-goals（本 pivot 全程）**：不动 CM6/markdown 正文引擎；不改单用户本地假设；不引入 alembic（仍走 `legacy_migration.py` 幂等 ALTER）。

---

## 1. 目标数据模型（方向，细节随波落地）

三级：**书架 Bookshelf → 容器 Container → 笔记 Note**。左栏树只到容器；笔记在中栏。

- **书架**（`Bookshelf`，现成表，基本不动）：容器的文件夹。
- **容器**（现 `Topic` 表，加类型）：
  - **`container_type`**（新，轴零）：`notebook` / `book` / `album`，决定**可用视图集 + 默认视图**（§4 表）。默认 `notebook` = 今日编年行为。
  - **`display_style`**（轴一，视图镜头）：当前激活视图，取值被 `container_type` 的视图集夹取。视图门控由**类型硬定**（§4），不再走数据能力 gate。
- **笔记为原子**（现 `TimelineEvent` 表，W6 改名 `notes`）：一条笔记 = 标题 + markdown 正文 + **可选**元数据（日期、属性、链接）。
  - **`note_type`**（轴二，模型 A）：`doc`（= 现 `entry`，markdown 正文）/ `mindmap` / `canvas`（新）。中栏选单条时按此渲染原生面。
  - **去时间化**：日期是**可选切面**、不是身份。schema 阻碍（W2 松绑）：`year / sort_key / era` 现 NOT NULL、无日期走「未定时间」兜底 → 转正为一等公民；默认序按容器类型（笔记本→time，书/相册→`updated desc`）。
  - **容器类型 ⟂ 笔记类型**：任何 `note_type` 可进任何 `container_type`；容器类型只管集合怎么显示。
- **链接**（W4）：写时解析 `[[ ]]` 落一张 links 表（source→target），backlink 查表、不运行时全文扫；**链接内部按 note-id 存、显示按标题**（改名/移动不断链），吃掉现有手动 `related_event_ids`；悬浮预览复用 `preview_text` + LRU 懒取。
- **canvas 嵌笔记**（W5）：嵌入节点引用 **note-id**（依赖 W4 寻址）；画布嵌入卡片懒渲染 + 视口裁剪。

---

## 2. 波次拆分（逐波验收，禁带病推进）

| 波 | 名称 | 范围 | 依赖 |
|---|---|---|---|
| **W1** ✅ | **后端排序分页** | feed 游标分页方向感知（升/降），修倒序失效 + 支撑规模化。已 commit `24a97ad` | 无 |
| **W2** ✅ | **容器类型 + 去时间化 + 左栏 2 级** | `container_type` 列 + 三类型视图预设（§4）+ 视图切换器按类型过滤 + 废数据能力 gate（换空态）+ 类型可转换；左栏砍到 2 级（书架→容器，去 era 第三级）；笔记去时间化（无日期转正）。已 commit `2a7b671`（默认序按类型 → 排序波，§4.3） | W1 |
| **W3** ✅ | **canvas note_type** | 自由画布 note_type（X6 快照存 `body_json`，镜像 mindmap 但**复用中栏结构化笔记机制** + 共享 X6 视觉原语，flat 图无树/布局/reparent）。**MVP**：自由卡片 + 连线（加卡/拖动/端口磁吸连线/双击改字/删/背景/文字色/撤销重做/全屏/跟随主题）+ 后端 `collect_x6_snapshot_text`（顺带修 mindmap 快照搜索暗坑）。**推迟**：图片/形状节点 · 卡片缩放/自动高度 · 滚轮平移 · 框选 · 笔记嵌入(=W5) | W2 |
| W4 | 链接系统 | `[[ ]]` 解析 + links 表（note-id 寻址）+ backlink 面板 + 悬浮预览（卡加载性能）。**详规 §5** | W2 |
| W5 | canvas 嵌笔记 | 嵌入节点引用 note-id + 懒渲染 + 视口裁剪。**详规 §6** | W3 + W4 |
| W6 | 改表名 | `timeline_events`→`notes` 等全栈机械 rename + 一次性迁移 | 独立、末位 |

虚拟化专项（`docs/loading-performance-design.md`）已由 codex 落地（`7bc2958`/`d738d5c`），建在 W1 方向感知 feed 之上。

---

## 3. W1 详规 · 后端排序分页（本波实现）

### 3.1 现状真相（2026-07-07 现场核实）

- 中栏 feed 走 `ensureTopicEvents`（游标分页，默认页 100）→ `GET /api/topics/{id}/events`。
- 后端 `query_topic_events`（`timeline.py:1689`）游标**只升序向前**（`date_key > cursor`），排序子句 `timeline_event_order_clauses()`（`timeline.py:1431`）**写死 `.asc()`**。
- 前端仅对**已加载事件**做 `filterEvents().sort(activeComparator)`（方向感知）。
- **根因**：方向对、但集合只有「最老的那批页」。大本子（topic=4=929）首屏只载最老 100，倒序只是把这 100 翻个个儿 → 体感「没有倒序」。`changeSort` 只改状态、不重取。

### 3.2 本波范围（明确边界，不过度）

- **做**：时间主排序**方向感知**（升/降）的后端游标分页——timeline/outline/list/gallery/board 的默认 time 排序在规模下正确；`dir` 变更时前端从第一页重取。
- **不做（后续波，显式记录，非静默截断）**：
  - 非 time 主排序（title/created/updated/收藏时间）在规模下的后端分页——仍走「对已加载集客户端排序」（= 今日行为，主要影响 table/list 大本），后续单列材化再补。
  - 自定义列（extra_json）排序的规模化——需材化，最难，最后。
  - 多级排序下沉后端——后端只认主级方向；次级 tiebreak 仍前端在已加载集内做。

### 3.3 后端改动

**`timeline.py`**

- `timeline_event_order_clauses(direction: int = 1)`：`date_key` 子句按方向 `.asc()/.desc()`；**「未定日期沉底」不随方向翻**（`case((date_key IS NULL,1),else_=0).asc()` 恒定）；`id` 恒 `.asc()` 作稳定 tiebreak。默认参数 `1` → 全部现有无参调用（`build_timeline_index`/`rebuild_search_index`/`build_related_lookup`/`list_topic_events` 等）**零行为变化**。
- `query_topic_events(..., direction: int = 1)`：
  - `order_by(*timeline_event_order_clauses(direction))`。
  - 游标 dated-row 比较按方向翻：`date_key < cursor_key`（降）/ `> cursor_key`（升）；`date_key IS NULL`（未定沉底）与 undated 游标（`id > cursor_id`）**两方向一致**。⚠ dated 比较**仅当 `cursor_key is not None` 才构造**（`null:<id>` 尾游标构造 `date_key < None` 会在 build 期抛错——review P0，已加守卫 + 测）。
  - `next_cursor` 生成不变（`f"{date_key or 'null'}:{id}"`，只记末行位置、方向无关）。

**`timeline.py` · `parse_cursor_key`（review P1，pre-existing 但 W1 依赖，一并修）**

- 游标的 date-key 段是服务端 mint 的**原始 `date_key` 整数**（`year*10000+month*100+day`），不是人类 `YYYYMMDD` 日期串。原 `parse_cursor_token` 走 `parse_query_date_key` 解析 → 年<1000（7 位 key）/BCE（负 key）resume 时 **400**、年<100（6 位 key）**静默错解**。改为 `int()` 解析，全年份 round-trip。**topic 4（含 BCE~2026）的降序 load-more 依赖此修才真能翻页**（否则首页之后即 400）。

**`topics.py`**

- `GET /api/topics/{id}/events` 加 `dir: int = Query(1)`；`direction = -1 if dir < 0 else 1` 传入 `query_topic_events`。默认 `1` = 今日行为，零回归。

### 3.4 前端改动

- **`useApi.js`** `getTimelineEvents(topicId, {cursor, limit, dir})`：`dir` 存入 query（仅 `dir < 0` 时 set `-1`，默认省略保持 URL 干净）。
- **`useTimelineStore.js`** `ensureTopicEvents(topicId, {..., dir})`：透传 `dir` 给 `api.getTimelineEvents`；`dir` 进 `requestKey`（force 重取 + 新 dir 视为独立请求，绕过去重）。
- **`TimelinePage.vue`**：
  - `feedFetchDir`（computed）= `activeSort` 主级 `field==='time'` 时取其 `dir`（clamp 后 timeline/outline 主级恒 time）；否则 `1`。
  - `ensureTopicEventsReady` / `loadMoreActiveTopicEvents` 调 `ensureTopicEvents` 时带 `dir: feedFetchDir.value`（load-more 复用同 dir 续游标）。
  - `changeSort`：改 `state.sort` 后，若 `feedFetchDir` 变了且非收藏模式且有活跃笔记本 → `ensureTopicEventsReady(activeTopicId, {force:true})` 从第一页按新方向重取。

### 3.5 验收

- **后端**：扩 `tests/test_timeline_api.py`——降序分页跨页正确、未定日期两方向恒沉底、`dir=1` 与旧行为逐行等价、游标续取不重不漏。`python -m pytest`。
- **前端**：`npm run agent:check` / `build` / `test:ui`。
- **手工**：dev server 实测 topic=4 时间线切倒序 → 首屏是**真·最新**、下滑 load-more 续更旧；切回正序恢复；小本子（≤1 页）两方向皆对。
- **Review gate**：触发（后端契约加 `dir` + 跨模块前端数据流 + 既有加载行为线）→ 独立 subagent review。**已跑**（后端 + 前端两独立 subagent，findings 全修 + 回归测）。

---

## 4. W2 详规 · 容器类型 + 去时间化 + 左栏 2 级

> **落地状态（2026-07-07）**：W2a 容器类型数据层 · W2b 视图门控换血 + 类型选择器 · W2c 左栏 2 级 · W2d 去时间化（无日期转正）**全部落地并过 review gate**（一处 P1 导入 round-trip 已修，见 §4.3）。§4.3 里三条「排序 / 默认」相关项**显式推迟到后续「排序波」**（依赖后端多字段排序）。左栏 era 死代码清理另挂 follow-up（review 确认 inert）。

### 4.1 容器类型 → 视图预设（FE/BE SSOT 常量）

| `container_type` | 可用视图（首=默认） | 气质 |
|---|---|---|
| **notebook** 笔记本 | 时间线 · 列表 · 大纲 · 表格 · 看板 | 时间导向（＝今日编年） |
| **book** 书籍 | 大纲 · 表格 · 列表 · 时间线 · 画廊 | 结构导向（章节/条目） |
| **album** 相册 | 画廊 · 看板 | 视觉导向 |

- **视图集硬定**：切换器只列该类型的视图，集外不提供。首个 = 默认视图（新容器 `display_style` 初值）。
- **废 `topic_capabilities` 数据能力 gate**：视图集固定，某视图暂无适用数据（如 book 无日期时的时间线、album 无图时的画廊）显**空态提示**（「加个日期就能看时间线」），**不隐藏**——更可预测，且删掉现有 capability 派生代码。
- **容器类型可转换**（相册↔书↔笔记本）：改 `container_type` → 视图集随之变；当前 `display_style` 若不在新集内，回落新集首个。这是内容长歪时的逃生口，替代软 ungate。
- 三类型先写死，`container_type` 存字符串保持可扩（将来「白板本」等）。

### 4.2 左栏 2 级 + 读模型简化

- 左栏树：**书架 → 容器**（2 级），**去掉 era 第三级**。容器节点显 `container_type` 图标（笔记本/书/相册不同 SVG）。
- `list_bookshelf_tree` 不再拼 era 行；`TopicEraStat` 仅供中栏 timeline 视图的 era 分组，不再喂树。左栏读模型**变轻**（不必再随树加载 era 聚合）。

### 4.3 去时间化（笔记）· 本波落地无日期一等公民；「排序 / 默认」拆到后续波

**本波已落地：**
- **无日期转一等公民**：写路径（`normalize_event_payload`）松绑——任何 `note_type`（含 entry/doc）可无日期，`date_key=None` / `sort_key=0.0` / `era` 可空。`era` 仅「有日期 entry」必填；**body 仍必填**（entry 是正文，不是日期）。判定「有日期」按**值非空**（present-but-null 也算无日期，和前端一致）。
- **编辑器清空日期→无日期**：`classifyEventDateInput`（纯函数）把三个日期框判成 dated / undated / partial；`EventDetailPane.submit()` 用它——整体留空 = 无日期（payload **不带** date keys）、半填报错、有日期才要 era。
- **导入 round-trip 修复（P1，review 抓出）**：导出把日期嵌在 `dateParts`、不发顶层 `dateYear`；松绑后 re-import 会把有日期 entry **静默变无日期**（原本是 loud 400）。`lift_import_date_parts` 在归一化前把 `dateParts`→顶层 date keys 提回，保真 round-trip（`test_export_import_round_trips_dated_entry` / `_keeps_undated_note_undated` 守）。
- **schema 未动**：无日期分支给安全默认，`year/sort_key/era` **不需** DROP NOT NULL（见 §4.4）。

**推迟到后续「排序波」**（都依赖后端多字段排序，塞本波会带病）：
- **默认序按容器类型**（notebook→`time asc`；book/album→`updated desc`）：`updated/created` 目前**只是前端排序字段**——W1 只把 *time* 排序后端化，非 time 排序按页在前端重排。设成类型默认 = 让 book/album **开箱即命中**那个规模化欠账，故等下一条落地再做。
- **`created/updated` 后端规模化排序**（真索引列 + 复用 `date_key` 游标套路）——上一条的前置。
- **按类型给新建默认日期 / 无日期**（笔记本填今日、书/相册默认无日期）：现新建仍默认填今日，无日期靠清空日期框触达；类型感知默认属同批 defaults 工作，一起推迟。

### 4.4 迁移（沿用 `legacy_migration` 幂等 ALTER）

- `ALTER TABLE topics ADD COLUMN container_type VARCHAR(32) DEFAULT 'notebook'` → 现有本子全＝笔记本，零回归。
- `year/sort_key/era` **无需改 schema**（落地发现）：无日期分支给安全默认（`sort_key=0.0`、`year`＝「未定时间」标签、`era=""`），`date_key` 本就可空 → 不必 DROP NOT NULL 或重建表。本波迁移只加 `container_type` 一列。
- ORM 同步加列；新库 `create_all`、存量幂等 ALTER。

### 4.5 API 契约 delta

- `topic_to_dict` / `TopicOut` 补 `containerType` + 由类型算出的 `views`（有序集）+ `defaultView`；替代 `topic_capabilities` 现成信号。
- `PUT /api/topics/{id}/meta` 收 `containerType`；转换类型时后端夹取 `display_style` 回落新集首个。
- 视图集/默认 = 类型的纯函数（FE/BE 同源）。

### 4.6 验收 / Review gate

- **pytest**：类型→视图集/默认纯函数、迁移幂等、类型转换夹取 `display_style`、无日期 entry 转正（含半日期 400 / 无 body 400）、导出→导入 date round-trip 保真。（默认序按类型、`created/updated` 后端排序分页 → 随「排序波」）
- **前端**：`agent:check` / `build` / `test:ui`；视觉 QA（左栏 2 级 + 三类型切换器 + 视图空态）。
- **Review gate**：触发（数据契约加列 + 左栏读模型改 + 视图门控换血）→ 独立 subagent review。

---

## 5. W4 详规 · 链接系统（`[[ ]]` + backlink + 悬浮预览）

> 依赖 W2（去时间化后笔记为一等公民、可按 id 稳定寻址）。本波未开工，先定边界。**承重决策已拍板（§5.1）：body 内存 note-id，非纯标题。**

### 5.1 寻址决策：id 锚定，非纯标题（性能 + 架构双判，已调研）

两类开源先例：
- **文件型 md（Obsidian / Logseq / Roam）**：body 存标题 `[[标题]]`，**改名时重写所有 backlink 源文件**（Obsidian「Automatically update internal links」）。被「.md 须人类可读/可移植」这个约束逼出来的传播式。
- **库型（Notion / Anytype）**：存**稳定 id + 显示缓存**，改名零传播、按 id 现查最新标题。

**编年是库型**——`body_markdown` 是 SQLite TEXT 列，不是磁盘 `.md` 文件，逼 Obsidian 走传播的约束不成立 → **走 Notion/Anytype 的 id 寻址**。性能判据（用户硬要求）决定性：

- 纯标题 + 传播：改名一个 hub = O(backlinks) 次 body 重写 + 每条 FTS 重索引 + read-model 重建 + **`updated_at` 级联污染刚上线的 `updated desc` 默认序**（改个标题→一堆不相关笔记跳「最近」顶部）。burst 写，卡顿雷。
- **id 寻址**：改名 = 单行 `UPDATE headline`；显示端按 id 走 `build_related_lookup` 现查。每根轴都赢。

**body token 形态** = `[[<id>|<别名>]]`（Obsidian `[[path|alias]]` 同形，path 槽放 id）。别名 = 人读显示 + 导出兜底 + 悬空标签。
- **Typora 手感补偿**：CM6 装饰在 caret 未真正进 token 时，连 `<id>|` 一并 conceal，只显 `[[别名]]`；caret 落进 token 才露完整 `[[<id>|别名>]]`（看/改绑定）。99% 时间 Typora-clean，改名又零成本。
- **导出可移植债**（记录，非本波）：导出纯 md 时走一道 render pass `[[id|别名]]` → `[[别名]]`。属独立场景，不拖累编辑/加载热路径。

### 5.2 解析时机：4 个不能混谈的时刻

| 时刻 | 在哪 | 触发 | 干什么 | I/O |
|---|---|---|---|---|
| **① 渲染** | CM6 ViewPlugin（镜像 `cmMarkdownLivePreview.js` 脚注 regex 段 650-701） | `docChanged/selectionSet/viewportChanged` | 可见行扫 `[[…]]`；caret 在内显原文、不在渲 atomic link widget（resolved=accent / dangling=muted） | 无 |
| **② 绑定 title→id** | CM6 autocomplete source（新引 `@codemirror/autocomplete`，CM6 例外簇内） | 敲 `[[` | 查候选（复用 FTS `search_events`，必要时 headline 加权变体）→ 选中插入 `[[id|别名]]` | 查询 |
| **③ 索引 →links 表** | 后端 create/update **写模型后**（id 已生成，紧邻 `upsert_search_index_row`；纯解析可提前在 `normalize_event_payload` timeline.py:1952 做） | create/update PUT | 抽 token → **diff 该 source 的 `wikilink` 行 → upsert/delete**，幂等 | 写 links |
| **④ 悬浮预览** | 前端 hover，懒 | hover widget | 取 target 预览弹卡 | 复用 `EVENT_PREVIEW_CACHE` |

- **一致性契约**：backlink 与 save 精确一致、与逐键实时最终一致——契合现有 autosave 节奏，链接图不逐键写。
- ② 候选源直接复用现成 FTS（`timeline_events_fts` / `search_events`），不新建索引。
- ④ 几乎零新代码：`buildEventPreview` + `EVENT_PREVIEW_CACHE`（LRU 2000, key 含 `updatedAt`）+ `RelatedEventPreviewPopover.vue` 全现成，从「关联事件」接到 `[[ ]]` widget。
- ⚠ ③ 的 DB diff 须在 `event.id` 存在后（create 走 autoincrement）→ 落在 `create_event`/`update_event` 写模型 + flush 之后，与 `upsert_search_index_row`/`rebuild_topic_read_models` 同段，非 `normalize_event_payload` 内。

### 5.3 数据模型 · 新表 `timeline_links`（SQLite-first）

```
timeline_links(
  id INTEGER PRIMARY KEY,
  source_event_id INTEGER NOT NULL,           -- 含 [[ ]] 的笔记
  target_event_id INTEGER,                     -- 解析到的 id；NULL = 悬空/未创建
  target_title    TEXT NOT NULL,               -- 别名（显示兜底 + 悬空标签）
  anchor_type     VARCHAR(16) DEFAULT 'wikilink', -- wikilink | manual(backfill) | embed(W5 canvas)
  position        INTEGER,                      -- source body 内字符偏移（排序 / 跳转）
  context_text    TEXT DEFAULT '',              -- 预算好的周边行（backlink snippet，免回扫源 body）
  created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
)
索引: (target_event_id, source_event_id) · (source_event_id)
```

- **`anchor_type` 三态统一**：canvas 嵌入（W5）= 一条 `embed` 链接（canvas→被嵌 note）→ 被嵌 note 的 backlink 面板天然显「被嵌入于画布 Y」。W5 靠此表寻址（§2 依赖 W4 的由来）。
- 每类 writer 只碰自己 `source_id` 下自己 `anchor_type` 的行：doc save 管 `wikilink`、canvas save 管 `embed`、backfill 一次性建 `manual`。互不踩，diff-upsert 幂等。

### 5.4 吃掉 `related_event_ids`

- 一次性 backfill：`related_event_ids_json` → `timeline_links` 的 `manual` 行（老手动关系转 backlink 保留，**不动 body**）；守卫标记同 `TEXT_FIELDS_BACKFILLED_V1` 套路。
- `event_to_dict` 的 `relatedEvents` 面包屑改由 links 表算（`build_related_lookup` 换成按 links 查）；`related_event_ids_json` 列留一波做回滚兜底，W6 清。
- 前端 `EventDetailPane.vue` 「关联事件·N」段（1088-1135）→ 升级成 backlink 面板（§5.5）；手动关联入口去掉，正向关联改为 body 里打 `[[`。

### 5.5 backlink 面板落点：一组件两宿主

- **抽 `BacklinkPanel.vue`**，两处挂：
  - **doc** → 右栏 `EventDetailPane` 底部（就地 evolve 关联事件段）。
  - **canvas/mindmap** → 中栏全宽时，右栏转「笔记 inspector」（属性 + backlink），header badge 按需唤出。**backlink 唯一归宿 = 右栏 inspector**，跨类型一致。
- 默认折叠显计数；展开才拉 `GET /api/events/{id}/backlinks`（`WHERE target_event_id=?` 索引查，limit 50 + 「更多」）。
- 行 = 源标题 + 容器 chip + `context_text` snippet（预算好、免回扫源 body）+ hover 预览（复用 popover）。悬空/未创建单列 muted 子区。**正向链接不进面板**（在 body 内联）。

### 5.6 API 契约 delta

- `event_to_dict` 加 `linkTargets: {id: 最新标题}`（同 payload 一次 join，复用 `build_related_lookup`；widget 优先用它、退回别名、查不到 → 悬空）。
- 新 `GET /api/events/{id}/backlinks?offset=` → `[{sourceId, headline, container, contextText, anchorType}]`。
- `TimelineEventIn`（`common.py:33-52`）正文照旧传 `bodyMarkdown`，链接由后端从 body 抽——**不新增前端 links 字段**（body 是 SSOT，避免前后端双写不一致）。

### 5.7 迁移 / 验收 / Review gate

- 迁移：`legacy_migration.py` 幂等建表 + 索引（`CREATE TABLE / INDEX IF NOT EXISTS`）；ORM 加 `TimelineLink`；SQLite-first，不引 PG。
- pytest：token 解析（含 `|别名`、悬空、hand-typed 裸标题解析）、diff-upsert 幂等、backlink 查、related backfill、**改名后 backlink/显示不断**。
- 前端：`agent:check` / `build` / `test:ui`；CM6 `[[ ]]` 装饰读↔编辑零位移、autocomplete、hover 预览、悬空态。
- Review gate：触发（新表 + 写路径 hook + CM6 扩展 + 契约加字段）→ 独立 subagent review。

---

## 6. W5 详规 · canvas 嵌笔记（懒渲染 + 视口裁剪）

> 依赖 W3（canvas note_type）+ W4（links 表寻址）。本波未开工，先定边界。

### 6.0 W3 前置（canvas note_type，机械镜像 mindmap）

- 镜像 `MindmapSurface.vue` + `MindmapEditor.vue`：X6 graph、`body_json` snapshot、debounced save chain；`NOTE_TYPES` 加 `canvas`（timeline.py:50）；`TimelinePage.vue` render dispatch 加 `v-if="canvasNote"` 分支（在 `MindmapSurface` 前）。自包含版（空白画布 + 基本图形/连线/文本节点）先落，嵌笔记留 W5。

### 6.1 调研定调（tldraw 参照系，Obsidian Canvas 反面教材）

- **tldraw**：离屏 shape 用 `display:none` **隐藏而非 unmount**（保 iframe / 有状态内容）；按 zoom 缩 LOD（`textShadowLod` 阈下停渲文字阴影）；CSS transform 走 pan/zoom 不触发 re-render；bounds-epoch 不变则跳过 cull 重算；R-tree 空间索引 O(log n) 查视口。
- **React Flow `onlyRenderVisibleElements` 坑**：可见时**重新初始化** node → 小/中图反而更慢；节点须 `React.memo`、别订阅整个 nodes 数组。
- **Obsidian Canvas 实测痛点（反面）**：①「节点进出视口逐个卡顿」= mount/unmount 抖动；②「嵌入项打开时卡死机器」= 无批量、开图即全量 full-render。**本波正是设计来规避这两条。**

### 6.2 4 档保真（静息态 = 预览）

| 档 | 内容 | 数据源 | 何时 |
|---|---|---|---|
| **T0 卡壳** | 边框 + 标题 + 容器 chip | 批量索引 `{id,title,container}` | 离屏 / 屏上太小 |
| **T1 预览** | `preview_text`(120字) | `buildEventPreview`（现成 LRU） | 视口内 + 可读缩放（**默认**） |
| **T2 全文** | `body_markdown` → 只读 HTML（复用读渲染器，**非** CM6） | `ensureEventDetail` 懒取 | 屏上够大 或 显式展开 |
| **T3 编辑** | 真 CM6 实例 | — | 双击激活，**全画布至多 1 个**，blur 降 T2 |

### 6.3 边界规则（促发 + 反抖 + 预算）

- **升 T1+** = (在视口 + margin ring) ∧ (屏上像素 = nodeW×zoom ≥ ~140px 可读阈)。T1→T2 需更大尺寸(~360px) 或显式展开。T2→T3 仅显式。（阈值实测调）
- **隐藏而非卸载**（照 tldraw）：出视口的卡 `display:none` / 降 T0，**保节点壳**——不 mount/unmount（避 React Flow re-init 坑 + Obsidian 抖动）。
- **反抖**：X6 pan/zoom 是 transform 非 scroll，IntersectionObserver 不触发 → **手动按 node bbox × graph transform 算可见集**，rAF-debounce 到手势结束再重算；手势中不动档。margin ring（如 +50% 视口，实测调）防小 pan 弹入弹出。
- **可见集集中判定**：surface 一遍算好、tier 当 prop 下发；卡组件 memo、不订阅全局 transform——照 React Flow「别让每节点订阅整数组」。
- **渲染预算（backstop）**：并发 T2 ≤ N（如 24）、T3 = 1，超出降 T1。tldraw 靠 cull 不设 cap 是因其静息态本就轻；我们 T2 是 full-markdown，故加软闸。**主策略是让 T1 够便宜使预算极少触发**，非靠 cap。

### 6.4 数据边界（分场景加载，接 W4）

- **开画布**：收集 `body_json` 全部嵌入 id → **一次 `POST /api/events/batch-preview {ids}`** → 灌 LRU → 全卡 T0/T1 即时。pan/zoom 零 fetch。
- 全文 T2 才逐卡 `ensureEventDetail` 懒取（detail cache）。**开图成本 O(1) round-trip，与嵌入数无关**——扛「硬要求性能」的关键。
- 规模逃生口（SQLite-first）：嵌入数破千再上内存 R-tree / 网格空间索引换线性 bbox 扫；本期线性即可。

### 6.5 一致性（id 寻址副产品，接 W4）

- 嵌入节点存 note-id：改名→标题现查刷新；移容器→仍按 id 解析；**删除→「笔记已删除」墓碑**（节点留、ref 悬空，不崩不消失）+「移除卡片」清理。同悬空 backlink 一个待遇。
- canvas save 写 `embed` links 行（§5.3）→ 被嵌 note 的 backlink 面板显「被嵌入于画布 Y」。

### 6.6 加载场景总表（「分场景够快」的兑现）

| 场景 | 成本 | 机制 |
|---|---|---|
| 中栏 feed 滚动 | 已虚拟化 | `[[ ]]` 仅样式化文本，不解析不 fetch |
| 开 doc（右栏） | ≈今日 + 1 join | detail cache；`linkTargets` 同 payload；backlink 不载 |
| hover `[[ ]]` | 首次 1 小请求 | 懒取 + LRU（重复 = 0） |
| 展开 backlink | 1 索引查(50) | `WHERE target_id=?` + 预算 snippet |
| 开 canvas | 1 batch 请求 | batch-preview 灌 LRU；T2 懒取；pan/zoom = 0 fetch |

### 6.7 依赖 / 验收 / Review gate

- 依赖例外：`@antv/x6-vue-shape`（Vue 组件当节点，承嵌入卡富内容），登记进 `AGENTS.md §9` X6 例外簇内。
- pytest：batch-preview 查、`embed` links 读写、墓碑（target 删）路径。
- 前端：`agent:check` / `build` / `test:ui`；**性能 QA 必做**——N=200 嵌入卡开图耗时、pan/zoom 帧率、进出视口无抖、T2 预算不超；归档 `docs/visual-qa/`。
- Review gate：触发（§9 依赖例外 + 新契约 + 性能基准）→ 独立 subagent review。
