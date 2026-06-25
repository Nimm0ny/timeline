# 编年 Chronicle · Obsidian Minimal 三栏改版 — 详细实现设计（交付 Codex）

> 产品名：**编年（Chronicle）**。代码/仓库技术名沿用 `timeline`；UI 品牌名、文档标题用「编年」。（旧称「历史长河」仅为占位，全部替换。）
> 本文是把 `prototypes/timeline-obsidian-minimal.html` 落到生产代码（Vue 3 + FastAPI + SQLite）的逐项实现说明，**也是本改版的实现基准（baseline of record）**。
> **像素与交互真相 = 该原型文件**；与文字描述冲突时以原型为准。配套高层视觉稿见 `docs/obsidian-minimal-design-spec.md`。
> 实现代理（含 Codex）开工前必读：本文 + 原型 + `AGENTS.md` 第 9 节 + `docs/agent-frontend-hardness.md`。

## 0. 定位与范围

- 目标：用 Obsidian 极简风格重构现有三栏时间线笔记界面。
- 技术栈不变：前端 `Vue 3 + Vue Router 4 + Vite`，后端 `FastAPI + SQLAlchemy + SQLite`。
- 本改版**取代**冻结基准 `docs/00-mandatory-readonly-design-brief.md` 的若干裁决（见 §12 差异表）。Codex 落地时需同步更新该冻结文档，否则与 `AGENTS.md` 第 4 节裁决顺序冲突。
- 已定决策：单页自适应、三栏可拖拽、全局禁滚动条、强调色=紫、**本期不做深色**、中栏列表+关联时间线、行高固定+显示预览、列可自定义、左栏 Obsidian 风格、右栏默认折叠按需展开、无感编辑、附件 Modal、正文内联图片、关联事件跳转。
- 所有功能按键一律 **纯图标（SVG / Lucide）**，集中走 `ui/src/components/timeline-notes/TimelineLucideIcon.vue`。

## 1. 设计令牌（仅亮色；深色暂缓，token 可保留备用）

写入 `ui/src/styles/timeline-notes.css` 的 `:root`。原型已是最终值，直接照搬。

```
强调色   --accent:#7b68d9  --accent-hover:#6a56cf  --accent-contrast:#fff
        --accent-soft:rgba(123,104,217,.10)  --accent-soft-2:rgba(123,104,217,.16)  --accent-line:rgba(123,104,217,.34)
底色     --bg-app:#efeeec  --bg-sidebar:#f3f2f0  --bg-timeline:#faf9f8  --bg-detail:#fff
        --bg-surface:#fff  --bg-surface-2:#f5f4f2  --bg-hover:rgba(20,18,14,.045)
描边     --border:#e5e2dc  --border-soft:#edeae4  --border-strong:#d8d4cc
文字     --text:#2b2824  --text-strong:#1d1b18  --text-muted:#6f6a62  --text-faint:#a59f95
其它     --rail:#d8d2c8  --scrim:rgba(40,34,24,.34)  --shadow-pop:0 10px 34px rgba(30,24,14,.14)
布局变量 --left-w:268px  --right-w:412px
半径     --radius-lg:12  --radius:8  --radius-sm:6  --radius-pill:999
字体     --tn-font:"Noto Sans SC","PingFang SC","Microsoft YaHei","Segoe UI",sans-serif   （正文/标题，自托管 Noto Sans SC woff2 子集）
        --tn-font-num:"Segoe UI","Noto Sans SC","PingFang SC","Microsoft YaHei",sans-serif  （日期/数字，tabular-nums）
缓动     --ease:cubic-bezier(.32,.08,.24,1)
标签色   --t-war:#c05a52 --t-politics:#5f78c2 --t-culture:#b0863e --t-reform:#4f9488 --t-diplomacy:#8a6bc2 --t-economy:#6f9a4d --t-science:#4d8f9a
```

## 2. 全局规则

- **禁显滚动条（全局）**：`*{scrollbar-width:none;-ms-overflow-style:none} *::-webkit-scrollbar{display:none} html,body{overflow:hidden}`；各栏内部用独立可滚动容器。
- 图标线宽 `1.75`，视觉尺寸 16–18px，圆角圆端；按钮热区 26–34px。
- 字体锁定自托管 `Noto Sans SC`（SIL OFL）；子集外字符回退系统 sans 栈，不回退宋体/衬线。
- 命令按钮统一 `.iconbtn`（hover 浅底，`.on` 强调色软底，`.primary` 强调色实心）。

