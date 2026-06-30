---
type: plan
status: define-first
owner: lhr
created: 2026-06-29
source: 用户 2026-06-29 会话拍板（两轴模型 + 思维导图画布 + 视图扩容）；2026-06-30 导图内核切换为 AntV X6
参考: D:/py_pj/sikao/docs/plan/sik-375-note-tab-redesign-*.md（反向参考，方向不同：本项目保留 CM6/markdown，Topic 不改名，单用户无 user_id）
---

# 编年 · 笔记类型 + 展示视图 设计（Define-First）

> 本文件只定义**数据边界与方向**。前端视觉/交互真相仍以 `docs/obsidian-minimal-implementation-spec.md` + `prototypes/timeline-obsidian-minimal.html` 为准；属性列契约以 `docs/property-system-design.md` 为准。
> 真相源（已现场核实 2026-06-29）：① `backend/app/models/entities.py`（Topic / TimelineEvent）② `backend/app/schemas/common.py:22`（ColumnDef）③ `backend/app/services/timeline.py`（COLUMN_TYPES / DEFAULT_TOPIC_COLUMNS / normalize）④ `backend/app/services/legacy_migration.py`（启动期幂等 ALTER 迁移；本项目**无 alembic**）。

---

## 0. 背景与目标

- **现状**：编年是单一时间线形态——`Topic`（专题=笔记本）容器 + `TimelineEvent`（条目）唯一笔记形态，中栏只有时间线一种展示。
- **方向（用户 2026-06-29 拍板）= 两个正交的轴**：
  - **轴一 · 展示视图（display_style）**：把「条目类」笔记的同一份数据，渲染成多种视图——`timeline / table / board / gallery / list / outline`。它们**数据结构同源**，所以是同一类型的不同显示模式，按数据能力（capability）enable/disable 切换。
  - **轴二 · 笔记类型（note_type）**：同一个笔记本可**混装不同类型的笔记**。当前两类：`entry`（条目，markdown 正文，走轴一各视图）+ `mindmap`（思维导图，节点树，自带画布）。未来可扩（白板/表格文档…）。
- **Goal**：定义支撑「笔记本 → 混装多类型笔记 → 条目类可切多视图 + 思维导图独立画布」的数据模型、迁移、依赖例外与落地波次。
- **Non-goals**：① 不动 CM6/markdown 正文引擎（编年命根子，区别于 sikao 的 TipTap 决定）。② 不改 `Topic` 表名/不引入 user_id（本地单用户）。③ 思维导图的协作/版本/历史（后议）。④ 移动端形态（桌面优先，以 `docs/mobile-web-design.md` 断点为准，本期不专门重排）。

---

## 1. 现状基线（约束）

- `Topic.columns_json`（列定义）+ `TimelineEvent.extra_json`（每条列值）+ `ColumnDef`（9 类型 `text/number/date/checkbox/url/email/phone/select/multiselect`）= **自定义列/可切视图的现成契约**，轴一几乎零地基成本。
- 默认列 `DEFAULT_TOPIC_COLUMNS` = `type`(select) + `tags`(multiselect)（`timeline.py`）。
- 正文 = `body_markdown`（CM6/Typora 源码级 live-preview）—— **保留不动**。
- 所有结构化字段都以 **JSON-as-TEXT** 存：`columns_json / extra_json / attachments_json / related_event_ids_json` 皆 `Text` 列。
- **迁移机制**：`legacy_migration.py` 在 `@app.on_event("startup")` 跑 `Base.metadata.create_all` + 一串**幂等 `ALTER TABLE … ADD COLUMN`**（检测列缺失才加）。新增列沿用此模式即可，**无 alembic**。

---

## 2. 数据模型

### 2.1 `Topic` 加 1 列

| 新列 | 类型 | 说明 |
|---|---|---|
| `display_style` | `String(32)` default `'timeline'` | 笔记本「条目类」的默认/当前展示视图（§3 枚举）；纯前端切换时也持久化回此列 |

### 2.2 `TimelineEvent` 加 2 列（判别 + 结构化正文）

