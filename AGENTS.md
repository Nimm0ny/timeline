# AGENTS.md

本文件是本仓库的强约束工程入口，目标是让每次任务都先读到同一套边界、视觉基准和验收标准，达到项目级常驻指导文件的效果。
本文件必须以 UTF-8 保存和读取；如果终端显示乱码，先用显式 UTF-8 重新读取，不得在乱码状态下改写中文内容。

任何自动化代理、AI 助手或维护者在开始改动前，必须先完整阅读本文件。涉及前端 UI、布局、样式、交互或视觉还原的任务，还必须阅读 `docs/00-mandatory-readonly-design-brief.md`。

## 0.1 Hardness 工作方式

总路线固定为 `开工前现场确认 -> Define-First -> 目标文档/实现计划 -> 编码 -> 测试验收 -> 收尾清理 -> 必要时 subagent review -> 本地 commit`。

- 非纯问答任务必须先 Define-First，再动代码。至少明确 `Goal`、`Non-goals`、`Scope`、`Acceptance` 和 `Verification`。
- 小于 20 行且边界明确的修复可以不单独写目标文档，但最终回复必须说明目标、范围和验证结果。
- 涉及新功能、前端视觉方向、跨模块改动、数据契约变化或需求不确定时，必须先形成目标文档或实现计划；涉及视觉拍板时，必须获得用户明确同意后再进入正式实现。
- 单次任务预计改动超过 `500` 行或超过 `12` 个文件时，必须先拆分任务；确实无法拆分时，必须在动手前说明原因。
- 新增单个函数、方法或计算块超过 `50` 行时，必须拆分或说明为什么保持单体更清晰；禁止为了满足行数规则制造无意义抽象。
- 单次任务新增代码有效行数超过 `50` 行时，必须在本地 commit 前进行 code review；不得通过拆文件、拆 commit 或把代码挪到配置/模板中规避 review。
- 当任务被拆给 subagent 时，必须给每个 subagent 明确独立目标和文件所有权；不同 subagent 不得同时修改同一文件。主 agent 负责整合、验证和最终 commit。
- 当任务要求或默认流程需要提交时，agent 负责创建本地原子 commit。commit 必须只包含本次任务相关文件，不得混入用户已有无关改动。
- push 远端必须等待用户明确授权；没有授权时，禁止执行 `git push`、发布、部署或任何会改变远端状态的操作。
- 前端视觉改动必须先确定视觉基准。可用基准包括用户确认的原型、必读设计文档、固定截图或当前已批准实现；没有基准时不得直接实施。
- 前端视觉实现必须按固定视口和关键热点验收，不得用“看起来差不多”作为验收结论。
- 不做 YesMan。当用户要求与本文件、设计基准、数据契约或工程安全冲突时，必须直接指出冲突、说明风险，并给出可执行替代方案。

## 0.2 Code Review 规范

触发 review 时，必须启动独立 subagent 进行，不允许由实现同一个改动的 agent 只做自检替代。

- 触发条件：单次任务新增代码有效行数超过 `50` 行，或涉及前端视觉基准、数据契约、删除/迁移、认证/权限、持久化语义等高风险区域。
- 统计口径：必须同时覆盖已跟踪改动和未追踪新文件，累计新增生产代码、测试代码、脚本代码；纯文档、空行、注释-only 变更、构建产物不计入。
- review 前必须先执行 `git status --short`，并用 `git ls-files --others --exclude-standard` 找出未追踪文件。
- 统计和提交给 subagent 的 diff 必须包含未追踪文件：优先对本次新增文件执行 `git add -N <path>` 后再使用 `git diff --numstat` 和 `git diff`；如果不能修改 index，必须把未追踪文件的完整内容列入 review 材料。
- review 必须发生在测试验收之后、本地 commit 之前。
- 交给 subagent 的材料必须包括：任务目标、Non-goals、已读关键文档、`git status --short`、改动文件清单、包含未追踪文件的完整 diff 或完整文件内容、已运行验证命令及结果、已知风险。
- review 输出必须以问题优先，按严重程度排序，并包含文件/行号、风险说明和建议修复；没有阻断问题时必须明确写 `No blocking findings`。
- P0/P1/P2 问题必须在 commit 前修复或向用户说明不修复理由并等待确认；不得带着未解释的阻断问题提交。
- 最终回复必须说明是否触发 subagent review；触发时列出 review 结论，未触发时说明原因。

## 0. 开工前强制流程