## 2.1 弹层（popover）与输入控件规范

所有浮层与输入框统一走以下规范，新增控件必须遵守，禁止每处各自造样式。

- **弹层容器**（`.popover` / `.meta-pop` / `.timeline-action-menu` 同款）：背景 `var(--bg-detail)`、1px `var(--border)` 边、圆角 `--radius-lg`、阴影 `--shadow-pop`、`z-index:40`、内边距 `6–8px`（密集表单类如列设置可用 10px）。标题用 `.pop-title`（11px、大写字距、`--text-faint`）。
- **分割线分组（强制）**：弹层内按语义分组，组间用分割线隔开——多组用 `.pop-section`（相邻组自动 `border-top:1px var(--border-soft)` + 间距），或用显式 `.pop-divider`（1px `--border-soft`，纵向 margin 6px）。破坏性操作（如永久删除）必须用分割线与普通操作隔开。
- **输入控件（强制无边框）**：`border:0`、底色 `var(--bg-surface-2)`、圆角 `--radius-sm`、字号 `13px`、最小高 `30px`、padding `0 10px`。聚焦：去 outline、底色提亮到 `--bg-surface`、加 `box-shadow: inset 0 0 0 1.5px var(--accent-line)`（聚焦环，非边框）。禁止 1px 实边框输入框，禁止让输入框继承浏览器默认 16px 字号。

## 3. 布局与外壳（自适应 + 可拖拽 + 右栏按需展开）

- 外层 `position:fixed;inset:0`，`display:grid; grid-template-columns: var(--left-w) minmax(0,1fr) var(--right-w);`，`transition:grid-template-columns .22s var(--ease)`（**展开/收起动画，保留**）。
- **默认两栏**：根容器带 `right-closed` 类 → 第三列宽度置 0，右栏内容裁切隐藏。点击中栏行 → 去掉该类（右栏展开）；右栏「关闭」按钮 → 加回该类（收起）。
- **拖拽**：左右各一根绝对定位 resizer（`#rzLeft left:var(--left-w)`；`#rzRight left:calc(100% - var(--right-w))`，`right-closed` 时隐藏）。拖动改写 `--left-w`/`--right-w`，**带 min/max**：左 `220–360`、右 `360–560`。
- 中栏内容 `max-width:1180px` 居中。
- 生产建议把 `--left-w/--right-w/right-open` 存 localStorage，刷新保持；窗口缩放只改内部滚动区高度。

## 4. 图标清单（Lucide）— 所有功能键

在 `TimelineLucideIcon.vue` 的 `icons` 映射登记下列名（原型用同形 SVG，已校验路径）。括号为 Lucide 组件名。

| 用途 | key | Lucide |
|---|---|---|
| 品牌/笔记本 | book / folder | BookOpen / Folder |
| 视图：全部/今天/本周/收藏/回收站 | library/calendar/clock/star/trash | Library, CalendarDays, Clock, Star, Trash2 |
| 笔记本节点 | notebook | NotebookText |
| 标签 | hash | Hash |
| 统计 | bar | BarChart3 |
| 搜索 | search | Search |
| 时间定位 | calendarSearch | CalendarSearch |
| 筛选 | filter | Filter |
| 列设置 | columns | Columns3 |
| 显示预览 | alignLeft | AlignLeft |
| 新建时间点 | plusCircle | CirclePlus |
| 新建笔记 / 新建笔记本 | squarePen / folderPlus | SquarePen, FolderPlus |
| 排序 / 全部折叠 | arrowUpDown / fold | ArrowUpDown, ChevronsDownUp |
| 展开折叠箭头 | chevronDown / chevronRight | ChevronDown, ChevronRight |
| 收藏/置顶/回收/保存 | star/pin/trash/save | Star, Pin, Trash2, Save |
| 阅读⇄编辑 | pencil / eye | SquarePen / Eye |
| 关闭详情 | x | X |
| 附件/图片/文件/下载/放大 | paperclip/image/file/download/maximize | Paperclip, Image, FileText, Download, Maximize2 |
| 关联跳转 | arrowRight | ArrowRight |
| 元信息：日期/专题 | calendar / leaf | CalendarDays, Leaf |
| 编辑器内联：标题/列表/链接 | hash/list/link | Hash, List, Link2 |
| 知识库切换/帮助/设置 | chevronsUpDown/help/settings | ChevronsUpDown, CircleHelp, Settings |
| 勾选（列设置） | check | Check |

