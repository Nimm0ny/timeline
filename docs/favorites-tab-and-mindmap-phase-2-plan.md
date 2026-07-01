# Favorites Tab + Mindmap Phase 2 · Define-First

## Goal

- 把左栏 `收藏` ribbon 从“只有一句计数文案”的弱面板，升级成一个真正可导航、可筛选、可跨本浏览的收藏工作台。
- 把 X6 mindmap 连线从当前 `er + smooth` 的“拖远后大弯线”升级为“路线算法”和“视觉样式”分层的可选系统，默认更稳、更清楚，同时允许用户切换曲线/贝塞尔等表现。
- 为 mindmap 补齐明确的新增子节点入口：工具条主按钮 + 节点四边中心 `+` 入口，交互接近 XMind。

## Non-goals

- 不重做三栏整体视觉基准，不改品牌、排版、主题系统或 Obsidian 基线令牌。
- 不新增除现有 `AntV X6` 栈之外的新依赖；不在本轮引入 `elkjs`、`libavoid`、图形引擎或 UI 框架。
- 不做思维导图富文本工具条、节点图标库、评论协作、多人编辑、自动布局重写或 `.xmind` bridge。
- 不顺手重构条目类 timeline / table / gallery 等其他视图。

## Scope

1. 左栏 `收藏` ribbon 面板内容设计与实现
2. mindmap 连线系统：路线算法、视觉样式切换、持久化
3. mindmap 新增子节点入口：toolbar + 节点侧边 `+`
4. 测试、视觉 QA、文档归档

## Existing Findings

来自 2026-06-30 browser QA：

1. `收藏` ribbon 面板并非“无数据”，但当前只有标题 `收藏` + 一句 `共 N 条收藏。` 文案，信息承载过弱。
2. mindmap 拖拽后连线会随动，但长距离拖拽时形成明显的大弯曲线，视觉不自然。
3. mindmap 当前没有任何显式“新增子节点”按钮；仅支持键盘 `Tab`。

## Design Constraints

- 所有新增按钮必须走 `TimelineLucideIcon.vue`，禁止内联 SVG。
- 图标热区与视觉尺寸必须复用现有 `iconbtn` / `--icon-bar` / `--btn` 体系。
- 颜色、圆角、间距只能用现有 `timeline-notes.css` token，不额外造色。
- 运行时 UI 必须是真实 DOM/SVG，不允许截图式节点装饰。
- 思维导图画布仍使用当前中栏嵌入方案，不扩成新页面。
- 所有用户可选的样式状态必须持久化到 `body_json`（X6 snapshot），不能只保存在本地内存。

## A. 收藏 Tab 设计

### A1. 左栏信息架构

左栏 `收藏` ribbon 从单文案扩展为四段：

1. **收藏总览**
   - `全部收藏`
   - `当前笔记本收藏`
   - `最近加星`
   - 每项显示 count，点击后只切中栏数据范围，不改 ribbon

2. **来源笔记本**
   - 按 notebook 聚合收藏数
   - 形态复用 `.ti.leaf` / `.ti.folder` 的树列表语法，不造新面板体系
   - 点击后中栏仍保持“收藏模式”，但只显示该 notebook 的收藏

3. **属性聚合**
   - 第一版只做 `类型`、`标签`
   - 数据来源限定为“当前收藏结果集”，不是全库
   - 未来再接通用属性系统（select / multiselect / text 等）

4. **最近收藏**
   - 展示最近 5 条收藏项
   - 直接跳转中栏 / 右栏 / mindmap canvas
   - 解决收藏数较少时左栏过空的问题

### A2. 中栏行为

- `收藏（跨本）` 仍保留为中栏标题
- 中栏结果允许跨 topic 展示，但左栏二级筛选必须明确告诉用户当前是在：
  - 全部收藏
  - 当前笔记本收藏
  - 某个来源笔记本
  - 某个标签 / 类型聚合
- 当前过滤条件必须可见且可清空

### A3. 空状态

- 无收藏时：显示真正空状态，而不是只剩一行文案
- 有收藏但当前二级筛选为空时：显示“当前筛选下没有收藏”
- 收藏面板必须始终有可交互内容，不能再只剩一条 copy

### A4. 数据来源

