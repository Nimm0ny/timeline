---
type: plan
status: define-first（待用户拍板视觉/参数 → implementing）
owner: lhr
created: 2026-07-07
source: 用户 2026-07-07 会话（鼠标按住中栏/右栏顶部工具条空白区拖拽即可互换两栏位置；重点关注渲染实现、性能、是否误触）
参考: docs/layout-swap-design.md §7（detailPosition 旋钮 = 本手势的状态底座，已实现）；docs/obsidian-minimal-implementation-spec.md §2.1（弹层外壳）/§2.2（尺寸·动画·状态令牌）/§3（外壳布局）/§4（图标清单）；docs/agent-frontend-hardness.md；AGENTS.md §9
---

# 编年 · 中栏/右栏拖拽互换手势（pane-swap drag）设计（Define-First）

## 0. 背景与目标

- **现状**：`detailPosition ∈ {edge, center}`（详情贴边/居中，即中右互换）已落地（2026-07-07），入口有两个：设置·外观·布局分段控件、右栏 ⋮ 菜单「详情居中/贴边显示」。持久化 = `app_config` 真相 + `localStorage["chronicle-detail-position"]` 首帧缓存（layout-swap-design.md §7）。
- **Goal**：加拖拽入口——鼠标按住**任一栏工具条空白区**水平拖拽、过阈值松手即互换该栏位置。左栏→`navPosition`，中/右栏→`detailPosition`。直接操纵、可发现、零新状态。（v1 只做中/右；v2 2026-07-07 追加左栏，见 §1.1。）
- **Non-goals**：
  - ~~不做左栏（功能栏）拖拽~~（v2 已解禁：用户 2026-07-07 明确要求。左栏抓手用 `.pane-head`/`.ph-title` 这条非交互标题栏，误触面可控）。
  - 不做自由排序/多槽位停靠（仍是两个正交布尔开关，非 3! 全排列——功能栏恒在外缘，不进中列）。
  - 不做「拖过中线立即实时互换」的实时预览（拖着的面板会瞬移、误触观感暴力、指针在中线附近摆动会连续触发整版 220ms 重排）——**松手才提交**。
  - 不改移动端（单栏抽屉，无三栏概念）；不支持触摸拖拽。
  - 不改 `detailPosition` 的持久化、回滚、跨设备语义（全部复用）。
- **Scope（文件所有权见 §6）**：新增 1 composable + 1 测试文件；改 `TimelinePage.vue`、`TimelineFeed.vue`、`EventDetailPane.vue`、`TopicSidebar.vue`（v2 左栏）、`TimelineLucideIcon.vue`（v2 `panelLeft` 图标）、`timeline-notes.css`；本文档 + spec §3。无后端改动、无新依赖。
- **裁决顺序**：与 AGENTS.md §9 不变量冲突时以 §9 为准；视觉细节以本文档 §2 为准（新交互，原型无对应元素，规格全部由既有令牌推导，不自造值）。

## 1. 交互设计（手势定义与状态机）

### 1.1 手势语义（2026-07-07 v2：三栏全可拖，每栏映射一个旋钮）

> v1 只做中/右两栏（切 `detailPosition`）。用户 2026-07-07 追加「给左栏也加互换」→ 扩为三栏，左栏拖拽切 `navPosition`。每一栏拖拽 = 切「自己那个」旋钮，模型仍是两个正交布尔开关、无自由排序。

| 起手位置 | 拖拽物 | 目标槽位 | 松手效果 |
|---|---|---|---|
| 左栏 `.pane-head` / `.ph-title` | 「功能栏」 | 对侧外缘（当前功能栏对面的那条边） | `navPosition` 翻转（left↔right） |
| 中栏 `.tl-bar` 空白区 | 「笔记列表」 | 详情面板当前占据的轨道 | `detailPosition` 翻转（edge↔center） |
| 右栏 `.actionbar` 空白区 | 「笔记详情」 | 中栏（feed/思维导图）当前占据的轨道 | 同上（同一开关，两侧对称） |