1. 先读本文件，确认任务边界。
2. 执行 `git status --short`，识别当前工作区是否已有用户改动；不得回滚、覆盖或格式化无关改动。
3. 如有未追踪文件，执行 `git ls-files --others --exclude-standard` 分清本任务文件和用户/并行文件；不得把未知来源文件纳入统计、review 或 commit。
4. 记录开工基线：当前分支、工作区脏文件、用户已有改动、已存在后台服务或端口占用。只需要记录与本任务相关的信息，避免无意义盘点。
5. 明确本次任务的可写范围和不可写范围；发现需求会触碰用户已有改动时，先读懂该改动并与其协作，不能直接覆盖。
6. 若任务需要启动服务、写临时文件、生成截图或修改环境变量，先确定命名、路径和退出/清理方式，保证收尾时可追踪。
7. 根据任务范围读取最小必要上下文：
   - 前端入口：`ui/src/pages/TimelinePage.vue`
   - 前端样式：`ui/src/styles/main.css`、`ui/src/styles/timeline-notes.css`
   - 图标入口：`ui/src/components/timeline-notes/TimelineLucideIcon.vue`
   - 时间线组件：`ui/src/components/timeline-notes/`
   - API 封装：`ui/src/composables/useApi.js`
   - 后端入口：`backend/app/main.py`、`backend/server.py`
   - 数据契约：`docs/stage-0-boundary.md`
8. 前端视觉任务必须额外读取：
   - `docs/00-mandatory-readonly-design-brief.md`
   - `timeline_notes_pixel_perfect_1920x1080_one_view.html`
9. 在动手前明确本次改动属于哪类：
   - `visual`: 布局、尺寸、颜色、字体、图标、像素还原
   - `interaction`: 搜索、筛选、收藏、回收站、编辑/阅读切换、未保存确认
   - `data-contract`: DTO、API、字段、持久化
   - `infra`: 构建、测试、启动脚本、依赖
10. 动手前明确 `Goal`、`Non-goals`、`Scope`、`Acceptance`、`Verification`；小修可在回复中简述，但不能省略边界判断。
11. 只改完成任务必须改的文件，不顺手重构、不顺手迁移、不顺手统一风格。

## 1. 项目事实

- 前端：Vue 3 + Vite。
- 图标：`@lucide/vue`，必须通过 `TimelineLucideIcon.vue` 集中使用。
- 文本测量：中栏使用 `@chenglou/pretext`，只负责测量、截断、高度预测和滚动 offset 估算，不负责渲染 UI。中栏卡片相关 preset 必须使用 `TimelinePrototypeFont`，不得回退到系统字体栈。
- 后端：FastAPI + SQLAlchemy + SQLite。
- 当前核心页面：三栏时间线笔记界面，左栏分类，中栏时间线，右栏详情/编辑。
- 当前视觉阶段：桌面端、亮色模式、`1920×1080`、one-view 像素级还原。

## 2. 文档优先级

发生冲突时按以下顺序裁决：

1. 用户当前明确要求。
2. 本 `AGENTS.md` 的工程流程和禁止项。
3. `docs/00-mandatory-readonly-design-brief.md` 的视觉与交互裁决。
4. `timeline_notes_pixel_perfect_1920x1080_one_view.html` 的原型事实。
5. 其他 `docs/` 文档。
6. 现有代码实现。

旧设计文档、旧截图、旧 1536 方案只作为历史参考。只要与当前 one-view 原型或必读设计文档冲突，一律不采用。
`README.md` 当前包含旧接口、旧页面和旧测试状态说明，只作为启动和背景参考；如与本文件、当前代码或测试脚本冲突，以本文件和当前代码为准。
旧文档中出现的 `.tmp-qa/visual-server.mjs` 或 `?topic=1&event=101` 属于历史验收写法；当前可追踪入口和 fixture 以本文件第 8 节为准。

## 3. 前端硬约束

### 3.1 视觉基准

- 基准视口固定为 `1920×1080`。
- `1920` 宽度下三栏宽度固定为 `293 / 1075 / 552`。
- `.timeline-workspace` 必须占满 `100vw × 100vh`。
- 左栏必须贴浏览器左边，右栏必须贴浏览器右边。
- 不允许使用任何运行时 `transform: scale*()` 承载布局、视觉修正或像素还原；如确需局部缩放动画，必须先说明理由并获得用户确认。
- 非 `1920` 窗口必须通过响应式变量重新计算左栏、右栏、中栏、事件卡、年份列、rail 和 composer。
- 高度变化只调整内部滚动区域，不得裁掉左栏设置、底部 composer、右栏底部操作区。
- 所有滚动容器允许滚动但不显示滚动条。

