# 历史长河 TimeLine

一个以时间轴为核心的历史笔记系统，采用 `Vue 3 + FastAPI + SQLite` 构建，适合本地或局域网环境下管理历史专题、维护时间节点并以可视化方式浏览内容。

## 功能概览

- 支持三栏时间线笔记界面：左栏分类，中栏时间线，右栏详情/编辑
- 支持专题切换、专题创建与删除，以及全部、今天、本周、收藏、回收站筛选
- 支持标签自动聚合、搜索、时间定位和底部快速记录入口
- 支持时间点新增、Markdown 编辑、收藏、软删除、恢复和永久删除
- 支持附件上传、正文插入和关联时间点选择
- 支持 legacy JSON 导入与 `schemaVersion: 2` 结构化导出
- 支持主题变量接口和基础站点配置
- 支持管理员登录后执行受保护写操作

## 技术栈

前端：

- `Vue 3`
- `Vue Router 4`
- `Vite`

后端：

- `FastAPI`
- `SQLAlchemy`
- `Uvicorn`
- `python-multipart`

数据与资源：

- `SQLite`：主数据存储
- `data/images/`：上传图片目录
- `theme/*.css`：主题变量文件
- `frontend/`：前端构建产物，由后端直接托管

## 系统架构

项目采用“前端源码独立开发、后端统一提供 API 和静态托管”的结构：

- `ui/` 存放前端源码
- `npm run build` 将前端构建到 `frontend/`
- `backend/app/main.py` 创建 FastAPI 应用并挂载 API、图片目录、主题目录和前端静态资源
- 浏览器访问 `http://localhost:8000` 时，实际由 FastAPI 返回 `frontend/index.html`

前端页面启动后的主要数据流如下：

1. 读取站点配置 `GET /api/config`
2. 读取专题列表 `GET /api/topics`
3. 根据 URL 中的 `topic / event / mode / filter / tag / date` 参数恢复当前工作区
4. 加载专题信息 `GET /api/topics/{topicId}/meta`
5. 加载事件列表 `GET /api/topics/{topicId}/events`
6. 写操作通过新版 REST API 提交到后端
7. 后端将主数据写入 `data/timeline.db`

## 目录结构

```text
timeline/
├─ backend/
│  ├─ app/
│  │  ├─ api/         # FastAPI 路由
│  │  ├─ core/        # 核心配置与路径定义
│  │  ├─ db/          # 数据库会话
│  │  ├─ models/      # SQLAlchemy 数据模型
│  │  ├─ schemas/     # Pydantic 模型
│  │  └─ services/    # 业务逻辑与迁移逻辑
│  ├─ requirements.txt
│  └─ server.py       # 启动入口
├─ data/
│  ├─ images/         # 上传图片
│  ├─ config.json     # 站点默认配置
│  ├─ *.json          # 旧版专题 JSON，可作为迁移来源
│  ├─ .auth_secret    # 访问令牌签名密钥
│  └─ timeline.db     # SQLite 数据库
├─ frontend/          # Vite 构建输出目录
├─ theme/             # 主题 CSS 文件
├─ ui/                # Vue 前端源码
├─ package.json
├─ run.bat
└─ README.md
```

## 页面说明

### 时间轴页 `/`

- 展示当前专题的三栏时间线笔记工作区
- 左栏提供专题、主筛选、标签和设置入口
- 中栏提供搜索、时间定位、纵向事件流和底部 composer
- 右栏提供阅读态、Markdown 编辑态、附件、标签和关联时间点
- 支持导入、导出、收藏、回收站、恢复和永久删除

### 兼容重定向 `/editor`

`/editor` 当前作为历史入口保留，并重定向到 `/`。编辑能力已并入右栏详情/编辑面板，不再维护独立 `EditorPage.vue`。

## 快速启动

### 方式一：Windows 一键启动

在项目根目录执行：

```bat
run.bat
```

脚本会自动完成以下步骤：

1. 安装 Python 依赖
2. 安装前端依赖
3. 构建前端
4. 启动 FastAPI 服务

启动后访问：

- 时间轴页面：`http://localhost:8000`
- `/editor` 历史入口会重定向到时间轴页面

### 方式二：手动启动

安装后端依赖：

```bash
python -m pip install -r backend/requirements.txt
```

安装前端依赖：

```bash
npm install
```

构建前端：

```bash
npm run build
```

启动后端：

```bash
python backend/server.py
```

说明：

- 如果未先构建前端，访问根路径时后端会返回 “Frontend has not been built yet”
- 后端默认监听 `0.0.0.0:8000`
- 启动后会打印本机和局域网访问地址

## 开发模式

前端开发服务：

```bash
npm run dev
```

后端开发服务：

```bash
python backend/server.py
```

Vite 开发服务器默认监听 `0.0.0.0:5173`，并将以下路径代理到后端：

- `/api`
- `/images`
- `/theme`

常见开发访问方式：

- 前端开发页面：`http://localhost:5173`
- 后端直出页面：`http://localhost:8000`