| 新列 | 类型 | 说明 |
|---|---|---|
| `note_type` | `String(32)` default `'entry'` | 笔记类型判别：`entry`（条目）/ `mindmap`（思维导图）；未来可扩 |
| `body_json` | `Text` nullable | 结构化正文（按 `note_type` 解释）；`mindmap` = X6 snapshot JSON（`cells/background/view/layout`，兼容读取 legacy tree / simple snapshot）；`entry` 留空走 `body_markdown` |

- `entry`：正文走现有 `body_markdown`（不动 CM6）；`body_json` 为 null。
- `mindmap`：正文走 `body_json`（整树 JSON）；`body_markdown` 为空。
- `date_* / era` 对 `mindmap` **可选**：带日期→在条目视图里作为单节点露面；不带→只在笔记本「全部/列表」里作为一项，不进时间线。
- ⚠ 表名仍叫 `timeline_events`（现在装多类型笔记）——**刻意不改名**（全栈引用面大、改名纯churn高风险），属已知 cosmetic 债。

### 2.3 为什么 SQLite 没问题（回应「会不会还是不支持」）

1. 树=JSON 字符串存 `Text`，和现有 4 个 `*_json` 列同款；SQLite TEXT 上限约 1GB，导图 KB 级。
2. 迁移=在 `legacy_migration.py` 现有幂等 ALTER 序列**加 3 行**（`display_style` / `note_type` / `body_json`），全 nullable+默认 → 老行零破坏回填，和当年加 `extra_json` 一模一样。
3. **不在 DB 里查树**：整图由 X6 snapshot 一次性 load/save，DB 当不透明 blob，不需要递归 SQL / JSON 函数；旧 simple snapshot 仅做读取兼容。

---

## 3. 轴一 · 条目类展示视图（display_style）

同一份条目数据，多种 display；`topic_capabilities()` 纯函数据笔记本数据能力 enable/disable（FE/BE 同源 SSOT；**性能要求：从 topic payload 现成信号即时算、零 round-trip，不每次扫全本聚合**，借鉴 sikao steer）。

| 视图 | capability（可用条件） | 实现要点 | 优先级 |
|---|---|---|---|
| `timeline` | 有 `date_key` | 现有中栏（era 分组 + 关联竖线 + `--rowgrid`） | 现有 |
| **`table`** | **永远可用**（列已在） | 去时间线竖脊 + 列头可排序，= Notion table；复用现有列渲染 | **先做** |
| `list` | **永远（兜底）** | 单列紧凑列表 | 随 table |
| `board` | 笔记本有 ≥1 `select` 列 | 按该列分组成看板列（党史「类型」列直接可用） | 次 |
| `gallery` | 有笔记带 `image_id` | `image + headline` 卡片网格；无图占位 | 次 |
| `outline` | 有 `era` | `era → event` 两层缩进大纲 | 末 |

- 切换器落在中栏 tl-bar（现有「列设置/显示预览」一排）；disabled 态对不满足 capability 的视图置灰 + tooltip 说明缺什么字段。
- 视图切换是前端状态 + 持久化 `Topic.display_style` 默认。

---

## 4. 轴二 · 笔记类型（note_type）

- **`entry`**（条目）：现有形态，`body_markdown`（CM6），走轴一各视图。
- **`mindmap`**（思维导图）：X6 snapshot（`body_json`），**自带画布**。
  - **编辑面**：点开占据**中栏/全屏宽画布**（右栏 412px 太窄，不走右栏无感编辑）；属于「不同类型=不同编辑面」的有意偏离。
  - **可选 date**：带日期则在条目视图露单节点（mindmap 图标），否则只在笔记本列表里作为一项。
- **新建笔记 = 类型选择器**（用户硬需求）：中栏「新建」由直接建时间点 → 先弹**类型选择**（条目 / 思维导图 / …），选 `entry` 落当前视图、选 `mindmap` 建空导图并打开画布。
- 收藏 / 回收站 / 搜索：两类笔记复用现有 `favorite` / `deleted_at` / 搜索通道（建议；§9 待确认 D-4）。

---

## 5. 依赖例外（撞 `AGENTS.md §9`「除 CM6 外不新增依赖」，已用户授权）