- 左栏（功能栏）恒在外缘 → 拖它 = 去对侧外缘 = `navPosition` 翻转（整屏镜像），中栏 feed 保留居中；`swapTarget` 计算的落点 = 对侧外缘一条「功能栏宽度」的竖条。
- 中/右栏互为唯一目标（swap feed↔detail = `detailPosition` 翻转）。
- 两个旋钮正交，四种 2×2 形态下三栏拖拽都可用，几何按当前形态计算（§3）。
- **左栏拖拽不要求右栏展开**（`navPosition` 与详情开合无关）；中/右栏拖拽要求右栏展开（否则无可交换对象）。`isEnabled(pane)` 分栏门控。

### 1.2 状态机

```
idle ──pointerdown(空白区,主键,鼠标)──▶ pending(死区)
pending ──位移<6px 内 pointerup──▶ idle（视为普通点击，无任何副作用）
pending ──首次位移≥6px 且 |dy|>|dx|──▶ idle（判为竖向/滚动意图，本次放弃）
pending ──首次位移≥6px 且 |dx|≥|dy|──▶ dragging（起 ghost、上 pane-dragging 类）
dragging ──每帧──▶ ghost 跟手；armed = 指针越过对面面板中线（§3.2）
dragging ──pointerup 且 armed──▶ commit：updateDetailPosition(next) → idle
dragging ──pointerup 且 !armed──▶ cancel（ghost 淡出，什么都不发生）→ idle
dragging ──Esc / window blur / resize / pointercancel──▶ cancel → idle
```

- `pending` 阶段**不渲染任何东西**（无 ghost、无类切换）——死区内的一切都和今天完全一样。
- `dragging` 阶段真实面板**纹丝不动**；只有 ghost（§2.1）和目标高亮（§2.2）两个叠加元素。
- commit 后实际互换动画由既有 `transition: grid-template-columns var(--motion-slow) var(--ease)` 完成；组件经 CSS `order` 换位、不重挂，编辑草稿 / CM6 状态 / 滚动位置全部保留。

### 1.3 参数表（拍板默认值，集中为常量便于调参）

| 参数 | 默认值 | 说明 |
|---|---|---|
| `DEAD_ZONE` | `6px` | 起手死区；小于此位移视为点击 |
| 轴向意图 | 首次超死区时 `|dx| ≥ |dy|` | 不满足即放弃，防误吞竖向手势 |
| 提交阈值（中/右栏，v2 微调） | 进入对面面板 `min(对面宽度/2, COMMIT_PENETRATION)` | v1 是「过对面中线」，对宽 feed 要拖 ~620px 太远；v2 封顶 `COMMIT_PENETRATION=200px`，窄栏仍取半宽。永不在还盖着拖拽栏时 armed；超出对面远端仍 armed |
| 提交阈值（左栏，v2 新增） | 指针越过**视口水平中线**（朝对侧） | 「拖过一半就翻到那边」；等价于「dragged 中心与对侧外缘落点中心的中点」，比强行拖到对面外缘更跟手 |
| `COMMIT_PENETRATION` | `200px` | 中/右栏提交所需的进入深度上限 |
| 迟滞 | 无 | 松手才提交，指针来回只切一个 class，无重排，无需迟滞 |
| ghost 指针偏移 | `+14px, +14px` | 纸片不遮指针；贴近视口右/下缘时向内收 |
| 生效条件 | `!isMobile && state.rightOpen && pointerType==='mouse' && button===0` | 右栏收起时无交换对象，禁用 |

## 2. 视觉 UI 设计

> 原型无此元素；规格全部取自 spec §1/§2.2 令牌与 §2.1 弹层外壳语言，**无新造色、无魔法值**（自检 14.2 第 1 条）。

### 2.1 幽灵纸片（ghost chip）`.pane-drag-ghost`

跟手的小纸片，代表被拖拽的面板。复用弹层外壳语言（§2.1「弹层容器」）：

