# 编年 Chronicle · Obsidian Minimal 三栏改版 — 详细实现设计（交付 Codex）

> 产品名：**编年（Chronicle）**。代码/仓库技术名沿用 `timeline`；UI 品牌名、文档标题用「编年」。（旧称「历史长河」仅为占位，全部替换。）
> 本文是把 `prototypes/timeline-obsidian-minimal.html` 落到生产代码（Vue 3 + FastAPI + SQLite）的逐项实现说明，**也是本改版的实现基准（baseline of record）**。
> **像素与交互真相 = 该原型文件**；与文字描述冲突时以原型为准。配套高层视觉稿见 `docs/obsidian-minimal-design-spec.md`。
> 实现代理（含 Codex）开工前必读：本文 + 原型 + `AGENTS.md` 第 9 节 + `docs/agent-frontend-hardness.md`。
>
> **【2026-06 整改基准增补】** 以下子系统以专属设计文档为准，**取代本文相应小节**：
> - 统一属性系统（类型/标签/自定义列皆为「属性」）→ `docs/property-system-design.md`（取代 §5.3 标签项 / §6.4 / §8.2）。
> - 外观/主题/Markdown + 全屏设置 → `docs/appearance-system-design.md`（**暗色已解禁**；§1 增暗色令牌组，§9/§12 同步）。
> - 图标尺寸分级（总功能区 ribbon / 三栏功能区两级，后者更小）于整改 P1 折入 §2。

## 0. 定位与范围

- 目标：用 Obsidian 极简风格重构现有三栏时间线笔记界面。
- 技术栈不变：前端 `Vue 3 + Vue Router 4 + Vite`，后端 `FastAPI + SQLAlchemy + SQLite`。
- 本改版**取代**冻结基准 `docs/00-mandatory-readonly-design-brief.md` 的若干裁决（见 §12 差异表）。Codex 落地时需同步更新该冻结文档，否则与 `AGENTS.md` 第 4 节裁决顺序冲突。
- 移动端 Web 形态（`≤768px` 单栏、左抽屉、详情全屏）以 `docs/mobile-web-design.md` 为独立断点基准；桌面 `>1024px` 仍以本文 + 原型为准。
- 已定决策：单页自适应、三栏可拖拽、全局禁滚动条、强调色=紫（可在外观设置自定义）、**深色经主题系统解禁**（见 `docs/appearance-system-design.md`）、中栏列表+关联时间线、行高固定+显示预览、列可自定义、左栏 Obsidian 风格、右栏默认折叠按需展开、无感编辑、附件 Modal、正文内联图片、关联事件跳转。
- 所有功能按键一律 **纯图标（SVG / Lucide）**，集中走 `ui/src/components/timeline-notes/TimelineLucideIcon.vue`。

## 1. 设计令牌（亮色基线；**暗色已解禁**，暗色令牌组见 `docs/appearance-system-design.md` §3.1）

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
- 图标线宽 `1.75`，圆角圆端；按钮热区 26–34px。**图标尺寸三级（令牌）**：ribbon `--icon-rail:18px` ＞ 三栏工具条 `--icon-bar:16px` ＞ 弹层菜单项 `--icon-menu:15px`。**尺寸 / 动画 / 状态的完整令牌与约定见 §2.2（强制）**。
- 字体锁定自托管 `Noto Sans SC`（SIL OFL）；子集外字符回退系统 sans 栈，不回退宋体/衬线。
- 命令按钮统一 `.iconbtn`（hover 浅底，`.on` 强调色软底，`.primary` 强调色实心）。

## 2.1 弹层（popover）与输入控件规范

所有浮层与输入框统一走以下规范，新增控件必须遵守，禁止每处各自造样式。

