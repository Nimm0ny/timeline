# 编年 API 与 CLI 契约规范

**状态：** 新应用 API 与 CLI 的目标规范。旧接口不构成兼容要求；迁移功能时直接迁移到本规范，不新增第二套读写实现。

本文使用“必须”“应该”“可以”表达要求强度。“必须”项是接口验收条件。

## 1. 目标和不变量

编年面向人和 LLM Agent 提供同一份笔记应用。人类通过 Web 完成日常笔记工作；Agent 通过 CLI 发现能力、执行有范围的操作并检查结果。两者调用同一套正式 HTTP API，读取同一份持久化状态。

以下条件必须同时成立：

- 普通 Markdown 笔记是默认且完整可用的内容类型。
- JSON、电子表格等格式通过独立格式适配器扩展；不得把未知格式静默转成 Markdown 或不透明文本。
- Feature Map 是 UI 入口、API operation、状态所有者、CLI 操作和可运行场景之间的共同能力目录。
- OpenAPI 和请求/响应 schema 定义线上的字段、类型、空值和错误契约。Feature Map 引用这些 schema，不复制另一份字段定义。
- CLI 只执行 Feature Map 中登记的具名操作，通过正式 HTTP API 工作；不得直接写数据库、拼任意 URL、执行任意 SQL 或页面脚本。
- 写入必须说明对象身份、基于的版本、重试身份、持久化结果和回读方式。
- Agent 的笔记修改先成为有范围、绑定版本的建议；必须由用户确认后才写入正文。过期建议不得覆盖新版本。

## 2. 契约来源与职责

### 2.1 唯一线上 schema

- 每个 HTTP operation 必须声明输入 schema、输出 schema、成功状态码和可能的错误响应；不得用无约束的 `dict` 代替公开请求或响应模型。
- OpenAPI 是 HTTP 契约的机器可读投影。前端类型应从 OpenAPI 生成；CLI 应使用同一份 schema 或其生成类型验证输入和输出。
- 如果未来更换 Web 框架、语言或数据库，线上的 operation、schema、错误和版本语义仍须保持本规范定义的行为；替换技术栈不能生成第二份产品逻辑。
- 请求对象必须拒绝未知字段。可选字段、可空字段、缺省值和“清空”语义必须分别定义。
- JSON 字段使用 lower camel case；资源 ID 使用不透明 UUID；时间使用 UTC RFC 3339。客户端不得推断 ID 内部结构或用时间戳代替版本号。

### 2.2 API operation 身份

- 每个 operation 有稳定、唯一、命名空间化的 `operationId`，例如 `notes.read`、`notes.update`。
- 修改 URL 或实现时，不因路由函数名、Vue 组件名或文件名变化而更换 operation ID。
- 一个 operation 必须在 OpenAPI 中声明 path/query/header/body 参数和响应 schema。实际路由、Feature Map 与 CLI 注册项必须能通过 `operationId` 对上。
- 破坏性契约变化必须升级 API 主版本或明确的新 operation；不得在同一个字段上悄悄改类型或含义。

### 2.3 Feature Map

Feature Map 描述“用户或 Agent 能完成什么”，不代替 OpenAPI，也不是组件或路由清单。每项能力至少登记：

- 稳定 `featureId`、标题和简短说明。
- 对应的 Web 入口和 CLI 命令。
- 关联的 `operationId`、HTTP method、path、请求/响应 schema 引用、查询 schema 和必需 headers。
- 状态所有者、数据范围、前置条件、权限要求和持久化结果。
- 失败后的恢复方式，以及可运行场景 ID。
- 当前生命周期：`planned`、`active` 或 `retired`。未实现能力不得伪装成可执行操作。

`feature list` 只返回目录摘要；`feature describe <featureId>` 返回能力、operation、schema 引用和场景详情。CLI 必须能用 Feature Map 检查 operation 是否仍存在于 OpenAPI，并在不一致时报告明确的 drift 错误。

## 3. 文档数据类型

所有可编辑内容共用文档信封，但正文由格式适配器定义。目标信封如下：

```ts
type Document<TFormat extends string, TContent> = {
  id: UUID;
  workspaceId: UUID;
  notebookId: UUID | null;
  title: string;
  formatId: TFormat;
  formatVersion: number;
  content: TContent;
  tags: string[];
  properties: Record<string, JsonValue>;
  revision: number;
  createdAt: string;
  updatedAt: string;
  deletedAt: string | null;
};
```

- Markdown 适配器声明 `content` 为 Markdown 源文本，保存和读取不得重排用户正文。
- 每个新增格式必须提供自己的请求、响应和内容 schema，并登记适配器版本及支持的读取、编辑、搜索、导入、导出能力。
- `formatId` 未知时返回 `document.format_unsupported`，包含所请求格式和当前支持格式；不得创建部分文档。
- 列表项使用独立的摘要 schema，不返回完整正文；分页响应固定包含 `items`、`hasMore` 和不透明 `nextCursor`。
- 标签、属性、回收站状态和笔记本归属是显式字段。不得将其塞入格式正文或依赖前端私有约定。