| 属性 | 值 | 来源 |
|---|---|---|
| 结构 | 图标 + 文案，单行 | — |
| 高度 | `28px`（= 动作菜单项行高） | spec §2.1 行密度① |
| 内边距 / 间距 | `padding: 0 10px; gap: 6px` | 输入控件 padding 语言 |
| 底 / 边 / 圆角 / 阴影 | `var(--bg-detail)`；`1px solid var(--border)`；`var(--radius)`；`var(--shadow-pop)` | 弹层外壳（§2.1） |
| 图标 | `--icon-menu`（15px），色 `var(--text-faint)` | §2.2 图标三档（弹层档） |
| 文案 | `12.5px`，色 `var(--text-muted)`，不换行 | 工具条小字号既例（`.tl-context-label` 11.5 / 菜单 13 之间取 12.5） |
| 定位 | `position: fixed; left/top: 0; transform: translate3d(x+14px, y+14px, 0)`；`will-change: transform`；`pointer-events: none` | 性能 §5 |
| 层级 | `z-index: 80` | 高于 resizer(30)/弹层(40)，低于确认层/toast |
| 透明度 | `0.96` | 「拿起来了」的轻浮感，无 glow/玻璃态（§14.3 禁止项） |

### 2.2 目标槽位高亮 `.pane-swap-target`

一个独立的 fixed 叠加矩形（**不**给 `.col` 加 `position:relative` 或伪元素，避免扰动列内部绝对定位），覆盖「松手后被拖面板将要去的轨道」的当前位置：

- 几何：`left/width` = 对面面板当前水平 span（§3.1，dragstart 时计算一次），`top: 0; bottom: 0`。
- 视觉：`background: var(--accent-soft-2)` + `box-shadow: inset 0 0 0 1.5px var(--accent-line)`（与全局聚焦环同语言，spec §2.1 输入聚焦；QA 后由 `--accent-soft` 提到 `--accent-soft-2`=16%，大面积落点在浅底上更清晰，仍为既有 active 态令牌）。无渐变、无 glow。
- 显隐 = `armed` 状态：`opacity 0 ↔ 1`，`transition: opacity var(--motion-base) var(--ease)`；`pointer-events: none`；`z-index: 79`（ghost 之下）。
- 未 armed（还没跨中线）时**完全不可见**——避免一起手就满屏高亮的噪音；高亮出现 = 「现在松手就会互换」的唯一信号，所见即所得。

### 2.3 光标与发现性

- 静息：`.tl-bar .spacer` 与 `.actionbar .spacer` 在手势可用时（桌面 + 右栏展开）给 `cursor: grab`——唯一的常驻提示，零视觉噪音，符合「看的极简」。选择器按工作区状态门控：`.timeline-workspace:not(.is-mobile):not(.right-closed) …`。
- 拖拽中：workspace 加 `pane-dragging` 类 → `cursor: grabbing`（含 `.pane-dragging *`）+ `user-select: none`，防拖拽途中划选文本。

### 2.4 动效时序

| 时刻 | 动效 | 令牌 |
|---|---|---|
| 进入 dragging | ghost 淡入（opacity 0→0.96） | `--motion-base`（0.12s）+ `--ease` |
| 跨过中线 / 退回 | 目标高亮淡入/淡出 | `--motion-base` + `--ease` |
| 松手 commit | ghost 淡出；三栏 grid 互换动画 | ghost `--motion-base`；grid 既有 `--motion-slow`（0.22s） |
| 松手 cancel / Esc | ghost 原地淡出（不做飞回动画，避免额外 JS 动画复杂度） | `--motion-base` |

禁止散写其他时长（§2.2 两档动画令牌）。

### 2.5 文案与图标

| 拖拽物 | ghost 图标（经 `TimelineLucideIcon`） | ghost 文案 |
|---|---|---|
| 左栏面板 | `panelLeft`（PanelLeft，v2 新增登记） | `功能栏` |
| 中栏面板 | `list`（List） | `笔记列表` |
| 右栏面板 | `note`（NotebookText） | `笔记详情` |

`list`/`note` 已在 spec §4 登记；v2 新增 `panelLeft`→`PanelLeft`（同步登记 spec §4 + `TimelineLucideIcon.vue`）。ghost 内图标同样经 `TimelineLucideIcon.vue`（图标纪律）。

## 3. 几何与判定数学

### 3.1 三栏水平 span（dragstart 时计算一次，拖拽期间不再读布局）

记 `W = innerWidth`、`L = paintedLeft()`（compact desktop clamp 220–240）、`R = paintedRight()`（compact clamp 360–380）、`Rd = rightOpen ? R : 0`。`paneSpans` 返回 `{sidebar, feed, detail}` 三栏 span：