- **弹层容器（统一·单一真相源）**：所有浮层共用 **`.popover` 一套外壳**——背景 `--bg-detail`、1px `--border`、圆角 `--radius-lg`、阴影 `--shadow-pop`、`z-index:40`；**宽度 / 定位 / 行密度由各浮层修饰类设置**，写法一律 `class="popover <modifier>"`，**禁止任一浮层再重复声明底/边/圆角/阴影**（2026-06-26 已收敛：`.meta-pop` / `.optpick-pop` / `.timeline-action-menu` 去重复用 `.popover`）。内边距随密度：动作菜单 `4px`、选择/字段编辑 `6px`、配置表单 `8px`。标题用 `.pop-title`（11px、大写字距、`--text-faint`）。
  - **弹层家族（判例·全部 = `.popover` + 修饰）**：`.tl-pop`（中栏工具条·配置/定位）、`.meta-pop`（右栏日期/分期·字段编辑）、`.optpick-pop`（属性选择下拉·带右侧打勾）、`.ti-menu`（笔记本行动作菜单）、`.timeline-action-menu`（事件行动作菜单）、列设置面板（`.pop-section` + `.pop-item`）。
  - **行密度三档（高亮态同款）**：① **动作菜单项** `.pop-item` `min-height:28px`（紧凑，见「展开菜单」）；② **配置项** `.pop-item` `32px`（表单类，可编辑需留白）；③ **选择项** `.optpick-opt`（色点 + 名称 + 右侧打勾(check)，见「列表式菜单/属性行」）。三者选中/高亮**同一信号**：`:hover` / `.is-active` = 整行 `--bg-hover` 软底 + `--radius-sm` 圆角（见「展开菜单」①）。
- **分割线分组（强制）**：弹层内按语义分组，组间用分割线隔开——多组用 `.pop-section`（相邻组自动 `border-top:1px var(--border-soft)` + 间距），或用显式 `.pop-divider`（1px `--border-soft`，纵向 margin 6px）。**即时不可逆**的破坏操作（如永久删除、清空回收站——无二次确认）必须用分割线与普通操作隔开；带二次确认卡的破坏项（如删除笔记本）则靠 `.danger` 红标识、可**同组相邻不夹线**（贴合 Notion，详见 §2.1 展开菜单 ③）。
- **输入控件（强制无边框）**：`border:0`、底色 `var(--bg-surface-2)`、圆角 `--radius-sm`、字号 `13px`、最小高 `30px`、padding `0 10px`。聚焦：去 outline、底色提亮到 `--bg-surface`、加 `box-shadow: inset 0 0 0 1.5px var(--accent-line)`（聚焦环，非边框）。禁止 1px 实边框输入框，禁止让输入框继承浏览器默认 16px 字号。
- **列表式新增（Notion 式·强制）**：向列表追加新项（笔记本 §5.3、自定义列 §6.4 等）一律走「**底部内联行**」——不弹独立输入框、不浮在列表顶部。① 列表底部常驻一枚低调的 `新增`(plusSign) 行（复用该列表行型如 `.ti.leaf`，色 `--text-faint`、hover 提亮 `--text-muted`）；② 触发（分组头 `+` 或点该 `新增` 行）后，在列表**末尾**就地展开一枚干净内联行（复用行型 `.ti.folder` / `.pop-item`，**无边框盒、无 ✓/✗ 按钮**，仅 `--bg-hover` 淡选中底），自动聚焦；③ 提交＝Enter / 失焦(有内容即存、空则弃)，取消＝Esc。新项天然落在列表底部（笔记本按 `id asc`）。**判例**：`新建笔记本`（§5.2/§5.3；2026-06-26 由顶部浮动框 + ✓/✗ 改本规范）、`新建列`（§6.4，组件早已底部追加，符合）。
  - **新增入口分级（图标 + 风格统一·强制）**：全应用「新增/新建」入口按角色分四级，**纯 `+`(plusSign) 用于次级 / 列表追加，圆 `+`(plusCircle) 仅留给工具条主操作**，形成层级——① **列表追加行（持久邀请）**：`plusSign` + `--text-faint`、hover 提亮 `--text-muted`，复用宿主行型（判例：左栏 `新增`笔记本 `.ti-add`、列设置 `新建列` `.col-add`，2026-06-26 由圆 + / 平铺 muted 收齐）；② **上下文新建（输入触发）**：`plusSign` + 文字 `--text-muted` / 图标 `--text-faint` + hover 软底（判例：属性选择下拉 `新建「query」` `.optpick-create`）；③ **工具条主操作**：`plusCircle` 强调色实心 `.iconbtn.primary`（判例：中栏 `新建时间点`）；④ **行内 ⊕（hover 操作组）**：`plusSign`（判例：笔记本行 `在此笔记本新建笔记`，见「列表行悬停操作组」）。