## 4. 写入、版本和幂等语义

- 每个文档有单调递增的 `revision`。成功的正文、元数据或生命周期写入只递增一次。
- 更新、回收和恢复必须带 `If-Match` 当前版本条件。缺少版本条件返回 `428 precondition_required`；版本过期返回 `409 document.revision_conflict`，并提供提交版本和当前版本。
- 每个可能改变持久状态的请求必须带 `Idempotency-Key`。同一作用域中，相同 key 和相同 method/path/body 重放返回首次结果；相同 key 用于不同请求返回 `409 operation.idempotency_conflict`。
- 服务端必须在事务内完成数据写入、版本记录、索引更新和幂等回执；不得出现正文已成功但回执或搜索状态未更新的半完成结果。
- 写入成功响应必须返回稳定资源 ID、最新 revision 和可回读标记。客户端必须通过正式 read operation 确认未知结果；网络超时后应重用原幂等 key，不得盲目创建第二个对象。
- 删除默认是可恢复的软删除。永久删除属于独立、明确、不可逆的 operation，不能复用“移入回收站”。
- Agent 建议必须记录 workspace、document、base revision、授权范围、建议内容和状态。接受建议时再次检查 base revision；不匹配则拒绝覆盖并返回冲突。

## 5. 错误契约

HTTP API 和 CLI 使用同一错误语义。每个预期失败都必须有稳定错误码；不能只返回不稳定的异常文本或 FastAPI 默认错误体。

```ts
type FieldError = {
  path: string;       // RFC 6901 JSON Pointer，例如 /content/title
  message: string;
  code: string;       // 稳定的验证规则标识
};

type NextAction =
  | { kind: "operation"; operationId: string; input: JsonValue; label: string; requiresApproval: boolean }
  | { kind: "command"; command: string; label: string; requiresApproval: boolean }
  | { kind: "manual"; instruction: string };

type ErrorEnvelope = {
  error: {
    code: string;
    message: string;
    requestId: UUID;
    retryable: boolean;
    fieldErrors: FieldError[];
    details: JsonValue;
    nextAction: NextAction;
  };
};
```

- 错误码采用小写点分命名，例如 `request.validation_failed`、`document.revision_conflict`。发布后不得改变已有错误码含义。
- HTTP status 与错误码必须一致：schema 验证 `422`、资源不存在 `404`、版本冲突 `409`、缺少版本条件 `428`、暂时不可用 `503`。
- `fieldErrors.path` 使用 JSON Pointer；同一错误在 UI、CLI 和 API 中必须返回相同字段位置与错误码。
- `details` 按错误码定义字段，不使用任意 `Any` 字段作为逃逸口。版本冲突至少返回 `documentId`、`submittedRevision` 和 `currentRevision`；不支持格式至少返回 `formatId` 和 `supportedFormats`。
- `retryable` 只在相同请求可以安全重试时为 `true`。冲突不是瞬时错误，必须先回读并协调。
- `nextAction` 必须具体且带真实资源参数。operation 类型只能引用 Feature Map 中登记的 operation；会写入的下一步必须设置 `requiresApproval: true`。禁止 `nextAction` 使用“重试一下”或未替换的 `<id>` 占位符。
- 服务器必须生成 `requestId`，并在响应 header 与错误体中返回，以便 CLI 日志和应用日志关联。

## 6. CLI 契约

### 6.1 发现与操作

CLI 必须包括：

- `feature list`、`feature describe`：能力发现和按需 schema 展开。
- `note`、`topic` 和其他产品命令；命令参数和执行使用同一 schema。
- `api list`、`api describe` 或等价命令：显示 operation ID、method、path、输入/输出 schema、必需 headers、状态码和错误码。
- `api call`：只执行 Feature Map 登记的 operationId；写入必须带 `--confirm`，笔记更新和删除必须带 `If-Match`。
- `doctor`：检查服务身份、OpenAPI、Feature Map 与 API operation 的对应关系；只报告实际执行的检查。
- `scenario list/run`：运行 Feature Map 登记的可复现业务场景。
- `dev up/status/doctor/logs/down`：启动和检查开发服务，停止时仅处理 CLI 能验证为自己启动的进程。
- CLI 不管理或运行仓库测试套件。测试套件由独立的开发或 CI 工具管理。

CLI 不得提供任意 URL/path 代理。若允许 `api call`，它只能接受 Feature Map 登记的 `operationId`，按该 operation 的 schema 校验 path、query、headers 和 body。
二进制响应要求调用者提供一个尚不存在的 `--output-file` 路径；CLI 不覆盖已有文件。