| 形态 | sidebar | feed | detail |
|---|---|---|---|
| edge + nav-left | `[0, L]` | `[L, W−Rd]` | `[W−Rd, W]` |
| edge + nav-right | `[W−L, W]` | `[Rd, W−L]` | `[0, Rd]` |
| center + nav-left | `[0, L]` | `[L+Rd, W]` | `[L, L+Rd]` |
| center + nav-right | `[W−L, W]` | `[0, W−L−Rd]` | `[W−L−Rd, W−L]` |

- 三栏恒平铺 `[0,W]` 无缝无叠；sidebar 恒在外缘（触 0 或 W）；右栏收起时 `Rd=0`、feed 吞掉空槽（供左栏在两栏态下仍可拖）。
- `swapTarget(pane)`：左栏→对侧外缘一条宽 `L` 竖条（knob=nav）；feed→detail span、detail→feed span（knob=detail）。
- 与 `relatedPreviewPosition` / resizer 既有数学同源；纯函数，单测覆盖四形态 + 收起态。

### 3.2 armed 判定（提交规则，v2 分手势）

- **中/右栏（相邻互换）**：穿透深度 `penetration(x)` = 指针越过共享边界进入对面的距离；`armed ⇔ penetration > min(对面宽度/2, COMMIT_PENETRATION=200)`。永不在还盖着拖拽栏时 armed；overshoot 仍 armed；退回则 disarm（可逆）。v1 的「过对面中线」对宽 feed 需拖 ~620px，v2 封顶 200px。
- **左栏（去对侧外缘）**：`armed ⇔ 指针越过视口水平中线 W/2`（朝对侧方向）。等价「dragged 中心 ↔ 对侧落点中心」的中点，比逐栏穿透到最外缘更跟手。
- 纯函数 `isArmed(pane, x, draggedSpan, targetSpan, W)`，每帧仅几次算术、**不读 DOM**（span 在 dragstart 缓存）。

## 4. 误触防线（四道，纵深）

| # | 防线 | 机制 | 兜住的场景 |
|---|---|---|---|
| 1 | **起手区域白名单** | 仅 `event.target === 工具条本体` 或指定空白元素（中/右栏 `.spacer`、左栏 `.ph-title`）才起手（**白名单**而非黑名单，天然覆盖未来新增按钮） | 点按钮/搜索框/弹层/上下文 chip 永不触发；左栏排序/折叠/多选钮不误触 |
| 2 | **死区 + 轴向意图** | 位移 < 6px = 点击（空白区点击本无行为，保持无行为）；首超死区时 `|dy|>|dx|` 即放弃 | 手抖、想滚动/竖向手势 |
| 3 | **提交阈值（分手势 §3.2）** | 中/右栏进入对面 `min(半宽,200px)`、左栏过视口中线；只碰边界不算；未 armed 松手 = cancel，**零副作用** | 拖了一半反悔、无意识小幅拖动 |
| 4 | **随时可逃** | Esc / 窗口失焦 / 窗口 resize / pointercancel 一律 cancel；`pointerType==='touch'`、非主键、`isMobile` 不启用；中/右栏还需 `right-open`（左栏不需要） | 拖到一半想放弃、异常环境 |

另：pointerdown 只在白名单命中后 `preventDefault()`（防文本划选/焦点抖动），不影响按钮等正常元素的默认行为。左栏 `.ph-title` 是非交互标题标签（点击无行为），作抓手不夺任何既有交互。

## 5. 渲染实现与性能预算

**原则：拖拽期间零 layout、零真实面板触碰；每帧只有合成器工作。**