- 继续复用现有 `globalFavoriteEvents` 计算链
- 不新增后端 API
- 左栏来源笔记本 / 类型 / 标签聚合均从当前收藏结果集前端即时计算

## B. Mindmap 连线系统

### B1. 核心原则

把连线拆为两层：

1. **路线算法（routing policy）**
   - 决定边从哪一侧出、哪一侧入、经过哪些折点

2. **视觉样式（stroke style）**
   - 决定同一路线如何被绘制成直角、圆角、平滑曲线、贝塞尔

禁止“直接切 connector 就算换线型”，否则又会退回当前“拖远后大弯线”的问题。

### B2. 用户可选样式（第一版）

对用户暴露四档 `连线样式`：

1. `直角`
   - routing: `smart-orthogonal`
   - rendering: `polyline`

2. `圆角`
   - routing: `smart-orthogonal`
   - rendering: `rounded`
   - **默认**

3. `平滑曲线`
   - routing: `smart-orthogonal` 生成折点
   - rendering: `smooth`

4. `贝塞尔`
   - routing: 基于父子相对方向的 side-to-side 控制点
   - rendering: custom bezier connector

### B3. 路线算法（第一版）

每个节点建立四个 side ports：

- `top`
- `right`
- `bottom`
- `left`

对任意父子节点：

1. 根据父子相对位置选候选 side 对
2. 生成有限候选路径：
   - 直连
   - 1 折
   - 2 折 dogleg
3. 对候选路径打分：
   - 总长度
   - 折点数
   - 是否穿越其他节点 bbox（重罚）
   - 是否贴近其他节点 bbox（次罚）
   - 是否与已有边完全重合（次罚）
4. 选最低分路径

这版目标不是“全局最优边路由”，而是先消灭当前最难看的长弯线和明显穿插。

### B4. X6 落地策略

**本轮推荐策略：只用 X6 现有能力 + 少量自定义。**

- `直角 / 圆角 / 平滑`：
  - 优先建立 side ports + side-aware router
  - 渲染分别用 `polyline / rounded / smooth`
- `贝塞尔`：
  - 不直接沿用当前 `smooth`
  - 改为基于 side pair 手工给控制点的 custom connector

### B5. 为什么不先引第三方方案

不采用外部依赖，理由如下：

- `elkjs` 更像 layout engine，不是当前需求的实时 connector router
- `libavoid` 更接近“动态避障连线”，但集成和维护成本过重，不适合作为当前项目第一步
- 现有 X6 栈足够先做出一个质量明显更高的第一版

### B6. 持久化

在 X6 snapshot 中增加导图级显示偏好，例如：

```json
{
  "_fmt": "x6-mindmap-v1",
  "layout": "free",
  "background": "",
  "edgeRouting": "smart-orthogonal",
  "edgeStyle": "rounded"
}
```

要求：

- 新建导图默认写入 `edgeRouting=smart-orthogonal`
- 默认 `edgeStyle=rounded`
- 用户切换后实时全图重绘，并持久化

## C. 新增子节点入口

### C1. Toolbar 按钮

在 mindmap toolbar 增加一级按钮：

- 名称：`新增子节点`
- 图标：`plusCircle` 或 `plusSign`（实现时按现有 toolbar 主次层级定）
- 未选中节点时 disabled
- 选中节点时点击即为该节点添加 child

### C2. 节点四边中心 `+`

交互参考 XMind，但收敛到本项目风格：

- hover 或选中节点时显示边中点 `+`
- root 节点默认显示四边
- 普通节点默认突出主增长方向（第一版建议右侧），hover 后显示四边
- 点击哪一侧 `+`，新子节点就从哪一侧生成，并把该边的首选出边方向记录给路由算法

### C3. 可见性与密度

- `+` 按钮必须是纯图标小热区，不允许大泡泡或营销式装饰
- 只在 hover / active 时出现，避免常驻噪音
- hit target 需要可点，但不能遮挡节点文本

### C4. 键盘保留

- 现有 `Tab` 新增子节点能力保留
- toolbar / side `+` 是显式可发现入口，不替代键盘入口

## D. 文件级落点

### 必改文件

