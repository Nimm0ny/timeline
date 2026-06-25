# Agent Frontend Hardness

本文件只在任务涉及 `visual`、`interaction`、`data-contract` 或三栏时间线 UI 时必读。普通文档、后端小修和脚本任务不需要加载本文件。

## 1. 前端项目事实

- 前端：Vue 3 + Vite。
- 图标：`@lucide/vue`，必须通过 `ui/src/components/timeline-notes/TimelineLucideIcon.vue` 集中使用。
- 文本测量：中栏使用 `@chenglou/pretext`，只负责测量、截断、高度预测和滚动 offset 估算，不负责渲染 UI。
- 中栏卡片相关 preset 必须使用 `TimelinePrototypeFont`，不得回退到系统字体栈。
- 后端：FastAPI + SQLAlchemy + SQLite。
- 当前核心页面：三栏时间线笔记界面，左栏分类，中栏时间线，右栏详情/编辑。
- 当前视觉阶段：桌面端、亮色模式、`1920×1080`、one-view 像素级还原。

最小上下文入口：

- 前端入口：`ui/src/pages/TimelinePage.vue`
- 前端样式：`ui/src/styles/main.css`、`ui/src/styles/timeline-notes.css`
- 图标入口：`ui/src/components/timeline-notes/TimelineLucideIcon.vue`
- 时间线组件：`ui/src/components/timeline-notes/`
- API 封装：`ui/src/composables/useApi.js`
- 后端入口：`backend/app/main.py`、`backend/server.py`
- 数据契约：`docs/stage-0-boundary.md`

## 2. 视觉基准

- 基准视口固定为 `1920×1080`。
- `1920` 宽度下三栏宽度固定为 `293 / 1075 / 552`。
- `.timeline-workspace` 必须占满 `100vw × 100vh`。
- 左栏必须贴浏览器左边，右栏必须贴浏览器右边。
- 不允许使用任何运行时 `transform: scale*()` 承载布局、视觉修正或像素还原；如确需局部缩放动画，必须先说明理由并获得用户确认。
- 非 `1920` 窗口必须通过响应式变量重新计算左栏、右栏、中栏、事件卡、年份列、rail 和 composer。
- 高度变化只调整内部滚动区域，不得裁掉左栏设置、底部 composer、右栏底部操作区。
- 所有滚动容器允许滚动但不显示滚动条。
- 前端视觉实现必须按固定视口和关键热点验收，不得用“看起来差不多”作为验收结论。

## 3. 视觉 QA Fixture

- 当前默认视觉 QA fixture 为 `topic=1`、`event=1`、`mode=edit`，对应固定 URL：`http://127.0.0.1:8798/?topic=1&event=1&mode=edit`。
- 该 fixture 必须通过 `cmd /c npm run qa:visual-fixture` 校验：`event` 必须属于同一个 `topic`，且不能处于回收站。
- 不得直接复制旧文档里的 `?topic=1&event=101`。当前数据库中该事件不属于 `topic=1`，会进入“指定事件不存在”路径，不能作为视觉验收目标。
- 如果迁移、重置数据库或调整种子数据导致默认 fixture 失效，必须同步更新本节、`tools/qa/visual-fixture.mjs` 默认值和视觉 QA 记录。
- 需要验证具名原型热点时，必须先确认 fixture 数据能渲染对应节点；否则按首屏第 N 张卡片的 selector 和坐标验收，并在目标文档写明映射关系。

## 4. 必须对齐的 1920 热点

目标容差为 `±4px`：

| 元素 | 坐标与尺寸 |
| --- | --- |
| 左栏快速记录按钮 | `x=21, y=80, w=253, h=40` |
| 搜索笔记 | `x=329, y=16, w=565, h=40` |
| 首屏第 1 张事件卡 | `x=473, y=167, w=531, h=175` |
| 首屏第 2 张事件卡 | `x=473, y=387, w=531, h=147` |
| 首屏第 3 张事件卡 | `x=473, y=580, w=531, h=162` |
| 首屏第 4 张事件卡 | `x=473, y=791, w=531, h=155` |
| 底部新增记录输入框 | `x=354, y=968, w=662, h=77` |
| 保存按钮 | `x=1751, y=80, w=84, h=38` |
| 右侧笔记编辑区域 | `x=1393, y=226, w=508, h=797` |

右栏顶部用户栏、日历按钮和“添加时间点”入口已经确认删除，不进入验收。

## 5. 真实 UI 原则