- `pointermove` 处理器只做：暂存 `(x, y)` + `requestAnimationFrame` 去重调度（rAF 已排队则直接返回）。**不写响应式 state**。
- rAF 帧内：① 直接写 `ghostEl.style.transform`（绕开 Vue 响应式与 diff）；② 调 `isArmed()`（两次减法）；③ 仅当 armed **翻转瞬间**切换目标高亮 class（不是每帧）。
- 面板 span、共享边界、对面中线全部在 dragstart **计算并缓存**；拖拽全程不读 `getBoundingClientRect`/`innerWidth`（窗口 resize 直接 cancel，杜绝陈旧几何）。
- ghost 与目标高亮都是 `position: fixed + pointer-events: none` 的叶子节点：transform/opacity 变化只走合成器，不触发文档 layout/paint。
- 对比基准：既有 `startResize` 每帧写 `state.leftWidth` → 触发 workspaceStyle 重算 → grid 重排整屏；本手势每帧成本**低于**它一个数量级。commit 时的一次 `--motion-slow` grid 过渡是既有已验收行为（右栏开合同款）。
- 预算：`pointermove` ≤ 0.05ms；rAF 帧 ≤ 0.2ms；dragging 稳态 DevTools Performance 无紫色 Layout 块（验收 A15）。

## 6. 组件契约与文件级改动映射

> 业务判断在页面/composable，展示组件只收 props / 发 emit（AGENTS §9 组件归属）。

| 文件 | 改动 | 预估行数 |
|---|---|---|
| `ui/src/composables/usePaneSwapDrag.js` **新增** | 状态机 + 纯几何函数（`paneSpans`/`swapTarget`/`dragIntent`/`penetration`/`isArmed` 具名导出供单测）；接 `{ isEnabled(pane), getLayout, getGhostEl, onCommit(pane) }`，返回 `{ onPaneDragStart, dragging, draggedPane, armed, targetRect }`；window 级监听 + `onBeforeUnmount(reset)` | ~200 |
| `ui/src/pages/TimelinePage.vue` | 实例化 composable（`getLayout` 复用 navRight/detailCenter/paintedLeft/paintedRight/rightOpen；`onCommit(pane)` = sidebar→`updateNavPosition`、其余→`updateDetailPosition`）；三子组件挂 `@pane-drag-start`；渲染 ghost + 目标高亮；绑 `pane-dragging` 类；startResize compact clamp 收敛（P2-2） | ~55 |
| `ui/src/components/timeline-notes/TimelineFeed.vue` | `.tl-bar @pointerdown`：白名单（bar 本体 / `.spacer`）→ `pane:'feed'`；含工具条图标分组 | ~15 |
| `ui/src/components/timeline-notes/EventDetailPane.vue` | `.actionbar` 同上 → `pane:'detail'` | ~15 |
| `ui/src/components/timeline-notes/TopicSidebar.vue` **v2** | `.pane-head @pointerdown`：白名单（pane-head 本体 / `.ph-title`）→ `pane:'sidebar'` | ~20 |
| `ui/src/components/timeline-notes/TimelineLucideIcon.vue` **v2** | 登记 `panelLeft`→`PanelLeft`（左栏 ghost 图标） | ~2 |
| `ui/src/styles/timeline-notes.css` | `.pane-drag-ghost` / `.pane-swap-target` / grab·grabbing 光标（含左栏 pane-head）/ `user-select:none`，全走令牌 | ~60 |
| `ui/tests/paneSwapDrag.test.js` **新增** | §10.1 用例（三栏 span + 分手势阈值 + swapTarget + gating） | ~200 |
| `docs/obsidian-minimal-implementation-spec.md` §3/§4 | 栏序 2×2 交叉引用 + `swap`/`panelLeft` 图标登记 | ~2 |

合计 ≈ 8 代码文件 / ~450 行（含测试），低于拆分阈值（500 行 / 12 文件）。**无后端改动、无新依赖、不动 `package-lock.json`。**

## 7. 持久化与失败回滚

- commit 唯一动作 = 调既有 `updateDetailPosition(next)`：乐观更新（grid 立即动画互换）→ `PUT /api/config {detailPosition}` → 失败回滚到前值 + toast「布局设置保存失败」（布局动画自动回摆）→ `localStorage["chronicle-detail-position"]` 镜像同步。本手势**不新增任何持久化路径**。
- 三个入口（设置分段控件 / ⋮ 菜单 / 拖拽）收敛到同一函数，状态永不分叉。

## 8. 边界情形决策表