- `docs/favorites-tab-and-mindmap-phase-2-plan.md`
- `ui/src/components/timeline-notes/TopicSidebar.vue`
- `ui/src/pages/TimelinePage.vue`
- `ui/src/components/timeline-notes/MindmapSurface.vue`
- `ui/src/components/timeline-notes/MindmapEditor.vue`
- `ui/src/utils/mindmapX6.js`
- `ui/src/components/timeline-notes/TimelineLucideIcon.vue`
- `ui/src/styles/timeline-notes.css`

### 测试文件

- `ui/tests/timelineViews.test.js`
- `ui/tests/timelineNotes.test.js`
- 新增 mindmap route/edge tests（必要时独立新文件）

## E. 实施阶段

### Phase 1. 收藏 Tab 左栏内容

- 先只做左栏与中栏过滤链，不动 mindmap
- 验证 `收藏` ribbon 不再是单文案面板

### Phase 2. 连线分层基础

- snapshot 持久化 `edgeRouting / edgeStyle`
- side ports + 默认 `smart-orthogonal + rounded`
- 验证拖拽后连线比当前明显更自然

### Phase 3. 连线样式切换

- toolbar 增加 `连线样式` 菜单
- 四种样式可切换并持久化

### Phase 4. 新增子节点入口

- toolbar 一级按钮
- 节点四边中心 `+`
- 点击方向与边方向联动

### Phase 5. Browser QA + 文档归档

- 1920×1080 固定 URL
- 收藏 tab 前后状态
- mindmap 拖拽 + 各线型截图
- toolbar + 节点侧边 `+` 截图

## Acceptance

### 收藏 Tab

- 左栏 `收藏` ribbon 至少包含：总览、来源笔记本、属性聚合、最近收藏 四段
- 在 `收藏数 = 1` 时左栏仍然不是单行空文案
- 切换不同收藏子视图时，中栏结果与标题/上下文一致

### 连线

- 默认连线样式改为 `圆角`
- 用户可切换 `直角 / 圆角 / 平滑曲线 / 贝塞尔`
- 任意拖拽后，边必须持续跟随
- 边不得穿过其他节点 body
- 默认样式下，不再出现当前这种“拖远后单根大弯线”主观丑陋问题

### 新增子节点

- toolbar 中存在显式新增子节点按钮
- 节点 hover/active 时可从边中点点击 `+` 增加子节点
- 新节点位置与点击侧方向一致

### 持久化

- 连线样式、路由策略保存后刷新不丢
- 新建导图默认继承系统默认线型

## Verification

### Automated

```bash
cmd /c npm run agent:check
cmd /c npm run build
cmd /c npm run test:ui
python -m pytest tests/test_timeline_api.py tests/test_date_utils.py
```

### Browser QA

固定视口：`1920×1080`

建议至少验证：

1. `收藏` ribbon
   - 有收藏时的完整面板
   - 无收藏时的空状态
   - 来源笔记本过滤

2. mindmap 默认线型
   - 打开画布
   - 拖拽一个一级子节点
   - 验证边实时跟随、无 console error

3. 四种线型
   - 每种各切一次
   - 至少对同一拖拽场景截图对比

4. 新增子节点
   - toolbar 按钮新增
   - 节点边中点 `+` 新增
   - 新增后立即保存、刷新再打开

### QA 归档

目录建议：

- `docs/visual-qa/<YYYYMMDD>-favorites-mindmap-phase2/`

至少包含：

- `1920-favorites-tab.png`
- `1920-mindmap-rounded.png`
- `1920-mindmap-polyline.png`
- `1920-mindmap-smooth.png`
- `1920-mindmap-bezier.png`
- `1920-mindmap-add-child-toolbar.png`
- `1920-mindmap-add-child-side-plus.png`
- `README.md`

## Review Gate

本任务默认触发独立 review，理由：

- 左栏信息架构变化
- mindmap 交互行为改线
- 新增用户可选样式状态
- 预期代码 churn > 120 行

## Risks

- 连线算法如果一次追求“全局最优避障”，复杂度会快速膨胀；必须分阶段落地。
- 四边中心 `+` 若做得过重，会破坏当前极简画布；必须压低视觉存在感。
- `收藏` ribbon 若把中栏同样内容重复塞进左栏，会变成信息冗余；左栏必须只做导航与聚合。

## Go / No-Go

- **Go 条件**：用户确认按本方案进入实现。
- **No-Go 条件**：若用户要改收藏信息架构、线型枚举或四边 `+` 可见策略，先更新本文件，再动代码。