- **列表行悬停操作组（Notion 式·强制）**：可操作的列表行（笔记本 `.ti.folder`、中栏事件 `.row` 等）**静息态只显示内容 + 尾部计数/星标，不露任何操作按钮**；仅在 `hover` / 行 `active` / 其菜单打开（`.menu-open`）时，于行**右缘绝对叠加**一枚操作组淡入，**同时尾部计数槽淡出（互斥，二者不并存）**，**绝不改变行高或回流**（硬约束，AGENTS §9 行高固定）。操作组以与行底色一致的遮罩（resting 用 `--bg-sidebar`+`--bg-hover`、active 用 `--accent-soft-2`；中栏用 `--bg-timeline`）盖住下方内容，长名绝不穿透。① **组内顺序（Notion）**：`⋯`(more，溢出菜单) 在左、`⊕`(plusSign，主新增) 在右；单操作行（如中栏事件行仅删除 `.row-act`）可只放一枚。② **`⋯` 行菜单**走弹层规范（本节弹层容器 + 分割线分组）：单一锚点定位于按钮下方（`position:fixed` 叠加于滚动裁切之上）、点外部/`Esc`/列表滚动即关；破坏性项（删除）置于 `.pop-divider` 之下并标 `.danger`。③ **重命名走就地内联编辑**——复用「列表式新增」的无边框输入行（`.ti-create`），Enter/失焦(有变更即存)、Esc 弃，与新增同一套列表编辑文法。图标尺寸 `--icon-bar`。**判例**：笔记本行（§5.3：`⋯`=重命名/删除、`⊕`=在此笔记本新建笔记；2026-06-26 由单一 `删除` 图标升为本规范）、中栏事件行（§6.2：单 `删除` `.row-act`，同族）。`创建副本 / 移动 / 排序`属 Phase 2，预留于 `⋯` 菜单（届时副本/移动加于重命名下、删除上）。
- **展开菜单（动作/弹出菜单·强制）**：由 `⋯` / 右键等触发的动作菜单（笔记本行 `.ti-menu`、中栏事件 `.timeline-action-menu` **同款**）走 **Notion 紧凑度量**，**比配置型弹层（列设置等 `.pop-item` 32px 行）更密**：菜单容器 padding `4px`、宽度按内容收窄（短标签约 `150–170px`，绝不留大片空白＝防「占位大」）；**菜单项**（`.pop-item`）= 前导类型图标(`.pop-item-ic`，15px、`--text-faint`) + 标签(`.lbl`，13px) + 可选尾部(快捷键 / 子菜单 `›` / 单选勾)，行高 `min-height:28px`、`gap:8px`。① **菜单项选中 / 高亮态（固化·唯一当前态信号）**：当前项——鼠标 `:hover` **或**键盘/程序聚焦 `.pop-item.is-active`（`.timeline-action-menu button.is-active`），**二者完全同款**——= **整行 `--bg-hover` 软底填充 + `--radius-sm` 圆角**；因菜单容器 `4px` 内边距，高亮块**内缩呈悬浮、不顶满、不与外框相接**（Notion 观感，见判例图）。**禁止**：描边 / 阴影 / 改字号字重 / 强调色实底 / 文字反白。**危险项 `.danger` 高亮时只换底（`--bg-hover`），文字与图标保持红 `#b0524c`**（不反白、不变色）。`.is-locked`（不可操作项，如列设置必选列）**不高亮**。② **单选菜单**（如主筛选）当前项 = **右侧打勾(check) + 整行极淡底，不画复选框**（详见下「列表式菜单/属性行」）；动作菜单无持久选中态（一次性命令）。③ **分割线分组**（见上「分割线分组」）：语义分组用 `.pop-section` / `.pop-divider`。**短动作菜单中重命名/删除等同组相邻、不夹分割线**——破坏项靠 `.danger`（红 `#b0524c`，文字与图标同色）区分即可，避免「1 项 1 段」的空隔。**仅当**菜单含「安全 vs 破坏」两类不同结果、且破坏项**即时不可逆（无二次确认）**时才用 `.pop-divider` 隔开。**判例**：回收站事件菜单 `恢复` ┄ `永久删除`（即时无确认 → **保留**分割线）；笔记本菜单 `重命名` `删除`（删除走二次确认卡 → **不夹线**、相邻）。强调色仅用于极少处（单选勾）。**判例**：`.ti-menu`（§5.3 笔记本行）、`.timeline-action-menu`（§6.2 事件行），2026-06-26 由 32px/184px 统一收紧为本紧凑度量。
- **中栏工具条弹层（单一锚点·互斥）**：时间定位、列设置等工具弹层共用工具条右侧同一锚点（`.tl-pop`，相对 `.tl-bar` 定位 `top:calc(100%+6px); right:12px`），**任一时刻只开一个**（互斥），点击弹层外或 `Esc` 关闭；宽度按列宽夹取 `min(320px, calc(100%-20px))`，绝不溢出中栏或跨栏重叠。禁止把每个工具各自锚在自己按钮上、且能并存——那会导致弹层重叠。
- **列表式菜单/属性行**：单选/多选菜单只在当前项**右侧打勾(check) + 整行极淡底，不画复选框**（**判例**：属性选择下拉 `.optpick-pop` = 色点 + 名称 + 选中右侧打勾；主筛选同理）；属性/列行 = 类型图标 + 名称 + 右侧操作（显隐眼睛等），强调色仅用于极少处（当前项勾选/打勾）。参考 Notion 克制。