> 深色切换图标（sun/moon）本期不接入。

## 5. 左栏：Obsidian 文件树（重写 `TopicSidebar.vue`）

结构 = `ribbon(44px) + pane(1fr)`；pane = `pane-head + pane-scroll + pane-foot`。

### 5.1 Ribbon（最左竖条）
- 顶部图标：品牌(book，紫底)、笔记本(folder，默认 active)、搜索(search)、收藏(star)、标签(hash)、统计(bar)；`flex:1` 间隔后底部：回收站(trash)。
- 单选高亮 `.rb.active`（强调色软底）。搜索点中展开中栏搜索框。生产可作为 pane 切换器（Files/Search/Tags/Stats）。

### 5.2 Pane Head（工具条）
- 左侧标题 `笔记本`；右侧纯图标：新建笔记(squarePen)、新建笔记本(folderPlus)、排序(arrowUpDown)、全部折叠(fold)。

### 5.3 Pane Scroll（分组文件树）
四个可折叠分组（`.tg`，组头 `chevron + 小标题大写 + 组内动作图标`，hover 露出动作图标）：

1. **视图**：全部笔记/今天/本周/收藏/回收站（`.ti.leaf`：图标 + 名称 + 计数）。语义沿用冻结基准 §3：均按当前 topic + 主筛选统计。
2. **笔记本**（文件树）：每个专题是可展开 `.ti.folder`（chevron + folder 图标 + 名称 + 计数），展开显示其**时代(era)** 子项（`.ti.leaf`，`--depth:1`，缩进 + 引导竖线）。子项点击=按 era 过滤中栏。`近代史` 默认展开，其余折叠。
3. **标签**：`.ti.leaf.tag`（色点 + 名称 + 计数），点击=按 tag 叠加过滤。
4. **统计**：仅 3 个 mini 数字（笔记 / 本周新增 / 收藏）。**已删除「标签分布」「年代活动」两个图表**。

行交互：`.ti` 单选 active（强调色软底）；folder 同时展开/收起子节点；分组 `.tg-head` 折叠；全部折叠按钮收起所有 `.tg`。

### 5.4 Pane Foot（底栏，左下角固定）
- 左：知识库切换 `chevronsUpDown + 历史长河`（vault-switch）。
- 右：帮助(help)、**设置(settings，固定产品设置入口)**。

### 5.5 数据来源
- 视图计数、专题列表、专题下时代、标签聚合、统计数字：现有 `topics` / `events` 数据可全部算出（events 已含 era、tags、favorite、deletedAt、createdAt）。
- props 扩展：`TopicSidebar` 现有 `topics/events` 足够；新增 `activeFilter / activeTag / activeEra`，emit 新增 `select-era`；保留 `create-event/create-topic/select-topic/update:filter/update:tag/open-settings`。

## 6. 中栏：列表 + 关联时间线（重写 `TimelineFeed.vue`，弃用卡片 `TimelineEventCard.vue` 改为行）

### 6.1 工具条
左：`历史事件` + `时间线 · 共 N 条`。右纯图标：搜索(展开输入)、时间定位、筛选、**列设置**、**显示预览**(默认 on)、新建时间点(强调色实心)。

### 6.2 列表结构
- 吸顶列头（`.tl-cols`，`grid-template-columns:var(--rowgrid)`，随激活列动态生成）。
- 按 **时代分组**：分组头 = 大圆点(强调色) + 时代名 + `起–止年份 · 条数`。
- 事件行 `.row`（grid 对齐）：`rdot | 时间 | 事件(标题 + 灰度预览 + 附件夹子) | [地点] | [类型] | [来源] | 标签色点 | ★`。
- **关联时间线**：每个 `.era` 一条连续脊线（`--rail`），行小圆点（空心→hover 描边强调色→active 实心）。

