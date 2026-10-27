# 编年前端与 CLI 协作规范

**状态：** Web 前端与 CLI 的规范及实现边界。本文规定前端行为如何被发现、操作和验证；只有列入当前实现切片的能力才表示已接通。

**当前实现切片：** `ui/contracts.json` 为全部 12 个 Web Feature 注册 contract；`api call` 可按共享 schema 调用全部 32 个 active API operation。CLI 可管理隔离的 API 和 Vite 开发服务。真实 UI 场景目前覆盖 `notes.search`；其他 Feature 的 contract 仍需补可执行 UI 场景。视觉对比和全站性能基线未实现。

本文的“必须”“应该”“可以”表示规范强度。API 请求、错误和数据版本遵循[API 与 CLI 契约规范](./agent-api-cli-contract-standard.md)。

## 1. 目标

前端是人使用编年的主要界面，CLI 是 Agent 和开发者发现能力、执行操作、调试界面并独立验证结果的入口。两者必须驱动同一个真实应用、调用同一套正式 API、观察同一份持久化状态。

人类可以直接完成创建、阅读、编辑、搜索、整理和恢复笔记；Agent 能通过 CLI 了解可用能力、前置条件、界面状态、API operation 和恢复路径。CLI 是开发与交付的一部分，不能只提供数据层接口，也不能把页面能打开或截图能生成报告为功能通过。

本规范借鉴 Sikao 的三个做法：Feature Map 关联能力与 UI 合约；CLI 按需发现 UI 状态和验证步骤；观察、自动断言、真实业务通过和人工视觉验收分别报告。Chronicle 复用这些边界思想，不复制 Sikao 的品牌视觉、固定视口、iOS 操作协议或完整证据生命周期系统。

## 2. 契约分层

### 2.1 三类契约分别维护

| 契约 | 说明 | 主要消费者 |
|---|---|---|
| API schema | 请求、响应、错误、版本和幂等语义；由 OpenAPI 表达 | 后端、Web API client、CLI |
| Feature Map | 用户或 Agent 能完成的能力、入口、状态所有者、operation、权限、场景和恢复路径 | Web 导航、CLI 发现、开发者 |
| UI contract | 某项能力在 Web 中的路由、可见状态、交互、可观察结果、响应式变体及可选布局规则 | UI 实现、CLI UI 工具、场景验证 |

Feature Map 不复制组件树或 API schema。UI contract 不另造业务状态；API 是持久化状态的权威来源，UI contract 说明用户如何抵达该状态并能观察什么。

### 2.2 前端结构

- 当前 Web 使用 Vue 3 和 Vite。页面按用户能力组织，组件按可复用职责拆分；除非实际复杂度需要，不按每个 API 路由创建一套组件。
- 全局应用状态、服务端查询缓存和组件临时状态要有明确 owner。服务端数据不能在多个 composable 或组件中形成可独立写入的副本。
- API 请求统一经过一个 typed client。页面不直接拼 URL、解析任意错误体或绕开共享客户端写服务端数据。
- Vue 类型从 OpenAPI schema 生成。共享 UI 组件不携带业务存储逻辑；业务交互由页面或 composable 调用具名 operation。
- 内容编辑器按 `formatId` 选择适配器。Markdown 默认可用；其他格式只能在其读写、验证、保存和回读契约可用时启用。
- 排版、颜色、间距、控件状态和图标优先使用 Chronicle 的 token 与共享组件。新增视觉值必须有用途和来源，不根据一张现有截图反推全站规范。
- Markdown 预览必须净化不可信 HTML；正文和属性不能通过 Vue 模板或 `v-html` 执行脚本。

### 2.3 持久状态与页面状态

服务端拥有持久化笔记、版本、标签、属性、回收状态和 notebook 归属。前端可拥有未保存草稿、焦点、当前面板和临时筛选，但必须标明它们是本地临时状态。

涉及笔记写入的页面必须明确呈现：

