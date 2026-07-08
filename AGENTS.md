# AGENTS.md

本文件是本仓库每次任务必读的根入口，只放全局流程、上下文路由、验收出口和禁止性规则。任务细则按需读取，避免普通任务反复加载完整前端视觉规范。
本文件必须以 UTF-8 保存和读取；如果终端显示乱码，先用显式 UTF-8 重新读取，不得在乱码状态下改写中文内容。

任何自动化代理、AI 助手或维护者在开始改动前，必须先完整阅读本文件。

## 0. 上下文加载规则

- 根文件必读：`AGENTS.md`、用户当前请求、`git status --short`。
- 不要为普通任务自动读取全部 `docs/`；按任务分类加载最小必要上下文。
- `visual`、`interaction`、`data-contract` 或三栏时间线 UI 任务：必须额外读取 `docs/agent-frontend-hardness.md`。
- 前端视觉/三栏 UI 落地任务：还必须读取 `docs/obsidian-minimal-implementation-spec.md`（实现基准）和 `prototypes/timeline-obsidian-minimal.html`（像素与交互真相），并遵守本文件第 9 节硬约束。
- 后端/API/数据契约任务：读取 `docs/stage-0-boundary.md`、相关后端入口和 API 调用方。
- 投产/部署任务：读取 `docs/production-deployment-runbook.md`，以该文档记录的真实 host 流程为准。
- 纯文档任务：只读取被修改文档及其直接引用的依据文件。
- `AGENTS.md` 目标是保持短小可常驻，原则上控制在 `120` 行、`6000` 字符以内；新增长规则时，根文件只写触发条件和路由，细则放入 `docs/agent-*.md`。

## 1. Hardness 工作方式

总路线固定为 `开工前现场确认 -> Define-First -> 目标文档/实现计划 -> 编码 -> 测试验收 -> 收尾清理 -> 必要时 subagent review -> 本地 commit`。

- 非纯问答任务必须先 Define-First，再动代码。至少明确 `Goal`、`Non-goals`、`Scope`、`Acceptance` 和 `Verification`。
- 小于 20 行且边界明确的修复可以不单独写目标文档，但最终回复必须说明目标、范围和验证结果。
- 新功能、前端视觉方向、跨模块改动、数据契约变化或需求不确定时，必须先形成目标文档或实现计划。
- 涉及视觉拍板时，必须获得用户明确同意后再进入正式实现。
- 单次任务预计改动超过 `500` 行或超过 `12` 个文件时，必须先拆分任务；确实无法拆分时，必须在动手前说明原因。
- 新增单个函数、方法或计算块超过 `50` 行时，必须拆分或说明为什么保持单体更清晰；禁止为了满足行数规则制造无意义抽象。
- 前端视觉改动必须先确定视觉基准；没有基准时不得直接实施。
- 当任务被拆给 subagent 时，必须给每个 subagent 明确独立目标和文件所有权；不同 subagent 不得同时修改同一文件。主 agent 负责整合、验证和最终 commit。
- 不做 YesMan。当用户要求与本文件、设计基准、数据契约或工程安全冲突时，必须直接指出冲突、说明风险，并给出可执行替代方案。
- 只改完成任务必须改的文件，不顺手重构、不顺手迁移、不顺手统一风格。

## 2. 开工前强制流程

1. 读取本文件，确认任务边界和需要按需加载的子文档。
2. 执行 `git status --short`，识别当前工作区是否已有用户改动；不得回滚、覆盖或格式化无关改动。
3. 如有未追踪文件，执行 `git ls-files --others --exclude-standard` 分清本任务文件和用户/并行文件。
4. 记录开工基线：当前分支、工作区脏文件、用户已有改动、已存在后台服务或端口占用。只记录与本任务相关的信息。
5. 明确本次任务分类：`visual`、`interaction`、`data-contract`、`infra`、`docs` 或 `backend`。
6. 明确本次任务的可写范围和不可写范围；发现需求会触碰用户已有改动时，先读懂该改动并与其协作。
7. 若任务需要启动服务、写临时文件、生成截图或修改环境变量，先确定命名、路径和退出/清理方式。
8. 动手前明确 `Goal`、`Non-goals`、`Scope`、`Acceptance`、`Verification`；小修可在回复中简述，但不能省略边界判断。