### 6.3 行高 + 显示预览（重点）
- 行高**固定** `min-height:33px`（= 不显示预览时的紧凑间距）。
- 「显示预览」切换 `:root[data-preview=on|off]`，仅控制 `.ev-sum` 显隐，**不改变行高**（预览与标题同一行内联省略）。
- 不再有「密度」概念。

### 6.4 列可自定义 —— **仅通用自助加列机制（已拍板 #3）**
不内置「地点/来源」等具体业务列；提供**通用机制**让用户自行加列。

- **内置列**（映射现有字段，无需 extra）：`事件标题`(必选) / `时间`(必选) / `类型`(由首个 tag 归类) / `标签`。后三者可在「列设置」显隐。
- **用户自定义列**（通用）：用户在「列设置 → 新建列」添加任意列：`key`(唯一)、`label`、`type`(text/number/date/select)、`width`、`order`、`visible`；可重命名/删除/排序/显隐。列定义按**专题(topic)** 存储（`columns_json`，§8.2）；每事件的列值存 `event.extra[key]`（§8.2）。
- 原型里出现的 `地点 / 来源` 只是**自定义列的演示样例**，不是内置列；某事件无该列值时显示占位 `—`，绝不臆造数据。
- 「列设置」浮层：内置列勾选 + 自定义列列表(显隐/编辑/删除) + 「新建列」。任一变更 → 重算 `--rowgrid`、列头、行单元。
- 行状态：hover 浅底；选中 = 左 `2px` 强调色竖条 + 软底 + 标题转强调色 + 圆点实心；收藏星标常驻(金棕)，未收藏 hover 可见。
- 分组粒度：本项目数据跨百年稀疏，用「时代」分组；数据密集专题可切「年/年月」（后端已有 `summarize_topic_events(group_by=year|month)`）。

### 6.5 点击行为
- 点行（非星标区）→ emit `select-event(id)` → 父级展开右栏并填详情。
- 点星标 → emit `toggle-favorite(id)`，复用现有 `PUT /api/events/:id {favorite}`。

## 7. 右栏：详情 + Obsidian 无感编辑（重写 `EventDetailPane.vue`）

### 7.1 操作条（纯图标，**去掉上一条/下一条箭头**）
`(占位 flex) 收藏 / 置顶 / 回收站 / 保存(强调色) | 阅读⇄编辑 / 关闭详情`。

### 7.2 阅读/编辑「同一排版」（重点，覆盖旧基准）
- 阅读与编辑**结构、尺寸、位置完全一致**：标题 → 元信息行(日历+日期、绿叶+专题·时代+下拉) → Markdown 正文 → 标签 / 附件 / 关联事件。
- **无边框、无编辑工具栏**。点「编辑」仅把标题、正文切为可编辑：
  - 原型用 `contentEditable` 演示（caret 强调色、块 hover 轻底）。
  - **生产实现**：正文用 **CodeMirror 6 + Live Preview**（或等价方案）实现真正的 Markdown 原地编辑——渲染态可编辑、光标行显语法、无独立编辑框。标题用同字号无边框 `contenteditable`/input。要求：阅读↔编辑切换无布局位移，右栏整体尺寸不变。
- 保存：手动保存（保留现有脏草稿确认流程：切换/换事件/离开前若有未保存草稿，应用内确认「保存/放弃/取消」，不用浏览器 confirm）。复用现有 `save / dirty-change / cancel` emit。

### 7.3 正文图片内联 + 附件 Modal
- **内联图片**：正文 Markdown `![alt](/images/<filename>)` 由渲染器内联显示；编辑态同样内联可见（Live Preview）。无真实图时用体面占位（原型 `.imgph`）。
- **附件 Modal**：点正文图片或「附件」行 → 弹 Modal 放大。图片用 `attachment.imageUrl`（后端已返回）；非图片(txt/pdf/docx)用 `attachment.url` 做预览/下载。Modal = scrim(blur) + 卡片(标题/元信息/关闭) + 内容区。Esc/点遮罩关闭，禁止触发原生 dialog。
- 新增组件建议：`AttachmentModal.vue`（受控 `open/kind/attachment`）。

