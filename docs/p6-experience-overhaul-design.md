# P6 · 编年 Chronicle 性能与体验重构 — 实现设计

> 本文是「性能 / 存储 / 跨本视图 / 搜索 / 编辑器」一轮重构的实现基准，供执行代理（含 Codex）**逐阶段**落地。
> 优先级：在本文涵盖范围内，本文为权威设计；与旧文档冲突时，以 **用户当前要求 → 本文 → AGENTS.md §9 硬约束 → 当前代码实际契约（§1）** 为准。
> 性质：数据契约 + 跨模块 + 视觉基准 + 新依赖 → **强制触发 review gate**。必须分阶段、逐阶段对照验收，禁止带病推进。

## 执行须知（每阶段开工前必读）
1. 读 `AGENTS.md`（尤其 §9 前端硬约束：令牌/图标纪律、右栏阅读↔编辑零位移、自适应无 scale、全局禁滚动条、行高固定）。
2. 读本文对应阶段 + §1「现状契约」+ §11「自检」。
3. 视觉阶段另读 `docs/obsidian-minimal-implementation-spec.md`、`prototypes/timeline-obsidian-minimal.html`、`docs/agent-frontend-hardness.md`。
4. 按 §2 阶段顺序，**P6-A 必须先落地**（其余多依赖它）。每阶段独立可验收、可提交。
5. 不臆造字段/数据；不顺手重构无关代码；不新增除 Pillow(后端)/CodeMirror6(前端编辑器阶段)外的依赖。

---

## 0. 目标与边界（Define-First）

- **Goal**：切换笔记本秒开、媒体小而快、收藏/搜索成为可用的**跨本**视图、编辑器升级路线清晰；既有不变量零回归。
- **Non-goals（本轮不做）**：笔记本真层级（**此旧决策已被 `docs/bookshelf-hierarchy-design.md` 取代，不再适用**）；知识类无日期笔记；多用户/协作；迁移 Postgres（SQLite 留用，见 §0.1.1）；CM6 编辑器实现（本文只排期，另立文档）。
- **Scope**：前端数据层、后端媒体管线、跨本来源标识、收藏视图、搜索命令面板（UI 壳 + FTS5 管线）、关联事件 modal、CM6 编辑器路线。
- **Verification**：各阶段「验收」+ §8 总验收；`npm run agent:check / build / test:ui` + `python -m pytest` 全过；视觉改动按 `docs/agent-frontend-hardness.md` 归档 1920×1080 截图至 `docs/visual-qa/`。

### 0.1 决策基线（用户已拍板，执行勿再问）
1. **SQLite 留用，不迁库**。理由：文本结构化数据极小（6 万条 × 5KB ≈ 300MB，SQLite 轻松），单人/读多写少碰不到并发写瓶颈；附件走文件系统、DB 只存引用。需迁库的边界（多人并发写 / 多 app server / 公网多租户）当前都不成立。
2. **媒体默认压缩**（WebP），设置开放「保留原图」开关；开源方案 = **Pillow 库**（进程内上传即处理），非 imgproxy 那类服务（那类存原图、省带宽不省存储）。
3. **笔记本平铺**，不做层级（**此旧决策已被 `docs/bookshelf-hierarchy-design.md` 取代，不再适用**）。
4. **收藏 = 跨本视图**，每行须清晰显示**来源笔记本**。
5. **搜索 UI 参考 Codex 命令面板**（仅参考 UI）；搜索**功能**（字段权重/范围/模糊/属性过滤/排序）**另立设计**，本文只定 UI 壳 + FTS5 管线 + 结果契约。
6. **编辑器走 CodeMirror 6**（AGENTS §9 唯一预批依赖）实现 Typora 式实时渲染，分期，细节另立 `docs/editor-cm6-design.md`。

---

## 1. 现状契约（base of truth，执行前核对真实代码，勿臆改）

> 行号对应当前 `backend/app/services/timeline.py` 等，落地时以实际代码为准。