### 3.1.1 视觉 QA Fixture

- 当前默认视觉 QA fixture 为 `topic=1`、`event=1`、`mode=edit`，对应固定 URL：`http://127.0.0.1:8798/?topic=1&event=1&mode=edit`。
- 该 fixture 必须通过 `cmd /c npm run qa:visual-fixture` 校验：`event` 必须属于同一个 `topic`，且不能处于回收站。
- 不得直接复制旧文档里的 `?topic=1&event=101`。当前数据库中该事件不属于 `topic=1`，会进入“指定事件不存在”路径，不能作为视觉验收目标。
- 如果迁移、重置数据库或调整种子数据导致默认 fixture 失效，必须同步更新本节、`tools/qa/visual-fixture.mjs` 默认值和视觉 QA 记录。
- 需要验证具名原型热点时，必须先确认 fixture 数据能渲染对应节点；否则按首屏第 N 张卡片的 selector 和坐标验收，并在目标文档写明映射关系。

### 3.2 必须对齐的 1920 热点

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

### 3.3 真实 UI 原则

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

### 3.4 字体与排版

- 页面字体必须使用项目内置 `TimelinePrototypeFont`。
- 字体文件：
  - `ui/src/assets/fonts/timeline-prototype-regular.ttc`
  - `ui/src/assets/fonts/timeline-prototype-bold.ttc`
- 不允许把标题、年份、卡片正文或 Markdown 区域切到宋体、衬线字体或随意系统字体栈。
- 不允许用视口宽度线性缩放字体。
- 字距保持正常，不使用负字距。
- 文本不得与按钮、图标、卡片边界或相邻内容重叠。
- 固定格式 UI 必须有稳定尺寸或响应式约束，避免 hover、加载、长文本造成布局跳动。
- `ui/src/services/pretextLayout.js` 中 `timelineCardTitle`、`timelineCardPreview`、`timelineCardChip` 必须绑定 `TimelinePrototypeFont`，并与 CSS 字号、字重、行高同步。`export*` 或历史测量 preset 可以保留系统字体，但不得用于三栏运行时 UI。

### 3.5 颜色与装饰

- 以现有 `ui/src/styles/timeline-notes.css` 的 token 为主，不在组件里散落新颜色。
- 强调色沿用红色体系，避免新增第二套主强调色。
- 不新增营销式 hero、装饰性渐变、glow、blur、玻璃态、彩色阴影、大面积插画背景。
- 不做嵌套卡片包卡片。
- 新增卡片圆角应保持克制，优先贴合现有 `7px~10px` 的工作台密度。

## 4. 三栏行为约束

### 4.1 左栏

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

### 4.2 中栏

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

### 4.3 右栏

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

## 5. 数据与 API 约束

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

## 6. 禁止项

- 禁止无任务要求时引入 Pinia、UI 框架、状态机库或新路由体系。
- 禁止把视觉问题绕成后端重构或数据迁移。
- 禁止恢复左栏日历、右栏用户栏、右栏日历按钮、“添加时间点”入口。
- 禁止把截图当 UI。
- 禁止新增暗色模式、移动端重排、复杂断点，除非用户明确要求。
- 禁止为了局部方便破坏 `1920×1080` one-view 基准。
- 禁止大范围格式化已有文件。
- 禁止修改 `package-lock.json`，除非确实变更依赖。
- 禁止提交未验证的视觉改动后只说明“看起来差不多”。

## 7. 实施要求

- Vue 组件保持现有 Composition API 风格。
- 样式优先使用 `timeline-notes.css` 中的 token 和已有类结构。
- 尺寸相关变化优先通过 CSS 变量和集中计算处理，不在多个组件中复制魔法数字。
- 新增图标先加入 `TimelineLucideIcon.vue` 映射，再在组件中以名称使用。
- 业务判断放在页面或 composable 层，展示组件只接收清晰 props 和 emit。
- 涉及 API 的改动必须同步检查前后端字段名、空值、旧数据回退和测试。
- 涉及用户可见中文文案时，必须确认文件编码正常，避免引入乱码。

## 8. 验收命令

常规前端/后端改动完成后至少运行相关命令：

```bash
cmd /c npm run agent:check
cmd /c npm run build
cmd /c npm run test:ui
python -m pytest tests/test_timeline_api.py tests/test_date_utils.py
```

`agent:check` 是硬约束快速检查，会拦截以下高风险违约：