- 不允许把原型截图、PNG 或整页图片作为页面背景。
- 所有文字、按钮、输入框、卡片、时间线、圆点、连接线、附件和关联项都必须是真实 DOM/CSS/SVG。
- 图标必须是真实 DOM/SVG/CSS 图形。
- 运行时 SVG 图标必须来自 Lucide，并经 `ui/src/components/timeline-notes/TimelineLucideIcon.vue` 统一维护。
- 不允许散落手写 SVG。
- 例外：`ui/src/services/timelineExport.js` 这类导出 SVG/PNG 的 artifact generation 逻辑不属于运行时 UI，可以生成 SVG 字符串；但不得把导出 SVG 反向用于页面渲染。
- 不允许从 PNG 反推一套运行时 SVG token。
- 常规图标视觉尺寸锁定在 `16px~18px`。
- 图标按钮热区按场景使用 `28px / 32px / 36px / 40px`。
- 线性图标线宽约 `1.65px`，圆角和端点保持 round。

## 6. 字体与排版

- 页面字体必须使用项目内置 `TimelinePrototypeFont`。
- 字体文件：
  - `ui/src/assets/fonts/timeline-prototype-regular.ttc`
  - `ui/src/assets/fonts/timeline-prototype-bold.ttc`
- 不允许把标题、年份、卡片正文或 Markdown 区域切到宋体、衬线字体或随意系统字体栈。
- 不允许用视口宽度线性缩放字体。
- 字距保持正常，不使用负字距。
- 文本不得与按钮、图标、卡片边界或相邻内容重叠。
- 固定格式 UI 必须有稳定尺寸或响应式约束，避免 hover、加载、长文本造成布局跳动。
- `ui/src/services/pretextLayout.js` 中 `timelineCardTitle`、`timelineCardPreview`、`timelineCardChip` 必须绑定 `TimelinePrototypeFont`，并与 CSS 字号、字重、行高同步。
- `export*` 或历史测量 preset 可以保留系统字体，但不得用于三栏运行时 UI。

## 7. 颜色与装饰

- 以现有 `ui/src/styles/timeline-notes.css` 的 token 为主，不在组件里散落新颜色。
- 强调色沿用红色体系，避免新增第二套主强调色。
- 不新增营销式 hero、装饰性渐变、glow、blur、玻璃态、彩色阴影、大面积插画背景。
- 不做嵌套卡片包卡片。
- 新增卡片圆角应保持克制，优先贴合现有 `7px~10px` 的工作台密度。

## 8. 三栏行为约束

### 8.1 左栏

左栏必须保留并实现真实功能：

- 品牌区。
- 红色“快速记录”按钮。
- `全部笔记 / 今天 / 本周 / 收藏 / 回收站`。
- 笔记本列表。
- 标签列表。
- 设置入口。

规则：

- 左栏日历不实现，不作为缺失项。
- 所有计数基于当前 topic。
- topic 是最外层范围。
- 主筛选是 `全部笔记 / 今天 / 本周 / 收藏 / 回收站`。
- 标签筛选叠加在主筛选结果上，不主动清空主筛选。
- 搜索范围固定为当前 topic + 当前左栏筛选结果。
- 搜索不得跨 topic，不得绕过回收站、收藏、今天、本周或标签筛选。
- 标签来自当前 topic 事件的 `tags[]` 自动聚合，不单独建标签表。

### 8.2 中栏

中栏以时间线为主体，必须保留：

- 顶部搜索入口，默认图标态，点击后展开。
- 顶部时间定位下拉，入口仅显示 SVG 图标。
- 年份/月/纵向 rail。
- 年份红点、月份浅色点、rail 到卡片的浅色横线、卡片前红点。
- 事件卡。
- 底部 composer。

规则：

- composer 点击后直接让右栏进入新建态。
- composer 可见结构必须保留：圆形加号、竖向分隔线、占位文案、日历/图片/旗帜三个图标按钮、红色圆形发送按钮。
- 时间定位控件是单图标按钮下拉 + 小面板输入，不改成常驻搜索框。
- 时间定位只滚动和聚焦中栏，不改变左栏筛选状态。
- 卡片日期信息由左侧年份/月轨道承担，不在卡片内新增单独日期行。
- 卡片星标和右栏星标操作同一个 `favorite` 字段，并立即持久化。

### 8.3 右栏

右栏默认阅读态，支持完整编辑态。

规则：

- 默认进入阅读态。
- 阅读态正文无编辑框边框。
- 编辑态只做原型里的 Markdown 编辑框，不做双栏预览。
- 编辑态 Markdown 编辑框必须有明确边框。
- 右栏顶部从事件 actionbar 开始，不恢复已删除的用户栏。
- 切换阅读态、切换事件、切换筛选或离开编辑态前，如果有未保存草稿，必须弹应用内确认层。
- 未保存确认层固定为“保存 / 放弃 / 取消”。
- 不允许使用浏览器原生 `confirm` 承担未保存确认。