- **事件序列化** `event_to_dict`（timeline.py:347）字段：`id, nodeType, dateKey, sortKey, isoDate, dateParts{year,month,day}, headline, displayLabel, legacyYear, era, image, imageUrl, bodyMarkdown, extra{}, attachments[], relatedEventIds[], relatedEvents[], createdAt, updatedAt, favorite, deletedAt, items[]`。**⚠ 缺 `topicId`**。
- **列表** `query_topic_events`（:552）返回 `{items, bounds, range, hasMore, nextCursor}`；`limit=None` 时**返回全部**（无分页截断）。
- **`list_topics`**（:463）已含每本 `columns`（见 `topic_to_dict` :50）+ `eventCount` + 日期 bounds。→ **「全量加载」无需 N 次 meta 调用**。
- **事件部分更新** `update_event`（:854）：payload 键 ⊆ `EVENT_STATE_KEYS`（favorite / deletedAt）→ 走轻量 `apply_event_state`（:97）；否则全量 `normalize_event_payload`。→ 收藏/软删/恢复**已是**轻量 patch；事件端点收 raw `dict`（非严格 `TimelineEventIn`），支持部分字段。
- **无 `GET /api/events/{id}`**：当前 `/api/events/{id}` 只有 PUT/DELETE；事件详情现仅经 `/api/topics/{id}/events` 列表整体返回。→ 懒加载详情**需新增** `GET /api/events/{id}`。
- **媒体上传** `store_uploaded_image`（:1024）：`uuid.hex[:10]+ext` 文件名、**原样落盘**（无压缩/缩略图/去重）、写 `ImageAsset(filename, original_name, mime_type, is_orphan)`；返回 `{id, filename, originalName, mimeType, url, imageUrl}`。允许 ext：jpg/jpeg/png/gif/webp/svg/pdf/md/txt/docx。
- **媒体服务**：`/images/{filename}` 静态（**无强缓存头**）。
- **前端数据流**：`pages/TimelinePage.vue` 的 `loadWorkspace` 每次切换/写后都重拉 `config + listTopics + meta + events` 且置 `state.loading=true`（→ `TopicSidebar` 笔记本树被「正在加载笔记本…」占位重建、中栏整屏白）= **切换卡顿根因**。

---

## 2. 阶段总览与依赖顺序

| 阶段 | 内容 | 依赖 |
|---|---|---|
| **P6-A** | 前端数据层（全量轻索引缓存 / 懒详情 / 写时 patch） | 无（**先做**） |
| **P6-B** | 后端媒体管线（Pillow/WebP/缩略图/去重/缓存头/设置） | 无（可并行 A） |
| **P6-C** | 跨本来源标识 + 收藏视图 | A |
| **P6-D** | 搜索命令面板（Codex 式 UI + FTS5 管线） | A |
| **P6-E** | 关联事件 modal 卡片 | A（懒详情） |
| **P6-F** | CM6 编辑器（另立文档，最后做） | A、E |

附：外观修复 ①②④⑤ 已由主代理完成（§9），**非 Codex 范围**。

---

## 3. P6-A 前端数据层

### 目标
启动一次性载入「轻量索引」（全本全事件元数据），切换笔记本 = 本地过滤（**零网络、不 blank 左栏**），详情/媒体懒加载，写操作就地 patch 缓存，删除 `loadWorkspace` 全量重载。

### 后端
1. `event_to_dict` 增 `"topicId": event.topic_id`（全站受益，不破坏现有消费方）。
2. 新增 `event_to_index_dict(event)` —— 只产**轻量**字段，避免给索引塞全文：
   ```jsonc
   { "id", "topicId", "dateKey", "isoDate", "displayLabel", "headline", "era",
     "extra": {…}, "favorite", "deletedAt", "createdAt", "updatedAt",
     "preview": "正文前~90字纯文本", "attachmentCount": 0 }
   ```