- 当前打开的文档身份和 revision。
- 编辑草稿与已保存版本的区别。
- 保存中、已保存、保存失败、版本冲突及离线/服务不可用状态。
- 冲突后的回读和恢复入口；不得静默丢弃本地草稿或覆盖较新版本。
- Agent 建议的来源版本、修改范围和待用户确认状态。用户确认前不得把建议当作已保存内容。

页面首次加载、空列表、无搜索结果、分页加载、无权限、API 失败和恢复后的状态都是 UI 行为的一部分，不能只实现成功态。

## 3. UI contract

### 3.1 Feature Map 绑定

每个面向用户的 Feature Map 项必须说明 Web 入口，并引用一个或多个稳定的 `uiContractId`。纯 API 或开发工具能力可明确声明没有 Web 入口。

UI contract 应按“能力 + 状态”记录，不按每个组件或截图建条目。它描述入口、真实数据条件、交互和可观察结果；源码路径只用于定位消费者，不足以证明能力已实现。

### 3.2 最小结构

```json
{
  "schemaVersion": 1,
  "contracts": [
    {
      "id": "notes.editor.markdown",
      "featureId": "notes.manage",
      "app": "web",
      "route": "/",
      "entryPoint": "笔记列表 → 选择 Markdown 笔记",
      "dataCondition": "用于此场景的真实笔记已存在",
      "states": ["loading", "empty", "editing", "saving", "saved", "conflict", "error"],
      "operationIds": ["notes.read", "notes.update"],
      "sourcePaths": ["ui/src/pages/NotesPage.vue"],
      "scenarios": ["notes.markdown-roundtrip", "notes.revision-conflict"],
      "variants": [
        {"id": "wide", "minWidth": 1024},
        {"id": "compact", "maxWidth": 1023}
      ],
      "mediaPolicy": "none"
    }
  ]
}
```

这是结构示例。正式 schema 必须给每个字段定义类型、必需性、允许值和校验规则；不得把示例字段当自由 JSON 扩展口。

每个 contract 至少包含：

- 稳定 ID、所属 feature、应用和路由。
- 用户入口和测试所需的真实数据条件。
- 需要覆盖的可见状态及对应 API operation ID。
- 引用的必需业务场景。
- 适用的响应式变体；只声明有意义的分界，不设一个所有页面必须使用的固定视口。
- 可选的无障碍定位、行为断言、布局规则和人工观察项。
- 媒体策略：默认 `none`；只有需要视觉判断或用户明确要求时才声明截图/录像。

### 3.3 交互定位与布局规则

- UI 自动化优先通过角色和可访问名称定位，例如 `role=button, name=保存`；其次使用稳定的 `data-testid`。
- 不以 CSS class、DOM 层级、`nth-child` 或当前渲染文本片段作为长期功能身份。
- `data-testid` 是 UI contract 的稳定定位接口；重命名前须同步修改对应 contract 和 CLI 场景。
- 布局规则只记录有设计依据且可以稳定量测的边界、对齐、间距、遮挡或目标尺寸。规则需说明单位、容差、适用变体和依据。
- 字体、颜色、层级、内容密度等不能由几何测量完整证明；需要人工观察时必须显式标记，不得因数值规则通过而自动判视觉通过。
- 不能从当前生产实现或临时原型反向生成“批准基线”。有设计取舍时记来源和适用范围；无取舍时遵循现有有效 token 与交互，不强制另做独立原型。

## 4. CLI 与前端的协作

CLI 是 Web 调试和 UI 验证的正式入口，不是 DOM 脚本集合。所有能力通过 Feature Map 和 UI contract 发现；操作使用命名步骤和正式 API。

建议的命令职责：

| 命令职责 | 行为 | 结果边界 |
|---|---|---|
| `ui guide` / `ui describe` | 按 feature、contract 和状态读取入口、前置条件、断言、operation 和引用规则 | 描述不表示已运行 |
| `ui check` | 静态检查 schema、Feature Map 绑定、可访问性定位和 contract 引用 | 只报告静态覆盖，不报告业务通过 |
| `ui inspect` | 在真实运行页面读取路由、可访问树和当前界面状态 | 观察结果，不是通过断言 |
| `scenario run` | 从真实 UI 入口驱动行为，校验用户可见结果、API operation 和持久化回读 | 只有所有必需步骤及恢复断言通过才返回 passed |
| `ui compare` | 仅在需要视觉判断时采集或对比指定状态 | 视觉/布局结论与业务行为结论分开 |
| `ui measure` | 重复运行一个真实 UI 场景并记录页面就绪和目标结果出现的耗时 | 输出样本、p50/p95、浏览器、视口、数据规模和源码哈希；不代表性能提升 |