## 2.2 组件系统令牌（尺寸 / 动画 / 状态·强制 · 颜色除外）

> **颜色**经主题系统（`docs/appearance-system-design.md`）由用户自定义；**尺寸 / 圆角 / 动画 / 状态**为固定设计标准，**不可随意造值**。新增任何组件：尺寸取尺寸令牌、动画取动画令牌、状态取下表、颜色取色彩令牌。（2026-06-26 全量收敛散值为令牌。）

### 图标尺寸（三档令牌）
- `--icon-rail:18px`（总功能区 ribbon，最大）／`--icon-bar:16px`（三栏顶部工具条 `pane-head` / `tl-bar` / `actionbar` / `pane-foot`、行内操作 `.ti-act`/`.row-act`）／`--icon-menu:15px`（弹层·菜单项图标 `.pop-item-ic`、选择项打勾 `.opt-check`、列设置眼睛 `.col-eye` 等）。**禁止散写 14/15/16/18 魔法值**。

### 按钮 / 控件尺寸（令牌）
- 图标按钮 `.iconbtn` = `--btn:30px`（顶部工具条标准；`.lg` 为同值语义别名）；`.iconbtn.sm` = `--btn-sm:26px`（密集处：组头、批量条）。行内悬停操作 `.ti-act`/`.row-act`、列眼睛 `.col-eye`、搜索框 `.searchbox`/`.sb-icon` 均取 `--btn`/`--btn-sm`。热区区间 26–34px。
- 圆角 `--radius-lg/--radius/--radius-sm`；输入控件最小高 30px、无边框（§2.1）。

### 交互动画（两档令牌 + 统一缓动）
- **缓动一律 `--ease`**（`cubic-bezier(.32,.08,.24,1)`），**禁止裸 transition 无缓动**。
- **`--motion-base:0.12s`** = 微交互（hover 底/文字、图标按钮反馈、操作组淡入、小幅 transform/旋转、计数互斥淡出）；**`--motion-slow:0.22s`** = 布局/展开（三栏 grid、搜索框宽度、右栏展开）。**禁止散写 0.1/0.15/0.16/0.18/0.24 等杂值**。

