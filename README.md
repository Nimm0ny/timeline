# 编年 Chronicle

编年是一个本地优先、以普通 Markdown 笔记为核心的应用。仓库名为 `timeline`；时间线是笔记的一种集合视图，不再代表产品的全部定位。

## 产品定位

编年面向用户与 Agent 共同维护笔记。用户可以让 Agent 订正文字、优化格式或扩写内容；Agent 的工作应限定在用户授权的笔记和范围内，并基于明确的笔记版本提出建议。用户查看差异后决定接受、拒绝或继续修改。旧版本建议不能覆盖用户之后的编辑。

计划由用户连接外部 Agent 运行时。编年不托管模型或凭据；真实模型调用、凭据读取及费用操作需要另行授权。

## 产品范围

产品范围包括：

- 普通 Markdown 笔记，以及笔记本和书架等组织方式。
- 时间线、列表、表格、看板、画廊和大纲等集合视图。
- 标签、属性、搜索、收藏、附件和回收站等日常笔记能力。
- FastAPI、Web 客户端和 CLI 共用有类型的 API 契约；写入围绕笔记身份、版本、操作身份和回读设计。
- Feature Map 与 CLI，让用户和 Agent 能发现正式 API 操作、执行 schema 校验的读写操作并运行可复现的场景。

产品目标不包括知识图谱能力：思维导图、自由画布、图关系浏览、反向链接和自动链接解析。普通 Markdown 正文、标签、属性和集合视图仍属于产品范围。

既有图形笔记、关联数据、数据库、附件和备份都是用户数据。任何转换或迁移都应先预览，再在数据库副本上核对，并保留恢复方式；不得因产品方向变化而自动删除或覆盖这些数据。

## 当前实现状态

图形笔记、画布、笔记链接与反向链接已从后端 Feature Map、API 路由和 Web 界面移除。旧 `data/timeline.db` 仍保留在原位置，应用不会导入或迁移其中的数据。新应用默认使用 `.chronicle-data/`。

CLI 通过 OpenAPI 与 FastAPI 共享 schema 验证全部 32 个 active API operation。写入通过正式 HTTP API 执行；命令需要 `--confirm`，笔记更新和删除还要提供 `If-Match` 版本。CLI 不访问 SQLite，也不提供任意 API 代理或页面脚本。12 个 Web Feature 都有 UI contract，目前只有笔记搜索有可执行浏览器场景。

Agent 提交建议、用户审阅差异、接受后保存的完整共写界面仍是产品目标，尚未端到端交付。README 中的产品方向不代表这些能力已全部实现。

## 技术架构

- 前端：Vue 3、Vue Router、Vite。
- 后端：FastAPI、SQLAlchemy、Uvicorn。
- 主数据库：SQLite，默认位于 `.chronicle-data/timeline.db`。
- 图片和附件：存放于 `.chronicle-data/images/`。
- Feature Map：由后端注册信息提供，CLI 与正式 API 共用。

`CHRONICLE_DATA_DIR` 可指定另一份应用数据目录。未设置时使用仓库根目录下的 `.chronicle-data/`。旧 `data/timeline.db` 保持原样，应用启动不会导入或迁移它。

前端源码位于 `ui/`。运行 `npm run build` 后生成后端托管的 `frontend/` 构建产物。FastAPI 提供应用 API，并托管前端和资源。

## 快速启动

Windows 可在仓库根目录运行：

```bat
run.bat
```

也可手动安装并启动：

```bash
python -m pip install -r backend/requirements.txt
npm install
npm run build
python backend/server.py
```

默认访问地址为 `http://localhost:8000`。前端开发模式可另开终端运行：

```bash
npm run dev
```

Vite 默认监听 `http://localhost:5173`，并将 API 请求代理到后端。

## CLI

开发时用 CLI 启动独立 API 和 Vite 服务，再通过 `tools/chronicle_cli.py` 访问正式 HTTP API：