3. 新增 `GET /api/index` → `{ "topics": list_topics(db), "events": [ event_to_index_dict … 全本未删+已删均含, 由前端按 deletedAt 分流 ] }`。
4. 新增 `GET /api/events/{id}` → `event_to_dict` 全量（bodyMarkdown + attachments + relatedEvents）。
5. `query_topic_events` / `/api/topics/{id}/events` **保留**（导出/兼容），前端主路径改用 index。

### 前端
- 新增 `ui/src/composables/useTimelineStore.js`：持有 `topics`、`eventsIndex`（全量轻量，`Map<id>` + 按 `topicId` 分组）、`detailCache: Map<id, fullEvent>`。
- 启动：`api.getIndex()` 一次填充；`TimelinePage` 不再每次 `loadWorkspace` 全量。
- **切换笔记本**：仅改 `activeTopicId` + 本地过滤 `eventsIndex`，不发请求、不 blank 左栏。
- **打开事件**：`detailCache` 命中直接用；否则 `api.getEvent(id)` 懒拉并缓存；右栏正文/附件用详情。
- **写时 patch**：create/update/favorite/trash/restore/permanent 调对应 API 后，用返回值**就地更新** `eventsIndex`（+ `detailCache`），失败回滚；不再 `loadWorkspace`。
- 中栏 loading：用 `state.eventsLoading`（仅 feed）替代会 blank 左栏的全局 `state.loading`。
- **保持**现有筛选/分期/搜索/URL 同步行为**不变**，仅替换数据来源（回归面大，逐项对照）。

### 文件映射
- 后端：`api/topics.py`（+`GET /api/events/{id}`、`GET /api/index`，或新 `api/index.py`）、`services/timeline.py`（`event_to_index_dict`、`build_index`、`topicId`）。
- 前端：`composables/useApi.js`（`getIndex`/`getEvent`）、新增 `composables/useTimelineStore.js`、`pages/TimelinePage.vue`（数据流重写）、`TopicSidebar.vue`/`TimelineFeed.vue`（仅改 loading 来源，props 接口尽量不变）。

### 验收
- 冷启动后切任意笔记本：**无网络请求、左栏树不闪、瞬时出列表**。
- 造 5k+ 事件：首屏一次拉 index、切换仍秒级。
- 收藏/软删/编辑后列表就地更新、无整屏闪。
- 详情首开懒拉、二次命中缓存。

### 风险
- index 体量：5k × ~0.3KB ≈ 1.5MB，OK；预留 `?topicId=` 退化按需（极大数据时，见 §10.5）。
- 与 URL/筛选耦合重 → 必须逐项回归现有行为。

---

## 4. P6-B 媒体管线（后端）

### 目标
上传即压缩（WebP）+ 生成缩略图 + 内容去重；强缓存头；压缩/保留原图可设置。一处改动同时满足「存储小」与「加载快」。

### 处理（`store_uploaded_image` 重写）
- **图片**（jpg/jpeg/png/webp/gif；svg 不解码转码）：
  - Pillow 解码 → 抹 EXIF → 长边 ≤ `maxEdge`(默认 1920) → 编码 WebP q=`quality`(默认 80) → 工作版 `<hash>.webp`。
  - 缩略图：长边 ≤ `thumbEdge`(默认 400) WebP → `<hash>.thumb.webp`。
  - `keepOriginal` 为真：另存 `<hash>.orig<ext>`。
- **非图片**（pdf/md/txt/docx/svg）：原样 `<hash><ext>`，无缩略图。
- **内容寻址 + 去重**：`hash = sha256(content)[:16]`；同 hash 已有则复用，不重复落盘（`ImageAsset` 按 `content_hash` 查重）。
- 返回扩展：`{ id, filename, thumbFilename, originalFilename?, mimeType, width, height, bytes, url, thumbUrl, originalUrl?, imageUrl }`。