### 6.2 输出和退出码

- stdout 每次命令只输出一个 UTF-8 JSON 对象。人类进度、调试信息和子进程输出写入 stderr，不污染 JSON。
- 成功结果至少包含 `status: "succeeded"`、`command`、`result`；API operation 命令还包含 `featureId`、`operationId` 和 `requestId`（服务可提供时）。
- 失败结果至少包含 `status: "failed"` 和完整 `ErrorEnvelope`。参数验证错误也必须指出字段路径、规则和可执行修正方式。
- 退出码固定为：`0` 成功，`1` API/应用操作失败，`2` CLI 参数或本地配置无效，`130` 用户中断。
- CLI 不得在失败时自动重试非幂等写入。需要重试时必须复用原 `Idempotency-Key`，并在未知结果中输出该 key。
- `dev up` 默认使用独立的开发数据目录。端口被占用时报告冲突，不接管、不终止外部进程。CLI 启动一个管理进程，由它持有 API 和 Vite 的子进程句柄。`dev down` 只向带随机 token 的管理进程发送关闭请求；管理进程不可达时，CLI 不按 PID 强制终止进程。

### 6.3 CLI 参数示例

以下是使用体验契约。实际参数必须与 API schema 和 Feature Map 保持一致：

```bash
chronicle dev up
chronicle feature describe notes.create
chronicle topic list
chronicle note get --note-id 1
chronicle api call notes_create --confirm --input-file ./create-note.json
chronicle api call notes_update --confirm --input-file ./update-note.json
chronicle api call media_read --input-file ./read-media.json --output-file ./attachment.bin
chronicle scenario run notes.search-readback --query "检索词" --expected-note-id 1
chronicle dev down
```

CLI 必须在 `--help` 和 `feature describe` 中说明参数类型、是否必需、默认值、格式限制和副作用；不得要求 Agent 从源码猜参数。

## 7. Web 契约

- Web API 客户端必须使用从 OpenAPI 生成的类型；不得维护字段含义相同但可漂移的手写接口副本。
- 请求必须通过共享 API 客户端执行，以统一 request ID、超时、取消、错误解析和幂等 headers。
- UI 保存流程必须跟踪当前 revision、保存状态和未知结果；收到冲突时保留本地草稿并显示回读/比较/重新应用路径。
- UI 和 CLI 必须映射到相同的 operation 和错误码。允许展示方式不同，不允许语义不同。
- 没有实现服务端写入和回读的界面控件不得显示为可用功能。

## 8. Feature Map 场景和验证

每个可运行场景必须声明：

- `scenarioId`、输入 schema、前置状态和所需权限。
- 使用的 operation ID 与顺序；步骤不得绕过正式 API 或直接改数据库。
- 可观察断言、预期持久状态、冲突检查和未知结果恢复办法。
- 清理范围及其是否可恢复。默认禁止永久删除或访问用户数据库。
- 是否需要截图、trace 或完整日志。没有视觉判断需求时默认不生成证据文件。

场景必须在真实 HTTP 服务上验证；纯服务健康、页面加载或 mock 响应不算业务场景通过。单元测试保护边界行为，CLI 场景验证端到端契约，性能测量记录 p50/p95、样本数、数据规模、环境和源码版本。

## 9. 设计、实现与变更流程

每项跨层功能先写出真实调用方式，再倒推契约和实现：

1. 写一个人类 UI 操作和一个 Agent CLI 命令的使用示例。
2. 定义 operation ID、请求/响应类型、状态所有者、错误和恢复路径。
3. 检查正常、非法字段、资源不存在、权限不足、版本冲突、重放和未知结果。
4. 实现 API、Feature Map、CLI、Web 客户端和场景；保持唯一的持久化写路径。
5. 用真实隔离服务运行场景，再测量受影响的列表、打开、搜索、保存或服务启动路径。
6. 如果调用方反复补参数、依赖 `Any`/强制转换、重复写适配逻辑或无法安全重试，视为契约/架构不合格；先修正边界，再扩展功能。

一个 operation 的新增或变化必须在同一改动中同步更新：OpenAPI schema、Feature Map、CLI 参数和帮助文本、Web API 类型、场景/行为验证以及相应的参考文档。检查 API schema 与 Feature Map drift。移除能力时先从 Feature Map 标记或移除，再删除入口；不得遗留看似可用的空壳命令。

## 10. 文档分工

本文是 API/Feature Map/CLI 的规范参考，不兼作新手教程、操作步骤和架构背景说明。教程和常见任务步骤应单独编写；架构选择与取舍应单独解释。CLI 的实际帮助、Feature Map 和 OpenAPI 必须与文档规范保持一致。