### 状态约定（颜色取主题令牌，结构固定）
| 状态 | 视觉 | 类 |
|---|---|---|
| 悬停 / 键盘聚焦 | `--bg-hover` 底 + `--text` | `:hover` / `.is-active` |
| 选中 / 激活 | `--accent-soft` 底 + `--accent` | `.on` |
| 主操作 | `--accent` 实底 + `--accent-contrast` | `.primary` |
| 危险（破坏项） | 文字与图标 `#b0524c` | `.danger` |
| 禁用 | `opacity:.55` + `not-allowed` | `:disabled`；`<label>` 类不接受 `:disabled`，用 **`.is-disabled`** |

**判例**：右栏「添加附件」为 `<label class="iconbtn">`，上传中加 `.is-disabled`，与同排按钮的禁用态一致（2026-06-26）。

## 3. 布局与外壳（自适应 + 可拖拽 + 右栏按需展开）

- 外层 `position:fixed;inset:0`，`display:grid; grid-template-columns: var(--left-w) minmax(0,1fr) var(--right-w);`，`transition:grid-template-columns .22s var(--ease)`（**展开/收起动画，保留**）。
- **默认两栏**：根容器带 `right-closed` 类 → 第三列宽度置 0，右栏内容裁切隐藏。点击中栏行 → 去掉该类（右栏展开）；右栏「关闭」按钮 → 加回该类（收起）。
- **拖拽**：左右各一根绝对定位 resizer（`#rzLeft left:var(--left-w)`；`#rzRight left:calc(100% - var(--right-w))`，`right-closed` 时隐藏）。拖动改写 `--left-w`/`--right-w`，**带 min/max**：左 `220–360`、右 min `360`、max 随视口 `max(560, min(960, 视口宽 - 左栏宽 - 480))`（feed 保底 480px；2026-07-07 拍板放宽，见 `docs/layout-swap-design.md` §7）。
- **栏序 2×2**：`navPosition`（功能栏靠左/靠右）× `detailPosition`（详情贴边/居中，即中栏右栏互换）两个正交旋钮，CSS `order` + grid 变体实现，详见 `docs/layout-swap-design.md` §1/§7。
- 中栏内容 `max-width:1180px` 居中。
- 生产建议把 `--left-w/--right-w/right-open` 存 localStorage，刷新保持；窗口缩放只改内部滚动区高度。

## 4. 图标清单（Lucide）— 所有功能键

在 `TimelineLucideIcon.vue` 的 `icons` 映射登记下列名（原型用同形 SVG，已校验路径）。括号为 Lucide 组件名。

| 用途 | key | Lucide |
|---|---|---|
| 品牌/笔记本 | book / folder | BookOpen / Folder |
| 视图：全部/今天/本周/收藏/回收站 | library/calendar/clock/star/archive | Library, CalendarDays, Clock, Star, Archive |
| 笔记本节点 | notebook | NotebookText |
| 标签 | hash | Hash |
| 统计 | bar | BarChart3 |
| 搜索 | search | Search |
| 时间定位 | calendarSearch | CalendarSearch |
| 筛选 | filter | Filter |
| 列设置 | columns | Columns3 |
| 显示预览 | alignLeft | AlignLeft |
| 新建时间点 | plusCircle | CirclePlus |
| 列表追加·次级新增（新建笔记本组头 + / `新增`行 / 新建列 / 新建选项 / 行内 ⊕ 新建笔记）| plusSign | Plus |（2026-06-26：**纯 + = 次级/列表追加**，圆 + 仅留工具条主操作；统一 §2.1 新增入口分级）
| 行更多操作（行 ⋯ 菜单：重命名/删除等）| more | MoreHorizontal |（2026-06-26 列表行悬停操作组，§2.1）
| 右栏操作收纳（详情 actionbar ⋮ 菜单：附件/关联/回收站）| moreVertical | MoreVertical |（2026-06-28 右栏按钮收纳，§7.1）
| 排序 / 全部折叠 | arrowUpDown / fold | ArrowUpDown, ChevronsDownUp |
| 布局互换（右栏 ⋮ 菜单：详情居中/贴边） | swap | ArrowLeftRight |（2026-07-07 中栏右栏互换，`docs/layout-swap-design.md` §7）
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

