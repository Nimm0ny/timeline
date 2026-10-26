# AGENTS.md

本文件是项目级短约束入口。任务细则按需读取，避免重复加载通用流程。
本文件必须以 UTF-8 保存和读取；乱码时显式指定 UTF-8，不得在乱码状态改写。

## 0. 开工前

- 每次任务先读本文件和用户请求，执行 `git status --short`；有未跟踪文件时再执行 `git ls-files --others --exclude-standard`，区分用户改动与本任务文件。不得覆盖或清理不明来源改动。
- 记录相关基线：分支、脏文件、既有服务/端口；确定任务分类、可写范围和临时文件路径。只改完成任务所需文件。
- 按任务读取最少上下文：前端视觉/交互/数据契约读 `docs/agent-frontend-hardness.md`；视觉落地另读 §6 指定基准；后端/API/契约读 `docs/stage-0-boundary.md` 和相关入口/调用方；部署读 `docs/production-deployment-runbook.md`；纯文档只读目标文档及直接依据。
- 本文件原则上不超过 120 行、6000 字符；新增细则放入 `docs/agent-*.md`，这里只保留触发条件与路由。

## 1. 默认工作方式

- 非纯问答任务默认使用 pstack 的 `poteto-mode` 工作流。Cursor 命令是 `/poteto-mode`，Claude Code 是 `/pstack:poteto-mode`；当前宿主未加载插件时，直接读取并遵循 `vendor/pstack/skills/poteto-mode/SKILL.md`，只执行当前宿主支持的步骤。pstack 负责通用流程，本文件和项目设计/契约约束优先。
- 改动前明确 Goal、Non-goals、Scope、Acceptance、Verification。只读问答和边界清楚的小修可不单独写计划；新功能、视觉方向、跨模块、数据契约或需求不确定时先形成计划。
- 预计改动超过 500 行或 12 个文件时先拆分；无法拆分须预先说明。新增函数/计算块超过 50 行时拆分或说明保持单体的理由。视觉决策须获用户明确同意；没有视觉基准不得实施。
- 并行工作须给每个代理独立目标和文件所有权，所有权不得重叠，不同代理不得同时改同一文件；只用当前任务需要的代理。不顺手重构、迁移或统一风格。
- 推送、发布、部署或其他改变远端状态的操作，必须先获用户明确授权。

## 2. Review、提交与远端操作

- 每次提交前判定 review gate。触发条件包括：新增有效代码超过 50 行；有效代码 churn（新增 + 删除，不含纯文档、空行、注释和构建产物）超过 120 行；实施指导文档语义改动超过 80 行或涉及超过 3 份文档；触碰超过 6 个生产/测试/脚本文件；以及 UI 基准、数据契约、既有行为/API/数据/验证路径、文件删除/迁移、权限、持久化、部署、测试 gate、agent guardrail、`AGENTS.md`、`docs/agent-*.md` 或强制设计文档。
- 删除/绕过验证、修复失败测试、更改 fixture/默认数据/URL/端口/环境变量/远端操作步骤也必须 review。纯 typo、无语义格式或历史标记可不 review，但须说明原因。
- 触发时先完成初步验收，再独立启动 subagent review；review 前重查 status 和未跟踪文件，并提供目标/非目标、关键依据、状态、完整 diff/新文件、验收结果和风险。Review 先列问题，注明文件/行号、风险和修复建议。P0/P1/P2 必须修复；否则说明理由并等待用户确认。没有阻断问题时记录 `No blocking findings`。
- 本地提交须为原子提交，只包含本任务文件；不得混入用户改动。未经明确授权不得 push、发布或部署。

## 3. 项目事实与优先级

- 产品名编年（Chronicle），仓库名 timeline；旧称“历史长河”只作占位，UI/文档统一用“编年”。前端 Vue 3 + Vite，后端 FastAPI + SQLAlchemy + SQLite。核心页面是左侧分类/标签/统计、中间时间线、右侧详情/无感编辑。
- 冲突按以下顺序处理：用户当前明确要求；本文件工程/安全规则；当前设计与数据契约文档；pstack 通用工作流；其他文档；现有代码。遇到设计、契约或安全冲突时，说明风险并给可执行替代方案。
- 当前桌面默认亮色，基准是自适应 Obsidian 改版：`docs/obsidian-minimal-implementation-spec.md` + `prototypes/timeline-obsidian-minimal.html`。移动端、属性系统、外观主题分别以 `docs/mobile-web-design.md`、`docs/property-system-design.md`、`docs/appearance-system-design.md` 为准；前端通则见 `docs/agent-frontend-hardness.md`。
- 旧 1920 设计稿、旧截图和 1536 方案只作历史参考；与当前基准冲突时不采用。README 只作启动/背景参考。

## 4. 验收出口

前端/后端改动运行相关验收命令：

```bash
cmd /c npm run agent:check
cmd /c npm run build
cmd /c npm run test:ui
python -m pytest tests/test_timeline_api.py tests/test_date_utils.py
```

- 纯文档改动可不跑构建和测试，需说明原因。`agent:check` 规则见 `docs/agent-frontend-hardness.md`。
- 前端视觉改动须按该文档使用 fixture、以 1920×1080 固定 URL 做 QA，并将截图归档至 `docs/visual-qa/`。

## 5. 收尾与回复

- 停止本任务启动的进程；清理本任务创建且来源明确的临时文件。不得清理 `data/`、`node_modules/`、`.git/`、上传资源、数据库或用户文件。归档的视觉 QA 截图是交付物。
- 恢复本任务修改的环境变量、配置、端口和服务状态，无法恢复时说明影响。结束前执行 `git status --short`，确认只包含本任务改动；用户/并行改动须明确排除。
- 最终回复简要包含 Read、Startup、Changed、Verified、Review、Cleanup、Risks；视觉任务另报 Visual QA。测试未运行须说明原因。

## 6. 「编年」Obsidian 前端硬约束

仅前端落地时适用。原型是像素与交互真相；不确定时照原型，不得自由发挥。完整读取第 3 节所列基准与 `docs/agent-frontend-hardness.md`；按外壳→左→中→右→后端→联调分阶段，对照原型验收后再继续，未达标先修复。提交前逐条检查实现 spec §14.2。

- 颜色、间距、圆角、字号只用 spec §1 令牌或 `notes.css` 既有变量；功能按键必须经 `LucideIcon.vue` 使用 spec §4 图标。业务判断放页面/composable，展示组件只收 props/emit。
- 必须保证并截图验证：自适应布局且不用 transform:scale()；全局禁滚动条；默认两栏，点行展开右栏；三栏拖拽有 min/max；中栏行高固定且预览开关不改行高；右栏阅读/编辑零位移、无边框/工具栏；编辑器图片内联。
- 自定义列只用 Topic.columns_json + Note.extra_json；字段改动须同步前后端和测试；后端丢弃未定义列键；空值显示 —，不得臆造数据。
- 仅允许 CodeMirror 6、AntV X6（@antv/x6、@antv/x6-plugin-history、@antv/x6-plugin-selection、@antv/x6-vue-shape；限 x6@2 / ^2.1.2；导图互通为 app-native JSON + Markdown，旧 simple-mind-map 只读兼容）和 @tanstack/vue-virtual。除此之外不加依赖；仅确有依赖变更时改 package-lock.json。
- 不恢复红色主强调、卡片流、底部 composer、有边框编辑器/工具栏、右栏前后箭头/用户栏、左栏日历；不擅自重排移动端，不加营销 hero、渐变/glow/玻璃态或嵌套卡片。暗色主题经统一主题令牌实现允许。