## 3. Code Review、commit 与 push

- 每次 commit 前必须先做 review gate 判定，并在最终回复说明触发或未触发的理由。
- `新增代码有效行数 > 50` 只是 review 触发器之一；删除、重构、行为改线和核心文档改写同样可能触发 review。
- 必须 review 的行数/范围条件：新增代码有效行数超过 `50`；有效代码 churn（新增 + 删除，排除纯文档、空行、注释-only、构建产物）超过 `120` 行；实施指导类文档语义 churn 超过 `80` 行或触碰超过 `3` 个文档；或单次任务触碰超过 `6` 个生产/测试/脚本文件。
- 必须 review 的风险条件：前端视觉基准、数据契约、既有行为/接口/数据/验证路径或文件级删除/迁移、认证/权限、持久化语义、部署/发布流程、测试/QA gate、agent guardrail、`AGENTS.md`、`docs/agent-*.md`、mandatory 设计文档、stage boundary、production runbook。
- 必须 review 的行为条件：删除或绕过既有验证；修改测试以适配实现；修复失败测试；更改默认数据、fixture、URL、端口、环境变量或远端/生产操作步骤。
- 不涉及上述行数/范围、风险、行为条件的小 typo、链接修正、纯格式调整、无语义历史文档标记可以不触发 review，但最终回复必须写明未触发原因。
- 触发 review 时，必须启动独立 subagent 进行，不允许由实现同一个改动的 agent 只做自检替代。
- review 前必须执行 `git status --short`，并用 `git ls-files --others --exclude-standard` 找出未追踪文件。
- 统计口径必须覆盖已跟踪改动和未追踪新文件。
- review 必须发生在初步测试验收之后、本地 commit 之前；review 要求补验证时必须补跑。未追踪新文件优先用 `git add -N <path>` 纳入 diff，不能修改 index 时必须把完整文件内容交给 subagent。
- 提交给 subagent 的材料必须包括任务目标、Non-goals、已读关键文档、工作区状态、改动文件清单、完整 diff 或新增文件内容、验证结果和已知风险。
- review 输出必须以问题优先，包含文件/行号、风险说明和建议修复；没有阻断问题时必须明确写 `No blocking findings`。
- P0/P1/P2 问题必须在 commit 前修复，或向用户说明不修复理由并等待确认。
- 当任务要求或默认流程需要提交时，agent 负责创建本地原子 commit。commit 只包含本次任务相关文件，不得混入用户已有无关改动。
- push 远端必须等待用户明确授权；没有授权时，禁止执行 `git push`、发布、部署或任何会改变远端状态的操作。

## 4. 项目事实和文档优先级

- 产品名：**编年（Chronicle）**；代码/仓库技术名沿用 `timeline`。旧称「历史长河」仅为占位，UI 与文档统一用「编年」。
- 前端：Vue 3 + Vite。
- 后端：FastAPI + SQLAlchemy + SQLite。
- 当前核心页面：三栏时间线笔记界面，左栏分类/标签/统计，中栏列表式时间线，右栏详情/无感编辑。
- 当前视觉阶段：桌面端、亮色、**单页自适应 Obsidian 改版**，已取代旧 `1920` 像素基准。实现基准见 `docs/obsidian-minimal-implementation-spec.md` 与 `prototypes/timeline-obsidian-minimal.html`；前端硬约束见第 9 节。
- 前端细则、三栏行为、数据契约、fixture 见 `docs/agent-frontend-hardness.md`。

发生冲突时按以下顺序裁决：