> 主题/深色切换在全屏设置「外观」面板进行（预设系统/浅色/深色 + 自定义），非 ribbon sun/moon 图标。

## 5. 左栏：Obsidian 文件树（重写 `TopicSidebar.vue`）

结构 = `ribbon(44px) + pane(1fr)`；pane = `pane-head + pane-scroll + pane-foot`。

### 5.1 Ribbon（最左竖条）
- 顶部图标：品牌(book，紫底)、笔记本(folder，默认 active)、搜索(search)、收藏(star)、标签(hash)、统计(bar)。〔回收站已从 ribbon 移除（D2，2026-06-26）：回收站本质是「删除筛选视图」，统一由 §5.3 视图组入口承载，图标改 archive（D4）以与删除动作 trash 区分。〕
- 单选高亮 `.rb.active`（强调色软底）。搜索点中展开中栏搜索框。生产可作为 pane 切换器（Files/Search/Tags/Stats）。

### 5.2 Pane Head（工具条）
- 左侧标题 `笔记本`；右侧纯图标精简为 **全部折叠(fold) + 多选(listChecks)** 两枚（D1，2026-06-26）。〔新建笔记移除（创建统一归中栏 `+`）；新建笔记本＝分组头右侧 `+`(plusSign) **或**列表底部常驻 `新增` 行触发，输入为「笔记本」列表**底部内联行**（Notion 式，见 §2.1 列表式新增；2026-06-26 由顶部浮动框改），不再浮于面板顶部；排序空壳移除（移动/排序并入 Phase 2）；删除当前笔记本下沉为笔记本行 hover 浮现，见 §5.3。〕

### 5.3 Pane Scroll（分组文件树）
四个可折叠分组（`.tg`，组头 `chevron + 小标题大写 + 组内动作图标`，hover 露出动作图标）：

1. **视图**：全部笔记/今天/本周/收藏/回收站（`.ti.leaf`：图标 + 名称 + 计数）。语义沿用冻结基准 §3：均按当前 topic + 主筛选统计。
2. **笔记本**（文件树）：每个专题是可展开 `.ti.folder`（chevron + folder 图标 + 名称 + 计数），展开显示其**时代(era)** 子项（`.ti.leaf`，`--depth:1`，缩进 + 引导竖线）。子项点击=按 era 过滤中栏（era 为派生筛选、非用户对象，**无行操作**）。`近代史` 默认展开，其余折叠。**hover/选中/菜单打开该行时**，右侧计数槽淡入**操作组**（`.ti-acts`，绝对叠加、计数互斥淡出、不改行高，见 §2.1 列表行悬停操作组）：`⋯`(more) 打开行菜单（**重命名** = 就地内联编辑、**删除**(`.danger`，复用现有删除确认卡)；二者同组相邻、不夹分割线）、`⊕`(plusSign) = 在此笔记本新建笔记（非当前专题则先切换再进创建态）；`创建副本/移动/排序`属 Phase 2。列表**底部常驻一枚低调 `新增`(plusSign) 行**（`.ti-add`，=新建笔记本），触发后于列表末尾就地展开**干净内联创建行**（`.ti-create`：folder 图标 + 无边框输入，无 ✓/✗ 按钮，Enter/失焦存、Esc 弃）——Notion 式，见 §2.1 列表式新增。
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
左：**单行**标题 `{专题} · 共 N 条`（去掉「时间线」前缀；窄栏标题先省略，不挤压按钮）。右纯图标**分组**（2026-07-07 细化为 `.tl-group` 语义分组：组内 gap 2px、组间 gap 10px）：查找组（搜索(展开输入)、时间定位）· 视图组（切换视图、排序、列设置、显示预览(默认 on)）· 选择组（多选）+ 细分隔线 `.tl-divider` + 主操作 新建笔记(强调色实心)。