### 模型（`models/entities.py` · `ImageAsset` 扩展）
新增列：`content_hash`(唯一索引)、`thumb_filename`、`original_filename`(nullable)、`width`、`height`、`bytes`。迁移：加列，随启动幂等；旧记录不强制回填，旧文件照常服务。

### 服务 / 缓存头
- `/images/{filename}` 及缩略图响应加 `Cache-Control: public, max-age=31536000, immutable` + `ETag`(=content hash)。
- 缩略图走约定 `<hash>.thumb.webp` 静态，或 `GET /images/thumb/{filename}`。

### 设置（config + `SettingsModal`）
- config 增 `media: { compress:true, keepOriginal:false, quality:80, maxEdge:1920, thumbEdge:400 }`。
- `SettingsModal` 增「媒体 / 存储」区：压缩开关、保留原图开关、质量。**默认压缩、默认不留原图**。

### 依赖
- `backend/requirements.txt` 加 `Pillow`。前端无新增。

### 前端
- 列表/预览用 `thumbUrl`；正文/灯箱用 `url`；`<img loading="lazy">`；`AttachmentModal` 全图懒加载。
- `useApi`/`EventDetailPane` 附件流对接新响应字段。

### 文件映射
后端：`services/timeline.py`（`store_uploaded_image` 重写 + hash/缩略图/去重）、`models/entities.py`（`ImageAsset` 列）、`api/media.py`（透传）、静态服务/`main.py`（缓存头）、config 服务/`core/config.py`（media 默认）、`requirements.txt`。
前端：`EventDetailPane.vue`/`AttachmentModal.vue`（thumbUrl/lazy）、`SettingsModal.vue`（媒体设置）、`useApi.js`。

### 验收
- 上传 3MB 照片 → 工作版 WebP ≤ ~250KB + 400px 缩略图；列表用缩略图、详情用全图。
- 同图二次上传不新增磁盘文件（去重生效）。
- 媒体响应带 immutable 缓存头；二次访问命中缓存。
- 关「压缩」或开「保留原图」按设置生效。
- `pytest` 补：压缩产物、去重、保留原图、缓存头。

### 风险 / 迁移
- 迁移前备份 `data/`；旧 uuid 文件保留服务、**不批量重处理**（可选一次性脚本，默认不跑）。
- Pillow（Windows host）pip 直装；部署/CI host 确认。
- gif：默认不转（转 WebP 可能丢动画）；本期 gif 原样存。

---

## 5. P6-C 跨本来源标识 + 收藏视图

### 5.1 来源标识（可复用）
- 新增 `ui/src/components/timeline-notes/NotebookChip.vue`：笔记本图标 + 标题；色点 = `调色板[topicId % N]`（**确定性派生色，不加 schema 列**；未来可加 `Topic.color` 自定义，见 §10.2）。props：`{ topicId, topics }`。
- 复用：收藏行、搜索结果行（右侧 meta 列，对齐 Codex 参考图「来源」列）。
- 样式走令牌；进 `timeline-notes.css`。

### 5.2 收藏视图（修 `RIBBON_PANELS.star` bug）
- **现状（实测结论）**：`TopicSidebar.vue` 的 `RIBBON_PANELS.star` 配置同 `files`（`sections:["views","topics"], tree:true`）→ 点「收藏」Ribbon 看到的是笔记本树（与「笔记本」Tab 一样）。中栏/右栏星**已验证可正常 toggle**（计数 0→1→0、两端同步），故真正缺的是「跨本收藏列表」这个落点。
- **改**：点「收藏」Ribbon → 中栏进入「收藏（跨本）」模式：列出 `eventsIndex` 中 `favorite===true` 的全部事件（跨本），每行带 `NotebookChip` 来源；点行 = 切到该本 + 打开详情。左栏「收藏」面板给计数/入口。
- 复用现有中栏行渲染，仅跨本模式追加来源列（`--rowgrid` 增列或行内 chip）。
- 顺带：中栏/右栏 star 的 `on` 态对比度增强（点击反馈更明确）。
- **IA（已定）二者并存、语义分明**：`视图>收藏` quick-filter 保留 = **当前笔记本内**收藏（与 今天/本周/回收站 同属「本内透镜」，移除会破坏该组对称）；Ribbon「收藏」= **跨笔记本**收藏合集（"我 star 的全部"，每行带 `NotebookChip` 来源）。二者答不同问题（本内 vs 全局），不冗余；Ribbon 视图需明确"跨笔记本收藏"标题/空态以免混淆。