具体命令名可由实现调整，但职责、结果含义和 Feature Map 绑定不得省略。CLI 必须使用 JSON stdout；进度和调试日志进入 stderr。未知 contract、无效状态、零适用断言和驱动失败必须返回明确错误码与 `nextAction`，不能以空检查集报告通过。

CLI 的服务启动与浏览器会话必须使用隔离的数据目录和可验证的资源归属。`down` 只停止 CLI 能确认由本次启动的进程；不能附着、清理或改写来源不明的浏览器、服务、数据库或用户资料。

## 5. 场景如何证明前端功能

一个 UI 场景至少应包含：

1. `scenarioId`、输入 schema、前置状态和目标 contract 状态。
2. 从真实 Web 入口开始的用户动作；不得直接调用 Vue 内部 handler 或写入组件私有状态来代替用户操作。
3. 行为断言：例如可见内容、按钮禁用/启用、错误提示、焦点和可恢复操作。
4. API 断言：实际 operation ID、请求版本/幂等键以及返回的稳定对象 ID。
5. 持久化回读：通过正式 API 或 CLI 读取结果，确认正文、属性和 revision。
6. 清理范围及恢复方式；默认只清理本场景创建且可识别的测试数据，不做不可逆删除。

功能场景使用真实应用和真实 HTTP API。Mock 适用于纯展示/算法单测，不得作为保存、版本冲突、恢复或 Agent 提议等端到端行为的唯一证明。测试可以直接准备隔离 fixture，但通过条件必须验证真实用户路径。

## 6. 证据和判定边界

UI 工具返回值必须区分以下结果：

- `observed`：读取到页面或界面状态。
- `asserted`：通过了一个明确、适用的 UI contract 断言。
- `scenario_passed`：业务场景的全部必需动作、可见断言和持久化回读均通过。
- `visual_review_required`：截图/样式仍需人工判断。
- `unknown` / `unsupported`：材料、状态或断言不足以作出结论。

规则：

- 服务健康、页面打开、静态扫描和单张截图不能代替 `scenario_passed`。
- UI contract 通过只证明该状态与列出的规则，不证明 feature 的所有范围。
- 截图、trace 和完整日志默认不采集。需要采集时只记录断言所需状态，并绑定源码版本、浏览器/视口、fixture 身份、API operation 与场景 ID。
- 视觉结论不能升级业务/API 结论；组件单测通过也不能升级真实交互结论。
- 人工需要判断的视觉、文案、信息层级和产品效果保持显式待审阅，不由 CLI 伪造用户批准。

## 7. 可访问性、响应式和性能

- 可操作控件必须有稳定的可访问名称、正确角色、键盘路径和可见焦点；弹层关闭后按交互契约恢复焦点。
- 错误、选中、禁用、保存中等状态不能只依赖颜色表示；减少动态效果设置必须生效。
- 每个 UI contract 声明适用 viewport variant 和目标设备范围。场景需回报实际 viewport；不得用一个固定尺寸替代所有响应式验收。
- 列表使用服务端分页和明确的加载边界。虚拟化、缓存、预加载等优化须由真实数据量和测量结果驱动，并保证键盘与可访问树仍有完整语义。
- 性能比较必须使用同一数据规模、运行模式、浏览器、设备和场景；至少报告样本数及 p50/p95。没有相同基线时只能记录首个基准，不得宣称提升或回归百分比。

## 8. 变更流程与验收清单

新增或修改一个用户可见能力时，在同一改动中完成：