### 7.4 关联事件跳转
- 「关联事件」按同 era 聚合（后端 DTO 已含 `relatedEvents[{id,headline,displayLabel}]`，也可用 `relatedEventIds`）。点击 → emit `open-related(id)` → 父级 `select-event(id)`（中栏高亮 + 右栏换内容）。

## 8. 后端与数据契约

### 8.1 现状（无需改动即可支撑的部分）
- 事件 DTO（`event_to_dict`）已含：`dateKey/dateParts/headline/displayLabel/era/bodyMarkdown/tags/attachments(含 url,imageUrl)/relatedEventIds/relatedEvents/createdAt/updatedAt/favorite/deletedAt/items`。
- 附件已带 `url` 与 `imageUrl` → 直接支撑 Modal 与内联图片；媒体上传 `store_uploaded_image` 已支持 jpg/png/gif/webp/svg/pdf/md/txt/docx。
- 筛选/收藏/回收站/时间定位/分组汇总均有现成服务，无需新接口。

### 8.2 新增：通用用户自定义列（已拍板 #1 方案 + #3 仅通用机制）
内置列(时间/类型/标签)映射现有字段，无需新增结构化字段。**仅为「用户自定义列」**新增以下两处（不预置任何具体业务列）：

1. **每专题列定义**：`Topic` 新增 `columns_json: Text default '[]'`，存用户定义的列：`[{"key":"...","label":"...","type":"text|number|date|select","width":80,"order":3,"visible":true}]`。
   - `topic_to_dict` / `get_topic_meta` 增加 `"columns": deserialize_json_list(topic.columns_json)`。
   - `update_topic_meta` 接收 `payload["columns"]`：校验 `key` 合法(`^[a-z][a-z0-9_]*$`)、唯一、不与内置键(`time/type/tags/title`)冲突。
2. **每事件值**：`TimelineEvent` 新增 `extra_json: Text default '{}'`（与 `tags_json` 同模式），存 `{<key>: <value>}`。
   - `event_to_dict` 增加 `"extra": deserialize_json_dict(event.extra_json)`（新增 `deserialize_json_dict` 工具，非 dict 回退 `{}`）。
   - `normalize_event_payload` 接收 `payload["extra"]`：**键白名单 = 该专题 `columns_json` 的 key**，丢弃未定义键；`write_event_model` 写 `event.extra_json = json.dumps(extra, ensure_ascii=False)`。
3. **API**：无需新增路由——`extra` 走现有 `POST/PUT /api/events`；`columns` 走现有 `PUT /api/topics/{id}/meta`。（可选语法糖 `PUT /api/topics/{id}/columns`。）
4. **Schema**：`TimelineEventIn` 增 `extra: dict[str, str] = {}`；新增 `ColumnDef(BaseModel){key,label,type,width,order,visible}`；`TopicMetaUpdateIn` 增 `columns: list[ColumnDef] | None`；`TopicOut` 增 `columns: list[dict]`。
5. **迁移**：两列均 Text + 默认值，启动期对旧库 `ALTER TABLE ADD COLUMN`（参考现有 `legacy_migration`），无数据风险。
6. **删除列**：从 `columns_json` 移除某 key 时，事件 `extra` 中的孤儿键保留不动（软删除，便于恢复），仅前端不渲染。

## 9. 文件级改动映射（逐文件）

前端 `ui/src/`：
- `styles/timeline-notes.css` — 全量替换为原型令牌与三栏/ribbon/列表/详情/Modal 样式（视觉控制平面）。
- `pages/TimelinePage.vue` — 改三栏为可拖拽 grid + 右栏折叠状态；新增 `leftW/rightW/rightOpen/activeColumns/showPreview/activeEra`；接 `select-event` 展开右栏、`open-related` 跳转、resizer 拖拽、列设置状态。
- `components/timeline-notes/TopicSidebar.vue` — 重写为 ribbon + 文件树 + 底栏（§5）；prop/emit 见 §5.5。
- `components/timeline-notes/TimelineFeed.vue` — 重写为列表 + 关联时间线 + 列设置 + 显示预览（§6）。
- `components/timeline-notes/TimelineEventCard.vue` — 废弃卡片，替换为行渲染（可并入 Feed 或改为 `TimelineRow.vue`）。
- `components/timeline-notes/EventDetailPane.vue` — 重写为无感编辑（§7），去箭头、接 CodeMirror、内联图片、关联跳转。
- `components/timeline-notes/AttachmentModal.vue` —（新增）附件/图片放大 Modal。
- `components/timeline-notes/TimelineLucideIcon.vue` — 补登记 §4 新增图标名。
- `components/ColumnConfigPopover.vue` —（新增，或内联 Feed）列设置浮层。
- `utils/markdownPreview.js` / `editorMarkdown.js` — 适配内联图片渲染与 Live Preview 取值。