- `@lucide/vue` 在 `TimelineLucideIcon.vue` 之外被直接导入。
- `components/timeline-notes/` 中散落内联 `<svg>`。
- 使用浏览器原生 `confirm()`。
- 使用运行时 `transform: scale*()` 承载布局、视觉修正或像素还原。
- 运行时 CSS 字体声明绕过 `TimelinePrototypeFont` 或 `--tn-*` 字体 token。
- 中栏卡片 Pretext preset 未绑定 `TimelinePrototypeFont`。

如果只改文档，可不运行构建和测试，但需要说明未运行原因。

视觉改动还必须做视觉 QA：

- 先运行 `cmd /c npm run build`。
- 启动后端：`python backend/server.py`。
- 校验 fixture：`cmd /c npm run qa:visual-fixture`。
- 另开终端运行：`cmd /c npm run qa:visual-server`。
- 固定 URL：`http://127.0.0.1:8798/?topic=1&event=1&mode=edit`。
- 固定视口：`1920×1080`。
- 检查首屏无横向溢出、无文本重叠、无关键元素缺失。
- 检查关键热点位置和尺寸接近第 3.2 节。
- 检查左栏筛选、标签、收藏、回收站、右栏阅读/编辑切换仍可用。

说明：旧文档中可能提到 `.tmp-qa/visual-server.mjs`；该路径属于本地临时目录且被 `.gitignore` 忽略。本仓库可追踪的视觉 QA 入口是 `tools/qa/visual-server.mjs`，通过 `npm run qa:visual-server` 使用。
说明：`qa:visual-fixture` 只校验后端数据和固定 URL 是否可用，不替代像素热点验收。涉及视觉改动时仍必须用浏览器在 `1920×1080` 读取真实 DOM 位置，或在目标文档中说明为什么无法完成。

## 8.1 最终回复强制格式

完成代码任务时，最终回复必须包含以下信息；缺一项视为未完成：

- `Read`: 已阅读 `AGENTS.md`，并列出本任务额外读取的关键设计/代码文件。
- `Startup`: 开工前工作区状态、用户/并行改动、任务分类和可写范围摘要。
- `Changed`: 实际改动的文件和行为摘要。
- `Verified`: 已运行的命令及结果；未运行必须说明原因。
- `Review`: 是否触发 subagent review；触发时列出 review 结论，未触发时说明原因。
- `Visual QA`: 若涉及前端视觉，说明是否通过 `qa:visual-fixture`，是否按 `1920×1080` 固定 URL 验证，以及发现的问题。
- `Cleanup`: 是否停止本任务启动的进程、是否清理本任务创建的临时文件、是否仍有非本任务工作区改动。
- `Risks`: 剩余风险或明确写 `无已知剩余风险`。

## 9. 完成前自检

交付前必须确认：

- 已读本文件和本次任务需要的设计文档。
- 没有覆盖用户已有改动。
- 没有扩大任务范围。
- 没有引入截图 UI、散落 SVG、无 token 新颜色或装饰性视觉。
- `1920×1080` 基准没有被破坏。
- 相关测试或构建已运行；未运行时说明原因。
- 如果新增代码有效行数超过 `50` 行，已完成 subagent review，且阻断问题已修复或已获得用户确认。
- 最终回复明确列出改动文件、验证结果和剩余风险。

## 9.1 收尾流程

交付或 commit 前必须执行收尾检查，原则是清理本任务制造的现场，不碰不确定来源的东西。

- 停止本任务启动的后台进程，例如 dev server、backend server、visual QA server；不得停止任务开始前已存在且不属于本任务的进程。
- 清理本任务创建的临时文件、临时日志、临时截图、一次性验证脚本和临时目录；只清理能确认由本任务创建的路径。
- 递归删除前必须确认目标绝对路径位于仓库内，且属于明确临时目录；禁止清理 `data/`、`node_modules/`、`.git/`、上传资源、数据库文件、用户文件和未确认来源的缓存。
- 临时测试文件必须二选一：要么升级为正式测试并纳入本次提交，要么在交付前删除；不得留下无说明的调试测试、临时 fixture 或一次性脚本。
- 不主动删除构建缓存、依赖缓存或包管理器缓存，除非它们由本任务生成、路径明确且已确认无用。
- 如果本任务修改了环境变量、配置文件、端口占用或本地服务状态，必须恢复到任务前状态，或在最终回复中说明未恢复的原因和影响。
- 执行 `git status --short`，确认只 stage/commit 本任务相关文件；发现用户已有或并行产生的改动时，必须明确排除并在最终回复说明。
- 最终回复的 `Cleanup` 项必须说明是否停止了后台进程、是否清理了临时文件、是否仍有非本任务工作区改动。
