---
type: plan
status: define-first
owner: lhr
created: 2026-07-03
source: 用户 2026-07-03 会话拍板（左中栏互换 = 功能栏可靠左/靠右，feed 恒居中，详情在对侧外缘弹出，按侧镜像动画；设置内切换；跨设备；移动端不改）
参考: docs/obsidian-minimal-implementation-spec.md + prototypes/timeline-obsidian-minimal.html（三栏外壳真相）；AGENTS.md §9（前端硬约束、右栏零位移不变量）；docs/appearance-system-design.md
---

# 编年 · 三栏布局互换（功能栏靠左/靠右）设计（Define-First）

## 0. 背景与目标

- **现状**：桌面三栏 grid 恒为 `功能栏(268) | feed(1fr) | 详情(412)`，DOM 顺序 = 列顺序，功能栏锁死最左。
- **Goal**：让用户在设置里选**功能栏靠左 / 靠右**。**收敛成一个旋钮**（用户拍板）：功能栏和详情都是「贴边栏」，feed 恒居中；功能栏选边，详情自动去**对侧外缘**。详情（可折叠）**永远从自己所在的外缘滑入/滑出，按侧镜像**。
- **Non-goals**：~~不做「feed 跑到最右」的 2×2 全自由版（详情夹中间观感差，用户同意先不做）~~（2026-07-07 用户明确要求中/右互换 → 解禁，见 §7）；不改行高/滚动/右栏零位移等 §9 不变量；不改移动端（抽屉单栏，开关自动 no-op）；不改排序/详情等既有行为。

## 1. 布局模型（Model A）

两种桌面布局，一个 `navPosition ∈ {left, right}` 驱动：

```
navPosition=left（默认，今天的样子）:
  功能栏(--left-w) | feed(1fr) | 详情(--right-w)     详情从右缘展开
navPosition=right:
  详情(--right-w) | feed(1fr) | 功能栏(--left-w)     详情从左缘展开（镜像）
```

- feed 恒居中（阅读主体不贴屏幕边缘）；功能栏恒贴一条外缘；详情占对侧外缘、各带自身宽度（不互挤宽度）。

## 2. 实现（纯 CSS 类 + 少量 JS 分支，不重挂组件）

- **外壳类**：workspace 加 `:class="{ 'nav-right': !isMobile && state.config.navPosition === 'right' }"`（**仅桌面**，移动端永不加 → 抽屉布局零触碰）。
- **grid + order（`timeline-notes.css`）**：`.nav-right` 反转 grid-template-columns（含 `.right-closed` 变体），并用 CSS `order` 把 `.col.detail`→首、`.col.timeline/.col.mm-surface`→中、`.col.sidebar`→末（不改 DOM、不重挂组件、不丢状态）：
  - `.nav-right{grid-template-columns:var(--right-w) minmax(0,1fr) var(--left-w)}`
  - `.nav-right.right-closed{grid-template-columns:0 minmax(0,1fr) var(--left-w)}`（详情 col1 折叠→0，从左缘长出）
  - `.nav-right .col.detail{order:0} .col.timeline,.col.mm-surface{order:1} .col.sidebar{order:2}`
  - 动画：复用既有 `transition: grid-template-columns var(--motion-slow)`，详情列 0↔412 过渡即「从外缘滑入/滑出」，两侧同曲线镜像。
- **resizer 翻转**：`.resizer` 是绝对定位（`left`）。`.nav-right #rzLeft{left:calc(100% - var(--left-w))}`（功能栏边界移到右）、`.nav-right #rzRight{left:var(--right-w)}`（详情边界移到左）。`startResize` 的拖拽数学按 `navPosition` 分支：功能栏 `left = navRight ? innerWidth-clientX : clientX`；详情 `right = navRight ? clientX : innerWidth-clientX`（clamp 不变）。rzRight 仍 `v-if rightOpen`。
- **功能栏内壳（QA 补丁）**：功能栏自身是 `44px(ribbon 图标栏) | 1fr(pane)` 内网格。整栏靠右时图标栏还贴在内侧（朝 feed），观感不对——须一并镜像：`.nav-right .sidebar{grid-template-columns:minmax(0,1fr) 44px}` + `.nav-right .ribbon{order:1}`（ribbon 落到外缘 44px 列，pane 朝 feed），且两条分隔线 `border-right→border-left`（`.sidebar` 对 feed 的边、`.ribbon` 对 pane 的边都翻到左侧）。仅 `.nav-right` 作用域，靠左零触碰。
- **详情内壳**：QA 核对左置时关闭钮/留白是否需镜像；实测无需镜像（工具栏右对齐 + 内容左对齐在两侧都成立，读↔编辑零位移不动）。

## 3. 持久化（跨设备 app_config = 真相 + localStorage = 首帧缓存）