后端 `backend/app/`：
- `models/entities.py` — `TimelineEvent.extra_json`、`Topic.columns_json`。
- `schemas/common.py` — `TimelineEventIn.extra`、`TopicMetaUpdateIn.columns`、新增 `ColumnDef`、`TopicOut.columns`。
- `services/timeline.py` — `event_to_dict` 增 `extra`；`normalize_event_payload`/`write_event_model` 处理 `extra`；`topic_to_dict`/`get_topic_meta`/`update_topic_meta` 处理 `columns`；新增 `deserialize_json_dict`。
- `services/legacy_migration.py`（或 db 初始化）— 旧库补列迁移。
- `api/topics.py` — meta 接口透传 `columns`（路由不变）。

测试 `tests/` `ui/tests/`：
- 新增/更新：列定义与 `extra` 读写契约（`test_timeline_api.py`）；前端列设置 grid 重算、显示预览不改行高、关联跳转、Modal 开关（`ui/tests/*.test.js`）。

## 10. 交互行为细则（沿用并适配冻结基准 §3–§5）

- 筛选叠加：topic 最外层 → 主筛选(全部/今天/本周/收藏/回收站) → 时代/标签在结果上继续叠加；切换主筛选不清空标签（除非该标签在结果中消失）。
- 搜索范围：当前 topic + 当前左栏筛选结果，不跨 topic。
- 时间定位：仅滚动/聚焦中栏，不改左栏筛选；无精确匹配滚动到最近后一个；URL 支持 `?date=1840 / 1840-06 / 1840-06-01`。
- 回收站：只查看/恢复/永久删除，禁编辑正文/标签/收藏/附件。
- 收藏：卡行星标与右栏星标同一 `favorite` 字段，切换即持久化。
- 脏草稿：切换/换事件/离开编辑前未保存必弹应用内「保存/放弃/取消」。

## 11. 验收与验证

```bash
cmd /c npm run agent:check
cmd /c npm run build
cmd /c npm run test:ui
python -m pytest tests/test_timeline_api.py tests/test_date_utils.py
```
- 视觉 QA：以新版自适应为基准（建议新增 fixture URL，如 `http://127.0.0.1:8798/?topic=1&event=1&view=obsidian`），核对默认两栏、点击展开右栏、拖拽 min/max、显示预览不改行高、无感编辑无边框无工具栏、附件 Modal、内联图片、关联跳转。
- 截图归档到 `docs/visual-qa/`。
- 触发 `AGENTS.md` review gate（视觉基准 + 数据契约 + 跨模块），commit 前需独立 subagent review。

## 12. 与冻结基准差异（需同步改 `00-mandatory-readonly-design-brief.md`）

| 项 | 冻结基准 | 本改版 |
|---|---|---|
| 尺寸 | 1920×1080 像素级 one-view | 单页自适应 + 三栏可拖拽(min/max) |
| 强调色 | 红 | 紫 #7b68d9 |
| 深色 | 不做 | 仍不做（本期） |
| 中栏 | 年份大字轨 + 卡片流 + 底部 composer | 列表 + 关联时间线 + 列可自定义；新建入口仅工具条一个图标 |
| 右栏编辑 | 有边框编辑框 + 工具栏 | 无感编辑：无边框、无工具栏、尺寸不变（CodeMirror Live Preview） |
| 右栏默认 | 常驻三栏 | 默认两栏，点击行展开 |
| 左栏 | 视图+笔记本+标签 | Obsidian ribbon+文件树+底栏；加标签管理+统计(仅3数字)；删两个统计图表 |
| 左栏日历 | 删除 | 仍不做 |