- **AntV X6**（`@antv/x6` + `@antv/x6-plugin-history` + `@antv/x6-plugin-selection`，MIT），提供自由坐标拖拽、连线自动跟随、原生历史栈；导图文件互通基线收敛为 app-native JSON + Markdown。
- 像 CM6 一样**登记为 baseline 第二个依赖例外**：落地时在 `AGENTS.md §9` 依赖项补一行；本文件即为当前决策记录。
- Vue3 集成：`onMounted` 初始化 X6 graph，`onUnmounted` dispose，`body_json` 持久化完整 snapshot；旧 bare tree / simple snapshot 在首次保存后迁移为 X6 snapshot。

---

## 6. API 契约 delta（对齐现有 REST）

- `GET/PUT /api/topics/{id}/meta`：TopicOut / TopicMetaUpdateIn + `displayStyle`；meta 携 `topic_capabilities` 现成信号（has_dated / has_select_col / has_image…）供前端零 round-trip 算可用视图集。
- `POST /api/topics/{id}/events` & `PUT /api/events/{id}`：`TimelineEventIn` + `noteType` + `bodyJson`（date_* 对 mindmap 可空）。
- 后端改完按现有约定跑 pytest；`extra_json` 校验/孤儿值沿用 `timeline.py` 现有 `normalize`/merge 逻辑，新列不参与列校验。

---

## 7. 迁移（沿用 legacy_migration 幂等 ALTER）

1. `ALTER TABLE topics ADD COLUMN display_style VARCHAR(32) DEFAULT 'timeline'`
2. `ALTER TABLE timeline_events ADD COLUMN note_type VARCHAR(32) DEFAULT 'entry'`
3. `ALTER TABLE timeline_events ADD COLUMN body_json TEXT`
- 全部 nullable/有默认；老数据：`note_type='entry'` / `display_style='timeline'` → **零行为变化**。
- ORM `entities.py` 同步加列；`Base.metadata.create_all` 负责全新库，幂等 ALTER 负责存量库。

---

## 8. Wave 拆分（逐波验收，禁带病推进）

- **W1 数据层**：3 列迁移 + ORM 同步 + `note_type`/`display_style` 常量 + `topic_capabilities` 纯函数（FE/BE 同源）+ 后端测试（迁移幂等 + 能力推导 + 默认值回填）。
- **W2 视图·表格（先做）**：中栏 display_style 切换器 UI + `table` 渲染器（复用列）+ `list` 兜底 + capability gate 置灰。
- **W3 视图·看板/画廊/大纲**：`board`（group by select）/ `gallery`（image grid）/ `outline`（era tree）。
- **W4 笔记类型·思维导图**：X6 集成（依赖例外登记）+ 新建类型选择器 + 宽画布编辑面 + `body_json` 读写 + 可选 date 联动 + mindmap 在条目视图的单节点呈现。
- **W5 打磨/互通**：X6 JSON / Markdown 导入导出、markdown ↔ 导图桥、笔记类型间的搜索/收藏/回收一致性收口；`.xmind` 若要恢复，需单列桥接项目。

---

## 9. 验收 / Review

- 每波：`npm run agent:check` / `build` / `test:ui` + `python -m pytest`（AGENTS §5）。
- 触发 review 条件齐（数据契约改动 + §9 依赖例外 + 视觉基准）→ 数据层与首个视觉视图各走**独立 subagent review**。
- 视觉视图按 `docs/agent-frontend-hardness.md` 做 1920×1080 QA 并归档 `docs/visual-qa/`。

---

## 10. 待 lhr 拍板（剩余小点）

| # | 决策点 | 推荐 |
|---|---|---|
| D-1 | 结构化正文列命名：通用 `body_json` vs 专用 `mindmap_json` | **通用 `body_json`**（未来类型复用，按 note_type 解释） |
| D-2 | 思维导图画布落点：中栏内嵌可全屏 vs 独立全屏路由 | **先中栏内嵌 + 可全屏**（复用现有壳，最小改动） |
| D-3 | 视图优先级：`table` → `board`/`gallery` → `outline`，`list` 随 table | 确认即按此 |
| D-4 | 思维导图是否共用现有 收藏/回收站/搜索 通道 | **共用**（复用 `favorite`/`deleted_at`/搜索，零新机制） |