- `navPosition` 是全局偏好（非按笔记本）→ 存 `app_config`（`DEFAULT_CONFIG["navPosition"]="left"`），经既有 `GET/PUT /api/config`，跟 `favoritesSort`/`media` 同一套（[[center-sort-design]] §12 已铺路）。**app_config 是跨设备真相**。
- 设置里切换 → 乐观改 + `updateConfig({navPosition})`（失败回滚服务器真值，同 media）。
- **首帧缓存（QA 补丁）**：与 media 不同，navPosition 决定整屏栏序，而 `loadWorkspace` 的 `Promise.all([getConfig, loadIndex])` 要等**整个事件索引**才 merge config——实测右栏用户每次加载先渲染默认「靠左」约 **~600ms** 再整屏交换（醒目毛刺）。故 navPosition 额外镜像到 `localStorage["chronicle-nav-position"]`：初始 `state.config.navPosition` 由缓存 seed（首帧即正确侧），`loadWorkspace` 用后端值 reconcile 并回写缓存（**后端赢**）。同设备零毛刺；跨设备（缓存与后端不一致，罕见）加载后一次 reconcile 交换，属正确行为。`normalizeNavPosition()` 统一把缓存/后端的非法值收敛到默认，后端不校验也不会破布局。

## 4. 设置 UI

- `SettingsModal.vue` **外观**分区顶部加「布局 · 功能栏位置：靠左 | 靠右」分段控件（app_config 路径，`navPosition` prop + `update-nav-position` emit，接 `TimelinePage.updateNavPosition`；与 `mediaConfig`/`update-media` 同构）。不塞进 `AppearanceSettings.vue`（那是 theme store/localStorage，另一套）。

## 5. §9 / 不变量

- 自适应无 `scale`、全局禁滚动条、行高不变、右栏读↔编辑零位移——均不触碰（只换栏序 + 镜像动画/resizer）。三栏拖拽 min/max clamp 保留。移动端不改。
- 图标/令牌纪律：分段控件纯令牌取色，无新图标（纯文字分段或复用既有 `.seg` 观感）。

## 6. 验收 / Review

- `agent:check`/`build`/`test:ui`/`pytest`（后端仅加 1 config 键，回归 sanity）。
- **1920×1080 视觉 QA 两态**（靠左/靠右）：栏序、详情左/右缘弹出动画、resizer 两侧拖拽 + min/max、详情内壳、`localStorage`-clear 跨设备记忆；归档 `docs/visual-qa/`。
- **Review gate**：触发（三栏视觉基准 + 新交互 + 持久化）→ 独立 subagent review。

## 7. 详情居中（中栏/右栏互换）— 2026-07-07 拍板追加

用户 2026-07-07 明确要求「中栏右栏可以自由切换位置」，解禁原 Non-goal。新增第二个独立旋钮 `detailPosition ∈ {edge, center}`（默认 `edge` = 今天的样子），与 `navPosition` 正交，组合出 2×2 全部形态：

```
nav=left  + detail=edge   : 功能栏 | feed(1fr) | 详情(--right-w)    （默认）
nav=left  + detail=center : 功能栏 | 详情(--right-w) | feed(1fr)
nav=right + detail=edge   : 详情(--right-w) | feed(1fr) | 功能栏
nav=right + detail=center : feed(1fr) | 详情(--right-w) | 功能栏
```

- **宽度语义不变**：`--right-w` 在四种形态下都是「详情宽度」，feed 永远是弹性 `minmax(0,1fr)` 列——收起动画保持 px↔px（中列 `--right-w`↔0），1fr 列不参与过渡，无 fr↔px 跳变。
- **实现**：workspace 加 `detail-center` 类（仅桌面），CSS `order` + grid-template 变体（同 §2 手法，不动 DOM）；`.detail-center #rzRight{left:calc(var(--left-w) + var(--right-w))}`、`.nav-right.detail-center #rzRight{left:calc(100% - var(--left-w) - var(--right-w))}`；`startResize` 详情侧拖拽数学按 2×2 分支。feed 分隔线在 detail-center 下翻边（`border-right→border-left`），收起态还原避免与功能栏边线叠加。
- **拖拽上限放宽（同次拍板「右栏能拖更宽」）**：详情 max 从固定 560 改为 `max(560, min(960, innerWidth - 左栏宽 - 480))`——feed 保底 480px 可用，小屏不劣化（isCompactDesktop 首帧 clamp 不变），min 仍 360。
- **持久化**：完全复用 §3 双通道——`app_config.detailPosition`（跨设备真相，后端 DEFAULT_CONFIG 补默认值）+ `localStorage["chronicle-detail-position"]` 首帧缓存 seed + loadWorkspace reconcile（后端赢）；`normalizeDetailPosition()` 收敛非法值。
- **入口**：设置·外观·布局加「详情位置：贴边 | 居中」分段控件（同 navPosition 行）；右栏 ⋮ 菜单加「详情居中显示 / 详情贴边显示」快速切换项（图标 `swap` = Lucide ArrowLeftRight，登记进 TimelineLucideIcon + spec §4）；第三入口 = 工具条空白区拖拽互换手势，独立设计见 `docs/pane-swap-drag-design.md`（define-first，待拍板）。
- **不变量**：右栏读↔编辑零位移、行高、无 scale、禁滚动条均不触碰；移动端不加类、零影响。