## 13. 已拍板决策（无需再问）

1. ✅ 自定义列后端 = `Topic.columns_json` + `TimelineEvent.extra_json`（§8.2）。
2. ✅ 无感编辑生产 = **CodeMirror 6 + Live Preview**（允许引入该依赖；其余依赖一律不新增）。
3. ✅ 列机制**只做通用「用户自助加列」**，不预置「地点/来源」等内置业务列（§6.4）。

## 14. 落地纪律与提交前自检（实现代理必须逐条执行）

> 本节是硬约束。配合 `AGENTS.md` 第 9 节与 `docs/agent-frontend-hardness.md`。原型是像素真相，**“看起来差不多”不是验收结论**。

### 14.1 分阶段落地（按序，每阶段独立验证后再进入下一阶段）
1. **外壳**：令牌(§1) + 自适应可拖拽三栏 + 右栏折叠/展开 + 全局禁滚动条。验证：默认两栏、拖拽 min/max、展开动画、无滚动条、无横向溢出。
2. **左栏**：ribbon + 文件树 + 底栏(§5)。验证：四分组、笔记本展开时代、底部设置常驻、单选高亮。
3. **中栏**：列表 + 关联时间线 + 列设置 + 显示预览(§6)。验证：列头/行对齐、脊线连续、行高固定、显示预览不改行高、列增删重算。
4. **右栏**：无感编辑 + 内联图片 + 附件 Modal + 关联跳转(§7)。验证：阅读↔编辑零位移、无边框无工具栏、右栏尺寸不变、图片内联、Modal、跳转。
5. **后端**：`columns_json` + `extra_json` + DTO/schema/迁移(§8.2)。验证：pytest 契约。
6. **联调**：点击行展开右栏、关联跳转、收藏双向、筛选叠加(§10)。
- 任一阶段视觉/行为与原型不符，**先修复再继续**，不得带病推进到下一阶段。

### 14.2 提交前自检清单（每条必须为「是」）
- [ ] 颜色/间距/圆角/字号**全部取自 §1 令牌或 `timeline-notes.css` 已有变量**，无散落魔法值、无新造色。
- [ ] **每一个功能按键都是纯图标**，经 `TimelineLucideIcon.vue`，名称取自 §4；无文字按钮、无散写 `<svg>`、无 emoji。
- [ ] 布局自适应、**无任何 `transform: scale()` 承载布局**、全局无可见滚动条。
- [ ] 右栏**阅读↔编辑无边框、无工具栏、整体尺寸不变**；编辑器内图片内联可见。
- [ ] 三栏拖拽 min/max 生效；默认两栏、点击行才展开右栏；展开动画保留。
- [ ] 中栏行高固定，「显示预览」开关不改变行高；列设置增删列后列头与行对齐。
- [ ] 自定义列：未定义键被后端丢弃；无值显示 `—`；无臆造数据。
- [ ] 数据契约改动**前后端字段名一致 + 测试同步**；未改既有接口语义。
- [ ] 未引入除 CodeMirror 外的新依赖；未动 `package-lock.json`（除非确有依赖变更）；未做无关重构/格式化。
- [ ] 中文文案文件 **UTF-8 正常无乱码**。
- [ ] `agent:check` / `build` / `test:ui` / 后端 `pytest` 全过；视觉 QA 截图归档到 `docs/visual-qa/`。
- [ ] 与原型逐屏对照：左/中/右默认态 + 右栏阅读态 + 右栏编辑态 + 附件 Modal，各截一张与原型并排核对。

### 14.3 禁止（防漂移）
- 禁止偏离原型“自由发挥”视觉；不确定就照原型 1:1，并在回复列出存疑点。
- 禁止把视觉问题改成后端重构/数据迁移；禁止恢复旧基准元素（红色、卡片流、底部 composer、有边框编辑器、右栏箭头/用户栏、左栏日历）。
- 禁止新增暗色模式、移动端重排、营销 hero、装饰渐变/glow/玻璃态、嵌套卡片。
- 禁止用截图当 UI；禁止 PNG 反推 SVG。
