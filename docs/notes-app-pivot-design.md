---
type: plan
status: implementing
owner: lhr
created: 2026-07-07
source: 用户 2026-07-07 会话拍板（编年从「时间线软件」pivot 成「通用 markdown 笔记软件」；模型 A + 书架/笔记本/笔记 文件夹树；第一波做后端排序分页）
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
  5. **组织架构改**：书架/笔记本/**分期** → 书架/笔记本/**笔记**；左栏文件夹树、笔记为叶子、不同 `note_type` 不同 SVG；中栏选笔记本=集合镜头、选单条笔记=其原生面。
  6. **改表名**：`timeline_events`→`notes` 等全栈重命名（单独一波纯机械 rename）。
- **建模决策（已拍板）**：
  - **模型 A（Obsidian 式）**：`note_type` = 文档型 `{doc(markdown)、mindmap、canvas}`；timeline/table/board/gallery/list/outline 是**笔记本级的视图镜头**（非可创建的笔记类型）。**保留现有两轴**（display_style × note_type），改动最小。（否决模型 B·Notion 式「视图也是笔记类型」，churn 过大。）
  - **文件夹树**：命名固定三级 **书架 / 笔记本 / 笔记**；左栏按可展开文件夹树呈现，笔记为带类型图标的叶子。（笔记本内是否再套子文件夹 = 后续 #5 波再抠，不挡第一波。）
- **Non-goals（本 pivot 全程）**：不动 CM6/markdown 正文引擎；不改单用户本地假设；不引入 alembic（仍走 `legacy_migration.py` 幂等 ALTER）。

---

## 1. 目标数据模型（方向，细节随波落地）

- **笔记为原子**：一条笔记 = 标题 + markdown 正文 + **可选**元数据（日期、属性、链接）。日期是**可选切面**，不是身份。
  - schema 阻碍（后续波松绑）：`TimelineEvent.year / sort_key / era` 现为 NOT NULL、无日期走「未定时间」兜底 → 需转正为一等公民。
- **note_type**（轴二，模型 A）：`doc`（= 现 `entry`，markdown 正文）/ `mindmap` / `canvas`（新）。中栏选单条笔记时按此渲染原生面。
- **display_style**（轴一，视图镜头）：timeline/table/board/gallery/list/outline，是笔记本集合的看法；timeline 仅在有日期笔记时可用（capability 门控已具备）。
- **组织**：Bookshelf → Notebook → Note 三级；左栏文件夹树。左栏第三级读模型从 `TopicEraStat`（era 聚合）改为笔记清单（分波实现，注意这会重写 `4fea71f` 的左栏优化）。
- **链接**：写时解析 `[[ ]]` 落一张 links 表（source→target），backlink 查表、不运行时全文扫；悬浮预览复用 `preview_text` + LRU 懒取。
- **canvas 嵌笔记**：嵌入节点存 note id（依赖链接寻址）；画布嵌入卡片懒渲染 + 视口裁剪。

---

## 2. 波次拆分（逐波验收，禁带病推进）

| 波 | 名称 | 范围 | 依赖 |
|---|---|---|---|
| **W1** | **后端排序分页（本波）** | feed 游标分页方向感知（升/降），修倒序失效 + 支撑规模化 | 无（与左栏树正交） |
| W2 | 去时间化 · 笔记转正 | `year/sort_key/era` 松绑、无日期一等公民、timeline 降为可选视图 | W1 |
| W3 | 组织架构 · 左栏文件夹树 | 左栏第三级 era→note、笔记叶子 + 类型 SVG、中栏双角色路由；左栏读模型重写 | W2 |
| W4 | canvas note_type | 镜像 mindmap（body_json + 宽画布），自包含版先落 | W2 |
| W5 | 链接系统 | `[[ ]]` 解析 + links 表 + backlink 面板 + 悬浮预览 | W2 |
| W6 | canvas 嵌笔记 | 嵌入节点引用 note id + 懒渲染 | W4 + W5 |
| W7 | 改表名 | `timeline_events`→`notes` 全栈机械 rename + 一次性迁移 | 独立、末位 |

虚拟化专项（`docs/loading-performance-design.md`）继续推进，但**必须建在 W1 的方向感知 feed 之上**——否则会把「只能升序」钉死。

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
- **Review gate**：触发（后端契约加 `dir` + 跨模块前端数据流 + 既有加载行为线）→ 独立 subagent review。