### 文件映射
前端：新增 `NotebookChip.vue`、`TopicSidebar.vue`（star 面板/Ribbon 行为）、`TimelineFeed.vue`（跨本模式 + 来源列）、`TimelinePage.vue`（收藏数据来源 = store 跨本过滤）、`timeline-notes.css`。

### 验收
- 收藏视图列出**所有本**的收藏，每行清晰显示来源笔记本；点击正确跳转并打开详情。
- 收藏/取消即时反映（store patch）；star `on` 态明显。

---

## 6. P6-D 搜索命令面板（UI 壳 + FTS5 管线；功能另设计）

### 6.1 UI（参考 Codex 命令面板，仅 UI）
- 触发：`Ctrl/Cmd+K` 全局 + 现搜索图标。覆盖层复用 `BaseModal`；顶部无边框输入；下方分组结果：
  - **事件**：标题 + 片段（左），`NotebookChip` + 日期（右）。
  - **笔记本**：匹配 topics。
  - **操作 / 命令**：新建事件 / 新建笔记本 / 设置 / 导出（带快捷键，仿参考图右侧列）。
- 键盘：↑↓ 选择、Enter 打开、Esc 关、命令区快捷键。
- 样式遵 spec §2.1 弹层家族 + 令牌；右侧 meta/快捷键列。

### 6.2 后端 FTS5 管线
- SQLite **FTS5** 虚表覆盖事件 `headline + body_markdown + era + extra 文本`；随写同步（触发器或写后重建该行）。
- 新 `GET /api/search?q=&limit=` → `[{ id, topicId, headline, snippet, dateKey, isoDate, rank }]`。
- **功能细节**（字段权重、范围、模糊、属性过滤、排序）→ **另立《搜索功能设计》**，本文不定；UI 壳先用「标题/正文基础匹配」打通。

### 文件映射
前端：新增 `components/timeline-notes/CommandPalette.vue`、`TimelinePage.vue`（挂载 + 快捷键）、`useApi.js`（search）、`timeline-notes.css`。
后端：迁移（FTS5 虚表 + 同步触发器）、`services/timeline.py`（search 查询）、新 `api/search.py` 或并入 `api/topics.py`。

### 验收（UI 壳）
- `Ctrl+K` 唤起、键盘可达、结果带来源、Enter 跳转；基础匹配先通，排序细化留待功能设计。

---

## 7. P6-E 关联事件 modal 卡片

- **现状**：点关联事件 → `open-related` → `selectEvent` **顶替**当前详情。
- **改**：点关联事件 → 弹 modal 卡片（复用 `BaseModal`），懒拉该事件详情（`detailCache`/`getEvent`），展示日期/标题/正文预览 + 「完整打开」（再走 `selectEvent`）。
- 文件：`EventDetailPane.vue`（关联点击改弹层）、新增/复用卡片组件、`timeline-notes.css`。
- 验收：点关联事件不顶替当前详情，弹卡预览；「完整打开」才切换；ESC/外点关闭。
- **注意**：依赖 P6-A 懒详情；与外观修复同改 `EventDetailPane.vue`，**需串行不并行**（文件所有权）。

---

## 8. P6-F CM6 编辑器（路线，另立文档）