## 9. 数据与 API 约束

- 后端栈固定为 FastAPI + SQLAlchemy + SQLite。
- 不为前端便利随意新增 API 路由；优先使用既有正式契约。
- 事件 DTO 必须支持：
  - `bodyMarkdown`
  - `tags`
  - `attachments`
  - `relatedEventIds`
  - `createdAt`
  - `updatedAt`
  - `favorite`
  - `deletedAt`
  - legacy `items[]`
- 删除进入回收站：设置 `deletedAt = now`。
- 恢复：设置 `deletedAt = null`。
- 回收站内只允许查看、恢复、永久删除。
- 回收站内不允许编辑正文、修改标签、切换收藏或上传附件。
- 旧 `items[]` 是兼容层，不应重新变成右栏主正文来源。

## 10. 禁止项

- 禁止无任务要求时引入 Pinia、UI 框架、状态机库或新路由体系。
- 禁止把视觉问题绕成后端重构或数据迁移。
- 禁止恢复左栏日历、右栏用户栏、右栏日历按钮、“添加时间点”入口。
- 禁止把截图当 UI。
- 禁止新增暗色模式、移动端重排、复杂断点，除非用户明确要求。
- 禁止为了局部方便破坏 `1920×1080` one-view 基准。
- 禁止大范围格式化已有文件。
- 禁止修改 `package-lock.json`，除非确实变更依赖。
- 禁止提交未验证的视觉改动后只说明“看起来差不多”。

## 11. 实施要求

- Vue 组件保持现有 Composition API 风格。
- 样式优先使用 `timeline-notes.css` 中的 token 和已有类结构。
- 尺寸相关变化优先通过 CSS 变量和集中计算处理，不在多个组件中复制魔法数字。
- 新增图标先加入 `TimelineLucideIcon.vue` 映射，再在组件中以名称使用。
- 业务判断放在页面或 composable 层，展示组件只接收清晰 props 和 emit。
- 涉及 API 的改动必须同步检查前后端字段名、空值、旧数据回退和测试。
- 涉及用户可见中文文案时，必须确认文件编码正常，避免引入乱码。

## 12. 验收细则

`agent:check` 会拦截以下高风险违约：

- `@lucide/vue` 在 `TimelineLucideIcon.vue` 之外被直接导入。
- `components/timeline-notes/` 中散落内联 `<svg>`。
- 使用浏览器原生 `confirm()`。
- 使用运行时 `transform: scale*()` 承载布局、视觉修正或像素还原。
- 运行时 CSS 字体声明绕过 `TimelinePrototypeFont` 或 `--tn-*` 字体 token。
- 中栏卡片 Pretext preset 未绑定 `TimelinePrototypeFont`。

视觉改动还必须做视觉 QA：

- 先运行 `cmd /c npm run build`。
- 启动后端：`python backend/server.py`。
- 校验 fixture：`cmd /c npm run qa:visual-fixture`。
- 另开终端运行：`cmd /c npm run qa:visual-server`。
- 固定 URL：`http://127.0.0.1:8798/?topic=1&event=1&mode=edit`。
- 固定视口：`1920×1080`。
- 检查首屏无横向溢出、无文本重叠、无关键元素缺失。
- 检查关键热点位置和尺寸接近第 4 节。
- 检查左栏筛选、标签、收藏、回收站、右栏阅读/编辑切换仍可用。
- 将视觉 QA 截图归档到 `docs/visual-qa/<YYYYMMDD>-<short-task>/`，并随本次视觉改动一起提交。
- 截图归档至少包含一个 `1920×1080` 固定 URL 的最终态截图；若改动影响多个状态，必须分别归档对应状态，例如 `1920-edit-after.png`、`1920-view-after.png`。
- 归档目录必须包含简短 `README.md`，记录任务、URL、视口、截图文件、验证命令和已知偏差。
- 归档目录只保留最终验收图片和说明文档，不得提交浏览器 profile、trace、临时日志、下载缓存或大体积调试目录。
- 如果截图工具失败，必须先重试或换 Browser/Playwright 路径；仍无法截图时，本次视觉 UI 改动不得 commit，除非用户明确批准无截图交付。

说明：旧文档中可能提到 `.tmp-qa/visual-server.mjs`；该路径属于本地临时目录且被 `.gitignore` 忽略。本仓库可追踪的视觉 QA 入口是 `tools/qa/visual-server.mjs`，通过 `npm run qa:visual-server` 使用。
说明：`qa:visual-fixture` 只校验后端数据和固定 URL 是否可用，不替代像素热点验收。涉及视觉改动时仍必须用浏览器在 `1920×1080` 读取真实 DOM 位置，或在目标文档中说明为什么无法完成。