- 更新或复用 Feature Map 和 UI contract；不因一次实现机械地复制新 feature。
- 更新 OpenAPI 相关 schema、operation ID 和生成的前端类型。
- 实现 loading、empty、success、failure、conflict、recovery 等适用状态。
- 更新 CLI help/guide 和至少一个可运行的行为场景。
- 运行本次受影响的静态检查、UI 场景及 API/CLI 回读；按需求运行视觉判断或性能测量。
- 在 JSON 结果中准确说明检查范围、通过项、未运行项和 nextAction。
- 当前可运行切片为 `notes.search`；通过顶层 `scenario run` 执行已登记场景。UI 场景操作真实页面，并由正式 API 回读结果。仓库不保留独立测试文件或测试脚本。

实现中若发现同一个持久状态出现多处 owner、组件直接拼接 API、selector 只能依靠易变 DOM 结构，或 UI/CLI 为同一操作维护两份 schema，应先修正边界再继续加功能。

## 9. 与 Sikao 的借鉴范围

Chronicle 采用 Sikao 中与本产品适配的思路：

- Feature Map 登记用户能力，按需发现，不把代码目录扫描当作能力目录。
- UI contract 单独声明模式、状态、适用页面和可量测约束，并由 CLI 显式检查。
- 行为场景沿真实入口执行并回读 API；观察、布局检查、视觉判断和业务通过分开报告。
- UI 规范引用有效 token 和设计来源，不把某个截图、临时原型或当前实现自动升级为标准。

Chronicle 不引入 Sikao 的 iOS/Admin 账户模型、后端权限矩阵、证据包回收流程或固定视觉数值。UI contract 和 CLI 先覆盖 Markdown 笔记核心路径，再随 JSON、工作簿和 Agent 协作能力扩展。

## 10. 当前实现边界

- `ui/contracts.json` 是 UI contract 的唯一机器可读注册表；Feature Map 的 `ui.contractIds` 只引用稳定 ID，不复制规则。纯 API Feature 用 `ui.hasWebEntry: false` 和 `route: null` 明确排除 Web 检查。`backend/app/schemas/ui_contracts.py` 定义允许的字段、动作、断言和输入类型。
- UI contract 与后端 API schema 分开保存，因为定位器、页面状态和布局规则属于前端。Feature Map 只发布 contract ID，CLI 校验引用与 API operation 仍有效。
- `ui check --feature <id>` 校验 schema、Feature 绑定、API operation、视口范围和源码路径。未映射的 Web Feature 返回 `partial` 和非零退出码；显式无 Web 入口返回 `not_applicable`。结果另列 `scenarioCoverage` 和 `scenarioGaps`，静态 contract 注册不会伪装成业务通过。
- `ui inspect --url <loopback-url>` 返回真实路由、页面标题、可访问树、视口和横向溢出事实，并标为 `observed`、`proof: false`。
- UI `scenario run` 只执行注册的键盘、角色、名称和输入动作。成功结果要求实际页面断言、登记的 API operation 和正式 API 回读全部通过。UI contract 可列出写入 operation；只有已登记的 scenario 才能报告业务结果。
- 当前 `notes.search-visible-result` 场景覆盖 Ctrl+K 全局搜索命令面板，并通过 `/api/search` 回读目标笔记。其他 11 个 Web Feature 已注册 contract，但还没有可执行 UI scenario。
- `ui measure <scenario-id> --repeat N --dataset-size N --run-mode <mode>` 重复同一场景并返回页面就绪、交互和总耗时样本、最近秩 p50/p95、浏览器版本、视口、调用者声明的运行模式和数据规模、Git revision 和相关源码 SHA-256。它不设通过阈值，也不宣称性能提升。
- 当前未实现 `ui compare`、截图差异与人工视觉判定自动化。`notes.search` 的结果层级、文案和视觉品质仍列为人工复核项。
- CLI 不运行仓库测试套件。`ui check` 诊断本地 contract、schema 和 Feature Map 绑定。API `scenario run` 使用正式 HTTP API；UI `scenario run` 和 `ui measure` 操作真实页面。写入通过 `api call <operationId> --confirm` 执行，并按 operation schema 提供 `If-Match` 等必需 header。