| 情形 | 决策 | 理由 |
|---|---|---|
| 右栏收起（`right-closed`） | 手势整体禁用；spacer 不给 grab 光标 | 没有可交换对象 |
| 中栏是思维导图（`mm-surface`） | 右栏 `.actionbar` 拖拽**可用**（目标 = 中央轨道，CSS 已覆盖 `.col.mm-surface`）；mm 自身工具条**不**做起手区 | W5 工具条密集无干净空白区；成本零因几何同款 |
| 编辑态有未保存草稿 | 允许拖拽互换 | CSS order 换位不重挂组件，草稿无损；不涉及「切换事件」，未保存确认层（hardness §8.3）不触发 |
| 拖拽中弹层开着 | 起手的 pointerdown 天然触发弹层的外部点击关闭，互不干扰 | 既有弹层互斥机制 |
| 拖拽中窗口 resize / 失焦 | cancel | 缓存几何已陈旧，宁可取消 |
| compact desktop（`isCompactDesktop`） | 可用；`L` 取 painted 值（220–240 clamp） | 与 workspaceStyle/resizer 同源，几何一致 |
| 与三栏 resizer 并发 | 不可能同时起手（不同 target；resizer 有自身 mousedown） | — |
| 触摸 / 笔 | `pointerType !== 'mouse'` 不启用（v1） | 触摸拖拽与滚动手势冲突面大，移动端本就无三栏 |

## 9. 可访问性与替代路径

- 手势是纯鼠标增强路径；**键盘可达路径保持两条**：设置·外观·布局分段控件、右栏 ⋮ 菜单项（`.pop-item`，Esc/焦点管理走既有弹层规范）。
- ghost 与目标高亮均 `aria-hidden="true"`（纯视觉反馈，屏幕阅读器路径走上述两个入口）。
- 不劫持任何既有键盘快捷键；Esc 仅在 dragging 态被消费。

## 10. 测试计划

### 10.1 单元测试（`ui/tests/paneSwapDrag.test.js`，node --test，纯函数无 DOM）

1. `paneSpans`：四形态（edge/center × nav-left/right）span 正确；compact clamp 生效；`L+R+feed = W` 恒等。
2. `dragIntent`：死区内 → `pending`；超死区横向 → `drag`；超死区竖向（含 45° 边界 `|dx|===|dy|` 判横向）→ `abort`。
3. `penetration/isArmed`：未越界 = 0/false；恰在边界 = false；中线 = false；中线 +1px = true；overshoot 越过对面远端 = true；退回 = false（可逆）。
4. commit 决策：四形态下拖 feed / 拖 detail 各自产生正确的 `next`（edge↔center 翻转，两侧对称）。
5. 门控：`touch` pointer / 非主键 / `right-closed` / `isMobile` → `onPaneDragStart` 直接忽略。

### 10.2 交互验收（playwright-cli，1920×1080，固定 fixture URL）

| 用例 | 步骤 | 断言 |
|---|---|---|
| 提交路径 | 按住 `.actionbar` 空白 → 横移过中栏中线 → 松手 | workspace 获 `detail-center`；`localStorage` = `center`；网络面板见 `PUT /api/config`；刷新后布局保持 |
| 取消路径 | 同上但只拖 200px（未过中线）松手 | 类不变、无 PUT、无 localStorage 变化 |
| Esc 取消 | 拖拽中按 Esc | 同上，ghost 消失 |
| 竖向放弃 | 按住后先竖移 20px | 不进入 dragging（无 ghost） |
| 空白点击 | 空白区点击（无位移） | 无任何副作用 |
| 按钮不受扰 | 点 `.tl-bar` 各按钮 / `.actionbar` 星标 | 原功能正常，不起手 |
| 反向拖回 | center 态下拖 feed 头回中央 | 翻回 `edge` |
| 收起禁用 | 关闭右栏后按住 `.tl-bar` 空白拖 | 不起手 |

### 10.3 视觉 QA（agent-frontend-hardness §12 流程）