## 数据与存储

当前项目已从旧的 JSON 文件模式迁移到数据库模式，主数据以 `SQLite` 为准：

- 数据库文件：`data/timeline.db`
- 图片目录：`data/images/`
- 主题目录：`theme/`
- 默认配置：`data/config.json`
- 鉴权密钥：`data/.auth_secret`

说明：

- 旧专题 JSON 文件仍可保留在 `data/*.json` 作为历史备份
- 页面实际读写的主体数据来自数据库，而不是直接改 JSON 文件
- 主题变量目前仍保存在 `theme/*.css` 中

## 旧数据迁移

应用首次启动时会自动执行以下动作：

1. 初始化数据库结构
2. 初始化默认站点配置
3. 创建默认管理员账号
4. 当数据库为空时，将 `data/*.json` 中的旧专题数据导入 SQLite

迁移后：

- 旧 JSON 文件不会自动删除
- 后续新增或修改的数据默认写入数据库

## 认证与默认账号

系统提供基础登录鉴权，前端会将访问令牌保存到浏览器本地，并在 401 时自动清理登录态并重新弹出登录框。

默认管理员账号：

- 用户名：`admin`
- 密码：`admin123456`

安全提示：

- 该默认账号会在首次初始化时创建
- 当前 README 保留了默认密码说明，仅适合本地或受控环境使用
- 建议首次进入系统后尽快替换为你自己的管理员密码

## API 概览

### 认证接口

- `POST /api/auth/login`
- `GET /api/auth/me`

### 站点配置

- `GET /api/config`
- `PUT /api/config`

### 新版专题接口

- `GET /api/topics`
- `POST /api/topics`
- `GET /api/topics/{topicId}`
- `DELETE /api/topics/{topicId}`
- `GET /api/topics/{topicId}/meta`
- `PUT /api/topics/{topicId}/meta`
- `GET /api/topics/{topicId}/events`
- `POST /api/topics/{topicId}/events`
- `POST /api/topics/{topicId}/import`
- `GET /api/topics/{topicId}/export`

### 节点接口

- `PUT /api/events/{eventId}`
- `DELETE /api/events/{eventId}`

### 主题与媒体

- `GET /api/themes`
- `GET /api/themes/{name}/vars`
- `PUT /api/themes/{name}/vars`
- `POST /api/media/upload`
- `DELETE /api/media/by-filename/{filename}`

### 兼容接口

后端仍保留一组兼容接口，供旧数据流或历史调用使用。当前前端 API 封装已转向新版 REST 路由。

- `GET /api/data-files`
- `POST /api/data-files`
- `DELETE /api/data-files/{topicId}`
- `GET /api/data-meta?topicId=...`
- `PUT /api/data-meta?topicId=...`
- `GET /api/events?topicId=...`
- `POST /api/events?topicId=...`
- `GET /api/export?topicId=...`
- `POST /api/upload`
- `DELETE /api/images/{filename}`

说明：

- 后端已经提供新版 REST 风格接口
- 当前主前端不再直接依赖这些兼容接口；旧命名的前端方法只转发到新版 API

## 常用命令

安装依赖：

```bash
python -m pip install -r backend/requirements.txt
npm install
```

前端开发：

```bash
npm run dev
```

前端构建：

```bash
npm run build
```

前端预览：

```bash
npm run preview
```

启动后端：

```bash
python backend/server.py
```

后端语法检查：

```bash
python -m py_compile backend/server.py
```

后端模块编译检查：

```bash
python -m compileall backend/app backend/server.py
```

## 测试现状

当前仓库已有轻量自动化验收入口：

- `cmd /c npm run agent:check`
- `cmd /c npm run build`
- `cmd /c npm run test:ui`
- `python -m pytest tests/test_timeline_api.py tests/test_date_utils.py`

其中 `test:ui` 使用 Node 内置测试运行 `ui/tests/*.test.js`，后端测试覆盖 timeline API、导入导出、日期工具和事件状态契约。

## 已知限制

- 更适合本地或局域网部署，当前没有完整的公网部署方案
- 默认管理员密码为固定初始化值，安全性有限
- 主题变量仍存储在 `theme/*.css`，尚未纳入数据库
- 后端兼容接口仍保留，后续可视情况收敛或删除
- 目前未提供完善的用户管理、审计日志和更细粒度权限模型

## 关键入口文件

- 前端源码入口：`ui/src/main.js`
- 前端路由入口：`ui/src/router/index.js`
- 时间轴页面：`ui/src/pages/TimelinePage.vue`
- FastAPI 应用入口：`backend/app/main.py`
- 服务启动入口：`backend/server.py`

## 后续建议

如果你准备继续迭代，建议优先考虑以下方向：

1. 增加管理员修改密码功能
2. 扩展前端交互 smoke 测试和视觉 QA 自动化记录
3. 逐步清理后端兼容接口并统一 API 风格
4. 将主题变量与更多系统配置纳入数据库管理