```bash
python tools/chronicle_cli.py dev up
python tools/chronicle_cli.py dev status
python tools/chronicle_cli.py dev doctor
python tools/chronicle_cli.py dev logs --service all
python tools/chronicle_cli.py --base-url <apiUrl> feature list
python tools/chronicle_cli.py --base-url <apiUrl> feature describe notes.read
python tools/chronicle_cli.py --base-url <apiUrl> note list --topic-id 1
python tools/chronicle_cli.py --base-url <apiUrl> note get --note-id 1
python tools/chronicle_cli.py --base-url <apiUrl> note search --query "关键词"
python tools/chronicle_cli.py --base-url <apiUrl> api list
python tools/chronicle_cli.py --base-url <apiUrl> api describe notes_get
python tools/chronicle_cli.py --base-url <apiUrl> api call notes_get --input-json '{"path":{"note_id":1}}'
python tools/chronicle_cli.py --base-url <apiUrl> api call media_read --input-json '{"path":{"filename":"<filename>"}}' --output-file ./attachment.bin
python tools/chronicle_cli.py --base-url <apiUrl> api call notes_update --input-json '{"path":{"note_id":1},"headers":{"If-Match":"<updatedAt>"},"body":{"headline":"新标题","bodyMarkdown":"正文","items":[]}}' --confirm
python tools/chronicle_cli.py scenario list
python tools/chronicle_cli.py ui guide --contract notes.search
python tools/chronicle_cli.py ui check --feature notes.search
python tools/chronicle_cli.py ui inspect --url <uiUrl> --viewport-width 390 --viewport-height 844
python tools/chronicle_cli.py --base-url <apiUrl> ui measure notes.search-visible-result --ui-url <uiUrl> --input-json '{"query":"词条关键词","expectedNoteId":1,"expectedHeadline":"目标笔记标题"}' --repeat 5 --dataset-size 1 --run-mode development
python tools/chronicle_cli.py --base-url <apiUrl> doctor
python tools/chronicle_cli.py --local-catalog feature list
python tools/chronicle_cli.py dev down
```

将 `<apiUrl>` 和 `<uiUrl>` 替换为 `dev up` 返回的地址。CLI 为每个开发会话创建独立数据目录；`dev down` 停止本次会话启动的服务并保留该目录。

CLI 默认连接 `http://127.0.0.1:8000`，也可以传入 `--base-url`。结果以 JSON 写入 stdout；`--debug` 将诊断进度写入 stderr。CLI 只运行 Feature Map 中已登记且 lifecycle 为 `active` 的 operation。写入必须带 `--confirm`，笔记更新和删除还必须带读取时的 `If-Match` 版本。

`api call` 只接受 Feature Map 中的 `operationId`，并按 OpenAPI 参数及 FastAPI schema 校验输入和响应。二进制读取要求提供一个尚不存在的 `--output-file` 路径，CLI 不覆盖已有文件。`--local-catalog` 从当前工作树读取目录，不需要服务；实际 API 调用仍通过 HTTP。`ui guide` 和 `ui check` 读取本地 contract 并核对全部 Web Feature 的绑定；`ui inspect` 观察可访问的 loopback 页面。当前真实浏览器场景覆盖搜索流程。`ui check` 会单独列出还没有可执行 UI 场景的 Feature，不把静态 contract 检查报告成业务通过。`ui measure` 重复运行已登记的 UI 场景并报告耗时。CLI 不管理或运行仓库测试套件。

## 数据与安全

- 应用当前按本地或局域网单用户模式运行，不提供账号认证。
- 旧 `data/timeline.db`、附件、图形笔记及关联数据均视为用户数据，不得直接清理。
- 默认应用数据位于 `.chronicle-data/`。应用不会从旧 `data/` 自动迁移内容。
- CLI 通过 HTTP API 读写应用，不直接写 SQLite。
- 迁移先做 dry-run 并在副本上验证；未获用户明确指令，不对现有数据库执行内容迁移或永久删除。
- Agent 写入应绑定笔记身份和来源版本，并处理冲突、未知结果及回读；用户确认前不得覆盖正文。

## 开发检查

按改动选择相关检查，不需要每次运行整套命令：

```bash
npm run agent:check
npm run build
python tools/generate_api_types.py --check
```

当前仓库不保留自动化测试文件。CLI 的场景执行和测量仍可直接验证真实页面行为；新增测试文件需先按 `AGENTS.md` 的规则通过 test-audit 必要性审查。

## 常用入口

- 前端页面：`ui/src/pages/NotesPage.vue`
- 前端 API 客户端：`ui/src/composables/useApi.js`
- FastAPI 应用：`backend/app/main.py`
- Feature Map：`backend/app/features.py`
- CLI：`tools/chronicle_cli.py`
- Python 依赖：`backend/requirements.txt`