1. 用户当前明确要求。
2. 本 `AGENTS.md` 的工程流程、禁止项与第 9 节实现硬约束。
3. `docs/obsidian-minimal-implementation-spec.md` + `prototypes/timeline-obsidian-minimal.html`（当前实现基准）。
4. `docs/agent-frontend-hardness.md` 的前端/数据契约硬约束。
5. 其他 `docs/` 文档。
6. 现有代码实现。

旧 `docs/00-mandatory-readonly-design-brief.md`、`timeline_notes_pixel_perfect_1920x1080_one_view.html`、旧截图与 `1536` 方案只作历史参考；与当前 Obsidian 改版基准冲突一律不采用。
`README.md` 只作启动和背景参考；冲突以本文件、当前基准和代码为准。

## 5. 验收入口

常规前端/后端改动完成后至少运行相关命令：

```bash
cmd /c npm run agent:check
cmd /c npm run build
cmd /c npm run test:ui
python -m pytest tests/test_timeline_api.py tests/test_date_utils.py
```

- 只改文档可不运行构建和测试，但必须说明未运行原因。
- `agent:check` 是硬约束快速检查；具体拦截项见 `docs/agent-frontend-hardness.md`。
- 前端视觉 UI 改动必须按 `docs/agent-frontend-hardness.md` 执行 fixture、`1920×1080` 视觉 QA，并把验收截图归档到 `docs/visual-qa/`。

## 6. 收尾流程

交付或 commit 前必须清理本任务制造的现场，不碰不确定来源的东西。

- 停止本任务启动的后台进程，例如 dev server、backend server、visual QA server；不得停止任务开始前已存在且不属于本任务的进程。
- 清理本任务创建的临时文件、临时日志、未归档临时截图、一次性验证脚本和临时目录；只清理能确认由本任务创建的路径。
- 前端视觉 UI 验收截图一旦按规范归档，就属于本次交付物，必须随相关改动一起提交，不得在收尾时删除。
- 递归删除前必须确认目标绝对路径位于仓库内，且属于明确临时目录。
- 禁止清理 `data/`、`node_modules/`、`.git/`、上传资源、数据库文件、用户文件和未确认来源的缓存。
- 临时测试文件必须二选一：升级为正式测试并纳入本次提交，或在交付前删除。
- 不主动删除构建缓存、依赖缓存或包管理器缓存，除非它们由本任务生成、路径明确且已确认无用。
- 如果本任务修改了环境变量、配置文件、端口占用或本地服务状态，必须恢复到任务前状态，或在最终回复中说明未恢复的原因和影响。
- 执行 `git status --short`，确认只 stage/commit 本任务相关文件；发现用户已有或并行产生的改动时，必须明确排除并在最终回复说明。

## 7. 最终回复强制格式

完成代码或文档改动任务时，最终回复必须包含以下信息：

- `Read`: 已阅读 `AGENTS.md`，并列出本任务额外读取的关键设计/代码文件。
- `Startup`: 开工前工作区状态、用户/并行改动、任务分类和可写范围摘要。
- `Changed`: 实际改动的文件和行为摘要。
- `Verified`: 已运行的命令及结果；未运行必须说明原因。
- `Review`: 是否触发 subagent review；触发时列出 review 结论，未触发时说明原因。
- `Visual QA`: 若涉及前端视觉，说明是否通过 fixture、是否按 `1920×1080` 固定 URL 验证、截图归档路径，以及发现的问题。
- `Cleanup`: 是否停止本任务启动的进程、是否清理本任务创建的临时文件、是否仍有非本任务工作区改动。
- `Risks`: 剩余风险或明确写 `无已知剩余风险`。

## 8. 完成前自检

- 已读本文件和本次任务需要的子文档。
- 没有覆盖用户已有改动。
- 没有扩大任务范围。
- 没有引入与任务无关的重构、格式化或依赖变更。
- 相关测试或构建已运行；未运行时说明原因。
- 如第 3 节 review gate 被触发，已完成 subagent review，且阻断问题已修复或已获得用户确认。
- 已执行收尾流程，最终回复明确列出改动文件、验证结果和剩余风险。