- 用 **CodeMirror 6**（AGENTS §9 唯一预批依赖）实现 Typora 式实时渲染（Obsidian Live Preview 同源思路）。
- 分期：① 行内 marks（粗/斜/码/链接）+ 标题/列表/引用 + **行内图片**；② 表格/代码高亮/脚注。
- 必守不变量：右栏阅读↔编辑**零位移**、无边框无工具栏、图片内联、**中文 IME 顺滑**（contenteditable 老大难，CM6 更优）。
- 包体 ~100–200KB gzip、运行时虚拟化，**性能不重**；重在装饰逻辑实现。
- 落地前另写 `docs/editor-cm6-design.md`；本文只占位排期（最后做）。

---

## 9. 已完成 / 进行中（主代理负责，非 Codex 范围）

外观验收修复 ①②④⑤（分支 `feat/acceptance-fixes`）：
- **①** 右栏阅读↔编辑零位移：属性区两态同渲染（空显「—」）、标题盒对齐、meta 行 `.meta` 重置原生 `<button>` chrome（消除 era「党史·近代中国 ⌄」的 6px 横移 + 1px padding 引起的 2px 纵移）。实测阅读/编辑 title/meta/body/属性头逐项像素一致。
- **②** 中栏时间线末段竖线延伸 ~50px + 渐隐（`linear-gradient(--rail→transparent)`）。
- **④** 属性名↔值间距：属性列表改**列表级共享内容宽列**（`display:contents`，短标签贴近、长标签对齐截断）。
- **⑤** 「笔记本」分组头 `+` 改 hover 显示（保留底部「+ 新增」常驻入口）。
- **⑥** 右栏 era 去掉误导的 `⌄`：read/edit 均移除 chevron，read era 改 `.meta-group`（hover 背景 + `title="所属分组"` 作为分组提示），与 `.meta-trigger` 同 padding/负边距 → era 文本 read/edit 同处 x=1529，零位移。
- **⑦** 属性「—」对齐：空值 `<strong>—</strong>` 与选项 chip 同 11px 内容内缩 + 30px 居中盒——「—」字形 x=1430=chip 圆点 x；属性行统一 30px，实测 read/edit 属性头/正文/标签逐项一致。

已过 `agent:check / build / test:ui`；视觉 QA 与提交由主代理收口（与本文 Codex 阶段分属不同批次）。

---

## 10. 开放问题（需用户/后续确认）

1. ~~**收藏 IA**~~（已定，见 §5.2）：**二者并存、语义分明**——`视图>收藏` quick-filter = 当前笔记本内收藏（与 今天/本周/回收站 同为「本内透镜」）；Ribbon「收藏」= 跨笔记本收藏合集（带 `NotebookChip` 来源）。
2. **来源色**：先用 `topicId % 调色板` 派生色（零 schema）；将来是否加 `Topic.color` 自定义？
3. **搜索功能**：字段权重/范围/模糊/属性过滤 → 另立《搜索功能设计》。
4. **媒体**：gif 是否需转（保动画→不转）；「保留原图默认关」确认。
5. **index 体量上限**：超大数据时是否退化为「当前本 + 后台预取」。

---

## 11. 提交前自检（叠加 AGENTS §8 / spec §14.2）

- [ ] 每阶段独立验收 + 截图归档（视觉阶段，`docs/visual-qa/`）。
- [ ] 数据契约前后端 + 测试同步；新端点（`/api/index`、`/api/events/{id}`、`/api/search`）有 pytest。
- [ ] 既有不变量零回归：右栏零位移、自适应无 scale、全局禁滚动条、行高固定、令牌/图标纪律。
- [ ] 媒体迁移前备份 `data/`；去重/缓存头/设置生效有测试。
- [ ] 新依赖仅 Pillow(后端) / CM6(前端编辑器阶段)；不动其它依赖、不动 `package-lock.json`（除非确有依赖变更）。
- [ ] 不顺手重构无关代码；文件所有权清晰（关联 modal 与外观修复串行改 `EventDetailPane.vue`）。
- [ ] 阶段顺序：P6-A 先行；C/D/E 依赖 A。
