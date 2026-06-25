# 历史长河 TimeLine

一个以时间轴为核心的历史笔记系统，采用 `Vue 3 + FastAPI + SQLite` 构建，适合本地或局域网环境下管理历史专题、维护时间节点并以可视化方式浏览内容。

## 功能概览

- 支持横向与纵向两种时间轴布局
- 支持节点悬停预览、点击查看详情
- 支持专题切换、专题创建与删除
- 支持时间节点新增、编辑、删除
- 支持节点图片上传与旧图片清理
- 支持 JSON 导入、导出
- 支持主题切换与主题变量编辑
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
2. 读取专题列表 `GET /api/data-files`
3. 根据 URL 中的 `topic` 参数选择当前专题
4. 加载专题信息与节点数据
5. 写操作通过 API 提交到后端
6. 后端将主数据写入 `data/timeline.db`

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

- 展示当前专题的时间轴内容
- 支持横向/纵向布局切换
- 支持节点悬停预览与点击详情
- 支持编辑模式下新增、编辑、删除节点
- 支持导入、导出、主题编辑、站点设置

### 编辑器页 `/editor`

- 管理专题列表
- 编辑站点展示文案
- 编辑专题标题与副标题
- 维护节点列表
- 执行导入 JSON、导出 JSON、图片上传等操作

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
- 数据编辑器：`http://localhost:8000/editor`

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
- `POST /api/upload`
- `DELETE /api/media/by-filename/{filename}`
- `DELETE /api/images/{filename}`

### 兼容接口

当前前端仍在使用一组兼容接口，主要包括：

- `GET /api/data-files`
- `POST /api/data-files`
- `DELETE /api/data-files/{topicId}`
- `GET /api/data-meta?topicId=...`
- `PUT /api/data-meta?topicId=...`
- `GET /api/events?topicId=...`
- `POST /api/events?topicId=...`
- `GET /api/export?topicId=...`

说明：

- 后端已经提供新版 REST 风格接口
- 但为了兼容现有前端，部分旧接口仍在保留并实际使用

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

当前仓库中未发现成体系的自动化测试配置或测试目录。

因此目前更准确的说法是：

- 已提供基础运行方式
- 可执行前端构建与后端语法检查
- 主要依赖人工功能验证

如果后续继续演进，建议补充：

- FastAPI 接口测试
- 前端基础 smoke 测试
- 核心数据流的回归测试

## 已知限制

- 更适合本地或局域网部署，当前没有完整的公网部署方案
- 默认管理员密码为固定初始化值，安全性有限
- 主题变量仍存储在 `theme/*.css`，尚未纳入数据库
- 当前兼容接口仍在使用，后续可逐步收敛到新版 REST 接口
- 目前未提供完善的用户管理、审计日志和更细粒度权限模型

## 关键入口文件

- 前端源码入口：`ui/src/main.js`
- 前端路由入口：`ui/src/router/index.js`
- 时间轴页面：`ui/src/pages/TimelinePage.vue`
- 编辑器页面：`ui/src/pages/EditorPage.vue`
- FastAPI 应用入口：`backend/app/main.py`
- 服务启动入口：`backend/server.py`

## 后续建议

如果你准备继续迭代，建议优先考虑以下方向：

1. 增加管理员修改密码功能
2. 为前端和后端补充自动化测试
3. 逐步清理兼容接口并统一 API 风格
4. 将主题变量与更多系统配置纳入数据库管理