## 9. 「编年」Obsidian 改版 · 实现代理硬约束（含 Codex，前端落地必读）

实现基准（baseline of record）= `docs/obsidian-minimal-implementation-spec.md` + `prototypes/timeline-obsidian-minimal.html`，优先级高于旧 1920 文档；移动端 Web 形态以 `docs/mobile-web-design.md` 独立断点基准为准。「属性系统」「外观/主题」两子系统分别以 `docs/property-system-design.md`、`docs/appearance-system-design.md` 为准（取代本基准相应小节；暗色已解禁）。涉及本改版前端落地，除常规流程外强制遵守（细则与分阶段/自检清单见 spec 第 14 节，前端通则见 `docs/agent-frontend-hardness.md`）：

- 原型即像素与交互真相：照原型 1:1 还原；不确定一律照原型，并在回复列出存疑点，**禁止自由发挥视觉**。
- 必读：实现 spec 全文（尤其 §14 分阶段落地 + 提交前自检）、原型文件、`docs/agent-frontend-hardness.md`。
- 分阶段落地（外壳→左→中→右→后端→联调），逐阶段对照原型验证后再继续；任一阶段不符先修复，**禁止带病推进**。
- 令牌纪律：颜色/间距/圆角/字号只能取自 spec §1 令牌或 `timeline-notes.css` 既有变量；禁止散落魔法值或新造色。
- 图标纪律：每个功能按键都是纯图标，经 `LucideIcon.vue`，名称取自 spec §4；禁止文字按钮、散写 `<svg>`、emoji。
- 组件归属：业务判断在页面/composable，展示组件只收 props/emit；按 spec §9 文件映射改对应文件，禁止把逻辑堆错层。
- 不变量（须显式保证并截图验证）：自适应且无 `transform:scale()` 承载布局、全局禁滚动条、默认两栏点击行展开右栏、三栏拖拽带 min/max、中栏行高固定且「显示预览」不改行高、右栏阅读↔编辑零位移且无边框无工具栏、编辑器内图片内联。
- 数据契约：自定义列只用 `Topic.columns_json + TimelineEvent.extra_json`（spec §8.2）；改字段必须前后端 + 测试同步；未定义列键后端丢弃；无值显示 `—`，**禁止臆造数据**。
- 依赖：仅三项登记例外——`CodeMirror 6`（无感 markdown 编辑）、`AntV X6`（W4 思维导图引擎，含 `@antv/x6` + `@antv/x6-plugin-history` + `@antv/x6-plugin-selection` + `@antv/x6-vue-shape`（W5 画布 note-embed 卡：Vue 组件当 X6 节点，承嵌入卡富内容/懒渲染分档；pin 在 x6@2 兼容线 `^2.1.2`），用于自由坐标拖拽、连线跟随与编辑历史；导图文件互通基线 = app-native JSON + Markdown，旧 `simple-mind-map` 数据只做读取兼容）与 `@tanstack/vue-virtual`（中栏/右栏/移动端加载性能专项虚拟化基础设施，用于线性视图窗口化、画廊按行虚拟化、看板列内虚拟化）；除此之外不新增依赖；不改 `package-lock.json`（除非确有依赖变更）；不做无关重构/格式化。
- 提交前逐条过 spec §14.2 自检清单；视觉改动按 `docs/agent-frontend-hardness.md` 做 QA 并归档截图；未达标不得 commit。
- 禁止恢复旧基准元素：红色主强调、卡片流、底部 composer、有边框编辑器 + 工具栏、右栏上一条/下一条箭头、右栏用户栏、左栏日历；禁止未按 `docs/mobile-web-design.md` 独立断点基准擅自移动端重排、营销 hero、装饰渐变/glow/玻璃态、嵌套卡片。（暗色已解禁，经主题系统统一令牌实现，见 `docs/appearance-system-design.md`；仍禁装饰渐变/glow/玻璃态。）