- `npm run build` → 后端 → `qa:visual-fixture` → `qa:visual-server` → 1920×1080 固定 URL。
- 归档 `docs/visual-qa/<YYYYMMDD>-pane-swap-drag/`（含 README：任务/URL/视口/命令/偏差）至少四张：
  1. `1920-drag-ghost.png`：拖拽中、未 armed（ghost 跟手、无高亮）；
  2. `1920-drag-armed.png`：跨中线（目标高亮 + ghost）；
  3. `1920-center-after.png`：commit 后 center 布局稳态；
  4. `1920-edge-after.png`：拖回 edge 后与基线一致（对照 §4 热点回归）。
- 回归检查：首屏无横向溢出、无文本重叠；左栏筛选/右栏读写切换可用；resizer 拖拽 + min/max 正常。

### 10.4 常规命令

`cmd /c npm run agent:check`、`cmd /c npm run build`、`cmd /c npm run test:ui`、`python -m pytest tests/test_timeline_api.py tests/test_date_utils.py`（后端零改动，跑回归 sanity）。

## 11. 验收清单（Acceptance，逐条可判真伪）

- [ ] A1 按住 `.tl-bar` / `.actionbar` 空白区横向拖过对面中线松手 → 中右互换，动画 = 既有 `--motion-slow` grid 过渡。
- [ ] A2 未过中线松手 / Esc / 失焦 / resize → 取消，工作区与持久化状态零变化。
- [ ] A3 位移 < 6px = 点击，无任何行为；竖向意图直接放弃。
- [ ] A4 工具条上所有按钮/搜索框/弹层/标题的既有交互零回归（白名单起手）。
- [ ] A5 拖拽全程真实面板不动；只有 ghost + （armed 时）目标高亮两个叠加元素。
- [ ] A6 ghost/高亮规格与 §2 一致：令牌取色、28px 纸片、`--icon-menu` 图标、`--motion-base` 动效；无新造色/魔法值/新图标。
- [ ] A7 armed 高亮 = 「松手即互换」严格所见即所得（armed 显示 ⇔ 松手会提交）。
- [ ] A8 四种 2×2 形态 + compact desktop 下手势几何均正确（含 nav-right 镜像）。
- [ ] A9 commit 经 `updateDetailPosition`：PUT 失败回滚 + toast；localStorage 镜像同步；刷新/重启保持。
- [ ] A10 编辑态拖拽互换后草稿、光标、滚动位置无损（组件未重挂）。
- [ ] A11 右栏收起、移动端、触摸、非主键均不启用；spacer grab 光标只在可用时出现。
- [ ] A12 ⋮ 菜单与设置分段控件两个既有入口行为不变，三入口状态一致。
- [ ] A13 §9 不变量全绿：无 `transform:scale` 承载布局、无可见滚动条、行高不变、右栏读↔编辑零位移、resizer clamp 不变。
- [ ] A14 单测 §10.1 全过；`agent:check`/`build`/`test:ui`/`pytest` 全过。
- [ ] A15 dragging 稳态 Performance 无 Layout 块（每帧仅合成器工作）。
- [ ] A16 视觉 QA 四态截图归档 + README，热点回归 §4 容差内。

## 12. 工作量 / Review gate / 风险

- **工作量**：~350 行 / 6 代码文件（§6），不触发拆分阈值；实现顺序 = 纯函数与单测 → composable → 接线与 CSS → 交互验收 → 视觉 QA。
- **Review gate**：**触发**（新交互 + 三栏视觉基准 + 触碰 >6 生产/测试文件边缘）→ 实现完成、初步验收后、commit 前，交独立 subagent review（材料含本文档、diff、验证结果）。
- **风险**：
  1. `pointerdown` 白名单误伤未来在工具条新增的可点元素 → 白名单机制天然安全（新元素默认不起手），仅需注意别把新按钮塞进 `.spacer`。
  2. 拖拽期间指针进入 iframe/CM6 编辑区导致 pointermove 丢失 → window 级监听 + `pointerup` 兜底；CM6 无 iframe，实测确认即可。
  3. 用户把「拖拽工具条」理解为移动窗口（桌面 App 心智）→ grab 光标 + ghost 纸片明确「拿起的是面板」；若反馈仍困惑，可调参数区再议常驻提示。
- **可调参数**（默认见 §1.3；实现后如需微调只动常量，不返工设计）：死区像素、提交阈值位置（中线 → 40%/60%）、ghost 文案措辞、grab 光标是否常驻。