- **主筛选（全部/今天/本周/收藏/回收站）只在左栏视图区，中栏不重复**——二者绑定同一 `sidebarFilter`，中栏曾经的「筛选」弹层是重复，已移除。
- **列设置**：单按钮（`columns` 图标）开单一锚点·互斥弹层（§2.1）。列表式：每列 = 类型图标 + 名称 + 右侧眼睛显隐；**必选列（时间/事件）为不可点灰色眼睛**；内置类型/标签可显隐；自定义列的编辑/删除悬停该行才浮现、点编辑渐进展开字段；底部「新建列」，右上角安静的 ✓ 保存到当前专题。
- 注：原型 `colPop` 只演示了内置列显隐，本节列设置按 §6.4 + 用户拍板细化为上述列表式（Notion 克制风）；原型其余像素仍为真相。

### 6.2 列表结构
- 吸顶列头（`.tl-cols`，`grid-template-columns:var(--rowgrid)`，随激活列动态生成）。
- 按 **时代分组**：分组头 = 大圆点(强调色) + 时代名 + `起–止年份 · 条数`。
- 事件行 `.row`（grid 对齐）：`rdot | 时间 | 事件(标题 + 灰度预览 + 附件夹子) | [地点] | [类型] | [来源] | 标签色点 | ★`。**hover/选中该行**时，★ 左侧淡入 `删除(trash)` 行内动作（`.row-act`，绝对叠加、渐变遮罩匹配行底色、不改行高）：非回收站视图=移入回收站，回收站视图=永久删除；`移动到其他笔记本`属 Phase 2。
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
- 阅读与编辑**结构、尺寸、位置完全一致**：标题 → **「属性」元数据区** → Markdown 正文 → 附件 / 关联事件。
  - **【2026-06-28 调整·Obsidian 元数据区】** 日期、分组(专题·时代) 不再是正文上方的独立「元信息行」，而是与类型/标签/自定义属性一起并入标题正下方的统一「属性」元数据区（名称仍「属性」，便于查找数据）；**正文内容区下移到属性区之下**，各区以分割线分组。日期/分组为每条笔记必有，故属性区恒显；类型/标签/自定义为空则该行不渲染。属性区每行 = 类型图标 + 标签名 + 值（读态展示、编辑态就地编辑：日期/分组用现有弹层、选项类用 OptionPicker、自由值用无边框输入）。三区(属性/附件/关联)「添加」入口统一为**区头 `+`**（仅当区可见时；附件/关联为空时整区隐藏、首次添加走 actionbar ⋮ 菜单），属性区头 `+` 开 popover 列未填属性。区头 `+` 不增块高度，read↔edit 零位移不破。
- **无边框、无编辑工具栏**。点「编辑」仅把标题、正文切为可编辑（`contenteditable` 正文必须 `outline:none`，去除浏览器默认聚焦黑框——否则违反零位移/无感切换）：
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
- `composables/useViewport.js` — 移动端独立断点状态（`≤768px` mobile；`769–1024px` 紧凑桌面）。
- `components/timeline-notes/MobileTopBar.vue` — 移动主屏顶栏（抽屉 / 标题计数 / 搜索 / 新建）。
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
| 深色 | 不做 | 主题系统支持（暗色已解禁，见 `docs/appearance-system-design.md`） |
| 中栏 | 年份大字轨 + 卡片流 + 底部 composer | 列表 + 关联时间线 + 列可自定义；新建入口仅工具条一个图标 |
| 右栏编辑 | 有边框编辑框 + 工具栏 | 无感编辑：无边框、无工具栏、尺寸不变（CodeMirror Live Preview） |
| 右栏默认 | 常驻三栏 | 默认两栏，点击行展开 |
| 左栏 | 视图+笔记本+标签 | Obsidian ribbon+文件树+底栏；加标签管理+统计(仅3数字)；删两个统计图表 |
| 左栏日历 | 删除 | 仍不做 |
| 移动端 | 禁止移动端重排 | 按 `docs/mobile-web-design.md` 独立断点基准实现移动 Web 单栏形态 |

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
- 禁止未按 `docs/mobile-web-design.md` 独立断点基准擅自移动端重排、营销 hero、装饰渐变/glow/玻璃态、嵌套卡片。（暗色已解禁，经主题系统统一令牌实现；上述装饰禁令在暗色下仍生效。）
- 禁止用截图当 UI；禁止 PNG 反推 SVG。
