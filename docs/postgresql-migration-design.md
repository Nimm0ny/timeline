# 性能与规模化设计：SQLite 优先，PostgreSQL 有条件延后

原始日期：2026-07-06
修订日期：2026-07-06（经设计评审重写，并折入 IVM 调研；见 §12 追溯、§13 参考）

> 文件名沿用 `postgresql-migration-design.md` 以保持连续性，但**本设计的主线不再是数据库迁移**。评审结论是：用户诉求（左栏计数慢 + 支撑百万级）与 PostgreSQL 迁移基本正交，应先在现有 SQLite 上交付性能改造（Track A），PostgreSQL 迁移（Track B）降级为**有条件、可延后**的独立轨道。

---

## 0. Revision Summary（为什么重写）

评审对上一版做了 22 条已验证发现（含 3 条 blocker）。核心纠偏：

1. **诊断错位。** 用户第一诉求是「左栏 notebook 计数加载慢」。真正成因是 `list_topics()` / `list_bookshelves()` 每次调用都对整张 `timeline_events` 表做 `OUTER JOIN + GROUP BY` 聚合。**这在 PostgreSQL 上同样是 O(全表行数)，迁库不会让它变快。** 修复它的手段（预计算计数 read model）是纯应用逻辑，可直接在现有 SQLite 上落地。
2. **排期倒置。** 上一版把这个 DB-agnostic 的修复（read model）放在 Phase 4，压在整套 PG 迁移（Phase 3）之后——把「低风险、直接解决用户问题」的改动，锁在「最高风险」的存储切换之后。
3. **迁移本身有真实数据风险**（时间戳静默偏移、JSONB 反序列化全线崩、启动期 SQLite-only 代码未真正对 PG 关闭等），若照上一版排期会带着这些隐患切生产。

因此本版拆成两条轨道：

- **Track A — SQLite 优先性能改造（现在做）**：直接解决用户诉求，DB-agnostic，零运维负担，每步可回滚。
- **Track B — PostgreSQL 迁移（有条件、延后）**：仅当触发条件满足时才启动；即便启动，也必须先修好本版列出的迁移安全问题。

**给实现方（codex）的读法**：Track A 是当前工单，按 §6 的任务表逐项实现并验收。Track B 现在**不实现**，仅作为将来触发时的安全规范存档；除非本文件另行说明「进入 Track B」。

---

## 1. Goal（修订）

- **P0（Track A）**：左栏（书架 / 笔记本）计数在 1k 与 100 万事件下都能快速返回，不做读时全表聚合。
- **P0（Track A）**：单个笔记本打开不再一次性拉取全量事件与完整详情 DTO；默认分页，浏览器内存不随库规模线性增长。
- **P1（Track A）**：收藏 / 属性 / 书架 era 分组 / 搜索走窄接口或 read model，不依赖 `/api/index` 全量载入。
- **P2（Track B，有条件）**：当且仅当出现 §5 的触发条件时，安全迁移到 PostgreSQL。

**非目标**（沿用并强化）：

- 不引入多用户 / 权限 / 租户 / 协作。
- 不把附件迁进数据库。
- 不重写 FastAPI / Vue / 业务服务层。
- **不把 PostgreSQL 当作性能手段**——性能来自 read model / DTO 拆分 / 索引，与存储引擎无关。
- 不为「支撑百万级」这一条就启动 Track B（规模不是 PG 的充分理由，见 §5）。

---

## 2. Current State（已按代码校正）

上一版的「Current State」有多处已过时或不准确。以下为经代码核对的事实（含 file:line）。

### 2.1 已经做到的（不要当成待办）

- **首屏已不走 `/api/index`。** `loadWorkspace()` 首帧并行 `getConfig` + `listBookshelves` + `loadTopics`，随后按需加载当前笔记本事件。搜索走 `GET /api/search`（FTS5）。
  证据：`ui/src/pages/TimelinePage.vue:891-925`；`ui/src/composables/useApi.js`。
- **游标分页机制已存在。** `query_topic_events()` 已实现 `(date_key, id)` keyset、`limit+1` 判 `hasMore`、返回 `hasMore` + `nextCursor="date_key:id"`（NULL 用 `"null:id"`）。
  证据：`backend/app/services/timeline.py:1353-1413`；`backend/app/api/topics.py:78-94`。
  **缺口**：接口 `limit` 是 Optional 且**无默认值**（`limit=None` 返回整表），无 100/500 上限；前端 `getTimelineEvents(id)` 不传 `limit`（`useApi.js`、`useTimelineStore.js:237`）——所以「机制在、但没启用分页」。
- **核心索引已存在**（模型 `__table_args__` + `legacy_migration` 双声明）：`ix_timeline_events_topic_date_id (topic_id,date_key,id)`、`ix_timeline_events_topic_year_month`、`ix_timeline_events_topic_deleted (topic_id,deleted_at)`、`topics.bookshelf_id`、`event_items.event_id`。
  证据：`backend/app/models/entities.py:76-80,83,123`。
  **上一版把这些当「新建索引」是错的**——它们是沿用；真正需新增的只有 A1 用于 min/max 派生的 live 分区索引（见 §6·A1）。
- **搜索走 SQLite FTS5**（`timeline_events_fts`，`unicode61`）。写路径已在 `create/update/delete_event` 通过 `upsert_search_index_row` / `remove_search_index_row` 维护，`create_event:1699`、`update_event:1714/1731`、`delete_event:1743/1747`。

### 2.2 真正的性能成因（这才是要改的）

1. **左栏计数 = 读时全表聚合。** `list_topics()`（`timeline.py:1140-1173`）与 `list_bookshelves()`（`timeline.py:1176-1196`）在每次调用时对整张 `timeline_events` 做 `OUTER JOIN + GROUP BY`（`count / min / max date_key / count image`）。这是**首屏就发生**的读时全表聚合，与详情 DTO 无关；PostgreSQL 不会让它变快。**这就是用户抱怨的接口。**
   - 附带 bug：`list_topics` 的 `eventCount = COUNT(所有事件，含软删)`（无 `deleted_at IS NULL` 过滤），左栏计数当前把回收站里的事件也算进去了。**已定：read model 化时改为只计 live，顺手修正**（见 §6·A1）。
2. **单笔记本打开 = 全量 + 重 DTO。** `getTimelineEvents(id)` 不传 `limit` → `query_topic_events(limit=None)` 不加 `LIMIT` → `serialize_event_rows` → `event_to_dict` 逐行做 **5 次 `json.loads` + markdown 生成 + 关联事件二次查询**（`build_related_lookup`）。**这部分 Python 序列化成本随事件数线性增长，且 PostgreSQL 完全不触及。**
   证据：`timeline.py:693-732,1083-1085,1330-1333,1387,1403`。
3. **FTS5 对中文只能整段前缀匹配。** `unicode61` 把一段 CJK 连写切成单个 token，`中华*` 命中、但中段子串 `人民` / `共和` 返回 0。这是既有限制（不是本设计引入的），Track B 的 `pg_trgm` 方案**并不更好**（见 §8.6）。

---

## 3. Architecture Decision（修订）

**保持** FastAPI + SQLAlchemy + SQLite 为默认与生产存储。性能改造（Track A）全部在此之上完成。

**不采用（现在）**：PostgreSQL 迁移、Alembic、DuckDB、独立搜索集群。

**理由**：本应用是**单用户、本地优先**（auth 已移除，见 `git`/模型）。单写者场景下 PG 的四条卖点——并发写、JSONB、物化统计、在线备份——对本应用要么不适用、要么 SQLite 可等价满足：

- 并发写：单写者，无并发写。read model 增量维护在**单引擎 + 每请求会话 + 三个集中写入口**下，比在 PG 双写切换窗口里做更简单、更安全。
- JSONB：本设计不需要按 JSON 内部字段做高频过滤；即便要，代价是「JSONB 让全部 `deserialize_json_*` 假设崩掉」（见 §8.5），不是免费午餐。
- 物化统计：`topic_stats` 是普通派生聚合，SQLite 一张表即可。
- 在线备份：单用户可用 SQLite WAL + `VACUUM INTO` / 文件快照 / litestream。

规模（百万级）**不是** PG 的充分理由：全表聚合在 PG 上同样 O(N)，而物化 `topic_stats` 读取是 O(#topics)，与事件数无关——在**任一引擎**上都靠 read model 解决。

---

## 4. Prerequisite — 分页 NULL-date 正确性（Track A 的 A0）

上一版把「现有游标 = 正确、照搬到 PG」当作前提。实际有一处**确证 bug**与一处**需验证**：

- **确证 bug（要修）**：裸日期游标分支 `query_topic_events` 中 `cursor_id is None and cursor_key is not None` → `filter(date_key > cursor_key)`（`timeline.py:1372-1373`）。SQLite 中 `NULL > n` 为未知→假，会**静默丢弃所有未定日期（`date_key IS NULL`）事件**；按排序它们应排在有日期行之后、仍需返回。
- **需验证（别盲改）**：主 keyset 分支（`timeline.py:1378-1384`）对「有日期段 → 未定日期段」的跨段推进，经手工推演在正向翻页下不重复不丢失；**不要在没有失败用例的情况下改它**。

**动作**：修裸日期分支使其包含 `date_key IS NULL`；补分页测试——对「含未定日期事件」的 topic 逐页翻到底，断言并集 == 全量、无重复。此项 DB-agnostic，是 A2 默认分页上线前的前置。

---

## 5. 两条轨道（Track A / Track B）与 PG 触发条件

### Track A — SQLite 优先性能改造（现在做）
覆盖 §1 的 P0/P1，全部 DB-agnostic。详见 §6 任务表与 §7 验收。

### Track B — PostgreSQL 迁移（有条件、延后）
**触发条件（满足任一才启动，否则保持 Track A）**：

1. 应用变为多写者 / 多用户（会推翻「单用户」非目标）。
2. 需要远端服务、多网络客户端并发访问同一库。
3. 出现 per-topic/era read model 无法预计算的**跨笔记本即席分析查询**（此时 PG JSONB + 表达式索引才真正有优势）。
4. 需要 WAL-mode SQLite 满足不了的**在线并发备份 / PITR**。

**并且**：启动 Track B 前，必须先在 Track A 已落地的前提下，用 100k / 1M 合成数据基准**证明 SQLite 确实到顶**（大概率不会）。若基准通过，迁移可能永远不需要。

Track B 的详细安全规范见 §8（现在不实现，作为将来触发时的规范）。

---

## 6. Track A 任务表（codex 工单）

图例：**A0–A4 = 现在做**；每项标注是否 DB-agnostic（本轨全部是）与验收。所有写路径共用同一 `db` 会话，read model / 派生列的更新**必须与事件变更在同一事务内**（在 `db.commit()` 之前）。

| ID | 任务 | 关键文件 / seam | 验收 |
|----|------|----------------|------|
| A0 | 修分页 NULL-date bug + 测试 | `timeline.py:1372-1384` | §4 |
| A1 | `topic_stats` read model 替换左栏全表聚合 | 新表 + `list_topics`/`list_bookshelves` 改读；写 seam 见下 | §7·A1 |
| A2 | list/detail DTO 拆分 + 默认分页 + 前端启用 | `timeline.py` 新增轻量行→dict；`topics.py:78-94`；`useApi.js`/`useTimelineStore.js` | §7·A2 |
| A3 | 写时派生列 `preview_text` / `search_text` | 模型 + 集中派生函数 + 三写入口 + 回填命令 | §7·A3 |
| A4 | 窄接口去 `/api/index` 依赖（收藏 / 属性 / era 分组） | 新增 `topic_era_stats` + 端点 | §7·A4 |

### A1 — `topic_stats`（直接解决左栏卡顿）

**设计依据（IVM）**：这是教科书级增量视图维护。用 counting algorithm（Gupta-Mumick, SIGMOD 1993）——每组存计数、写时 ±1、计数归零删该组行；pg_ivm 的 `__ivm_count__` 正是此法。关键洞察是 **count 与 min/max 的不对称**：

- `COUNT` **没有引擎捷径**——即便走覆盖索引也是线性扫每条索引项，永远非 O(1)（SQLite `optoverview` + 官方论坛实证）。→ **必须物化进汇总表**。
- `MIN/MAX` 在 `(topic_id, date_key)` 索引上是**边界 seek，O(log N)**（SQLite `optoverview` 的 MIN/MAX 优化）。→ **读时现算即可，不存、不维护**。

所以只物化计数、min/max 读时从索引取——这样把 IVM 里唯一的难点「删掉当前极值需重算底层」**整体删除**（你根本没存它）。出处见 §13。

新表（SQLite，随 `Base.metadata.create_all` 建；不需要 PG）——**只有计数**：

```sql
CREATE TABLE topic_stats (
  topic_id            INTEGER PRIMARY KEY REFERENCES topics(id) ON DELETE CASCADE,
  live_event_count    INTEGER NOT NULL DEFAULT 0,
  deleted_event_count INTEGER NOT NULL DEFAULT 0,
  favorite_count      INTEGER NOT NULL DEFAULT 0,   -- 仅 live 收藏
  image_count         INTEGER NOT NULL DEFAULT 0,   -- 仅 live；has_image = image_count > 0
  updated_at          DATETIME NOT NULL
);
```

min/max 读时派生需要一条 **live 分区索引**（`timeline_events` 上唯一需新增的索引；核心复合索引已存在，见 §2.1），使其保持边界 seek 而非扫描：

```sql
CREATE INDEX ix_timeline_events_live_topic_date
  ON timeline_events (topic_id, date_key) WHERE deleted_at IS NULL;
```

**维护 = 一个符号权重函数**（借 DBSP 的 signed-weight：create/update/delete 收敛成一条路径，删除即负权重）：

```python
def apply_topic_stats_delta(db, topic_id, *, live=0, deleted=0, favorite=0, image=0):
    # 每列 += delta；行不存在先建零行（Noria「upquery-on-miss」式自愈）
    ...
```

写 seam（与现有 search-index 钩子同位；同一事务、`commit` 前）——**全部 O(1) 增量，无一处扫全表**：

| 事件动作 | 位置 | delta |
|----------|------|-------|
| create | `timeline.py:1699` 后 | `live+1`；有收藏 `favorite+1`；有图 `image+1` |
| update（state·收藏开/关） | `timeline.py:1710-1714` | `favorite ±1` |
| update（state·软删） | `timeline.py:1743` | `live-1, deleted+1`；曾收藏 `favorite-1`；有图 `image-1` |
| update（state·恢复） | `timeline.py:1710-1714` | `live+1, deleted-1`；回补 favorite/image |
| update（完整编辑） | `timeline.py:1731` | 仅 image/favorite 变化的差值（live/deleted 不变，已删事件不可编辑） |
| delete（永久） | `timeline.py:1747` | 按当时 live/deleted 归属 `-1`，连带 favorite/image |
| create_topic / delete_topic | `create_topic` / `delete_topic:1270` | 建零行 / 删行 |

- **读**：`list_topics` JOIN `topic_stats` 取计数；min/max 用**每 topic 的相关子查询** `MIN(date_key)/MAX(date_key) WHERE topic_id=? AND deleted_at IS NULL`（命中上面的 live 分区索引 = 边界 seek）。几百个 topic 也就几百次 O(log N) seek，亚毫秒且与事件总数无关。**用 `EXPLAIN QUERY PLAN` 确认走 `SEARCH ... USING INDEX` 而非 SCAN**；回填后跑一次 `ANALYZE`（新库无统计信息可能误判计划，造成「索引没生效」的假象）。
- `list_bookshelves`：书架级计数 = 该书架下各 `topic_stats` 之和（`GROUP BY` over 小表 `topic_stats`，**不碰 `timeline_events`**）。
- **rebuild = counter_cache 式修复**（借 Rails `reset_counters`）：`rebuild_topic_stats(db)` 跑一次真值 `GROUP BY` 覆盖全表——既是导入/迁移后的回填，也是「计数看着不对」时的一键修复。启动自愈：`topic_stats` 行数 != topics 行数时重建。任何**绕过三写入口**的写库（那个裸 `sqlite3` docx 导入器）都必须在结尾调 `rebuild`，否则静默失同步（counter_cache 的经典坑）。
- **已定：左栏只计 live。** `eventCount` 显示 `live_event_count`、min/max 按 live 派生（这也顺手修正 §2.2 那个「含软删」miscount——软删事件不该再进侧栏计数）。上面的 live 分区索引 + `deleted_at IS NULL` 子查询即为此服务。回收站数量另由 `deleted_event_count` 单独提供（回收站视图用），不混入 live 计数。

### A2 — list / detail DTO 拆分 + 默认分页

- 列表接口 `GET /api/topics/{id}/events` 返回**轻量 DTO**，**不经** `event_to_dict` / `serialize_event_rows`（避免每行 5×`json.loads` + markdown + 关联查询）。新增一个专用轻量 `row → dict`，`preview` 直接读 A3 的 `preview_text` 列。
- 轻量 DTO 字段（在上一版基础上**补 `searchText`**，见下）：`id, topicId, dateKey, isoDate, dateParts, displayLabel, headline, era, noteType, image, imageUrl, thumbUrl, extra, favorite, favoriteAt, deletedAt, createdAt, updatedAt, preview, searchText, attachmentCount`。
- **务必补 `searchText`**：前端 `detailSearchText` / `detailToIndexEvent` / `buildEventPreview` 的兜底当前**直接读 `bodyMarkdown` / `bodyJson`**。若列表 DTO 删掉 body 字段而不提供 `searchText`（服务端由 `search_text` 列产出），新编辑事件的客户端搜索文本 / 预览会静默变空。上线前审计所有 `bodyJson`/`bodyMarkdown` 的前端消费点。
- 分页策略：接口 `limit` 默认 `100`、上限 `500`；返回既有的 `hasMore` / `nextCursor`。前端 `getTimelineEvents(id)` 起始传 `limit=100`，滚动加载后续页。
- 详情 `GET /api/events/{id}` 保持完整 DTO（`bodyMarkdown/bodyJson/attachments/relatedEvents/items`）。

### A3 — 写时派生列 `preview_text` / `search_text`（DB-agnostic）

- 模型新增两列：`preview_text TEXT NOT NULL DEFAULT ''`、`search_text TEXT NOT NULL DEFAULT ''`（SQLite 用启动期幂等 `ALTER TABLE`，与现有 `ensure_timeline_event_schema` 同套路）。
- **集中派生**：抽一个 `derive_event_text(note_type, body_markdown, body_json, items, extra, topic) -> (preview_text, search_text)`，复用现有 `markdown_preview_text` / `collect_mindmap_text` / `extra_search_text` 逻辑。**所有写入口都调它**，挂在与 `upsert_search_index_row` 同一 seam（`create_event:1699`、`update_event:1714/1731`）。派生随 `note_type` 而变（mindmap vs markdown），别只处理 markdown 一种。
- **覆盖旁路写入口**：至少三条不走 `create/update_event` 的路径必须同步派生列，否则预览 / 搜索静默漂移：
  1. `tools/import_outline_docx.py`（当前用裸 `sqlite3` 写库）——改为走服务层，或写后调派生 + `rebuild_topic_stats`。
  2. 批量导入 / 迁移加载器（若走 Track B）。
  3. state-only 的 favorite / restore 分支（body 不变时无需重算，但删除/恢复影响 search 收录）。
- 提供 `POST /api/admin/read-models/rebuild`（本地管理用）回填 `preview_text` / `search_text` / `topic_stats` / `topic_era_stats`，并在 §7 校验里抽样断言 `preview_text == recompute(row)`。

### A4 — 窄接口，去 `/api/index` 依赖

- **`topic_era_stats`（首批交付，已定纳入）**：`(topic_id, era, live_event_count)` —— **只需计数**（侧栏 era 叶子仅显示 `count`，见 `TopicSidebar.vue:1483`，不需要 min/max）。用与 A1 相同的 signed-weight 维护，多两条规则：编辑改了 `era` 时 `旧era-1 / 新era+1`；**某 era 计数归零就删掉该行**（counting-algorithm 的 Cnt=0 规则，让空 era 叶子自动消失）。左栏 era 子列表当前由前端从全局 `eventsIndex` 推导（`buildBookshelfTree`，`timelineNotes.js:1289`），只有懒加载 `/api/index` 后才出现；改为 `GET /api/topics/{id}/era-stats` 读该表即可去掉全量依赖。前端局部刷新可借 Obsidian `file-explorer-note-count` 的「失效集 = 变动节点 + 祖先链 + debounce」，但**别学它重新遍历子节点**——用累加计数器。
- 收藏 / 属性面板：改窄接口（`GET /api/favorites`、`GET /api/topics/{id}/property-usage`），不再经 `ensureGlobalIndexReady -> getIndex` 拉全量 index。`property_usage` 若要 read model 化，**注意基数**：`normalize_extra` 把 text/number/date/url 等自由文本列原样 `str()`，`(topic_id, column_key, value)` 对自由文本列近似 per-event 基数（百万级≈百万行/列）。**只对 select/multiselect/checkbox（值域有界）建 usage 聚合**；自由文本列不做全值聚合。
- 收尾后 `/api/index` 仅保留开发调试用途或删除。

---

## 7. Track A 验收

- **A0**：含未定日期事件的 topic，逐页翻到底，事件并集 == 全量且无重复（新增测试）。
- **A1**：`GET /api/topics` / `/api/bookshelves` 的 `EXPLAIN QUERY PLAN` **不出现对 `timeline_events` 的全表 SCAN / GROUP BY**，min/max 子查询走 `SEARCH ... USING INDEX`（边界 seek）。**写路径 O(delta) 验收**（借 Turso/DBSP 判据）：任一 create/update/delete 触及的 `timeline_events` 行数为 O(1)、与事件总数无关，写时不扫全表。左栏计数在 100k / 1M fixture 下 p95 与 topic 数相关、与事件总数无关；read model 与真值一致（`rebuild` 后逐 topic 比对 count/favorite）。
- **A2**：首屏只请求 config + bookshelves + topics + 当前 topic 第一页（≤100）；浏览器内存不随全库事件数线性增长；10 万事件 fixture 首屏不载入全量 payload。列表接口不调用 `event_to_dict`。
- **A3**：列表 DTO 的 `preview` 来自列读取，不在请求内跑 markdown 生成；抽样 `preview_text/search_text == recompute`；docx 导入后派生列与 read model 一致。
- **A4**：属性面板 / 收藏 / era 子列表不再触发 `/api/index`；`property_usage` 只聚合有界值域列。
- **全局**：每步单独可回滚；现有 pytest 通过；新增百万级基准记录 p50/p95 + payload bytes + SQL plan。

---

## 8. Track B — PostgreSQL 迁移（有条件；现在不实现，触发时按此规范）

> 仅当 §5 触发条件满足、且基准证明 SQLite 到顶后启动。以下把上一版被评审指出的迁移隐患**全部收编为硬性规范**。

### 8.1 Schema ownership 与启动期 gating（Track B 第一步，先落）
- PG schema 只由 Alembic 管理；应用启动**不得**对 PG 执行 `Base.metadata.create_all` / SQLite `ALTER TABLE` / PRAGMA / 表重建 / FTS 重建。
- **真正 gate 掉 SQLite-only 路径**（上一版只写了目标、没给机制）：`app_lifespan` 当 `DATABASE_BACKEND != sqlite` 时只跑「Alembic head 校验」，跳过 `init_database` / `ensure_*_schema` / `rebuild_table_from_model` / `rebuild_search_index`。并在 `rebuild_table_from_model` 内 `assert engine.dialect.name == "sqlite"`——它现在用**硬编码 `sqlite3.connect(DB_FILE)` 按路径打开文件**，与 `DATABASE_URL` 无关，必须防止对 PG 部署时误改本地 stale 文件。
- 启动时若 PG 当前 revision != Alembic head：**fail fast**，不静默补 schema。
- 测试：用 `postgres://` URL 启动，断言零条 SQLite DDL/PRAGMA 发出。

### 8.2 Alembic 基线 ≠ 现网 SQLite 文件（真实 schema drift）
- 现网库是被历次 `ALTER TABLE` 塑形的，其**物理列序与可空性**与 ORM 不一致（如 `note_type` / `body_json` / `favorite_at` 在实体末尾追加，且 `note_type` 现网可空、ORM 为 NOT NULL）。
- 规范：迁移加载器**必须按列名映射，禁止 `SELECT *` / 位置拷贝**；Alembic 基线以 ORM 为目标真值；加载后校验**逐表比对列名/类型**（不止行数），任一不符即失败。可选：迁移前先 `rebuild_table_from_model` 把源库整形。

### 8.3 时间戳迁移会静默偏移（blocker）
- 现网 `created_at/updated_at` **混存** naive（`CURRENT_TIMESTAMP` 空格串）与 tz-aware（`utcnow` ISO 串）。目标 schema 声明 `timestamptz`，若逐字搬运，naive 串入 `timestamptz` 会被按服务器时区解读，**约 92% 行整体偏移**，而行数/计数/`date_key` 排序校验都发现不了。
- 规范：加载器对 `created_at/updated_at/favorite_at/deleted_at` 显式解析，naive 值补 UTC，使全部落为正确 `timestamptz`；**新增校验断言逐行 ISO 时间戳相等**。

### 8.4 数据加载器与校验
- 只迁移白名单业务表：`bookshelves, topics, images, timeline_events, event_items, app_config`；**排除 6 张 FTS5 影子表**（否则「所有表行数一致」会报幽灵表 / 通用加载器会呛虚表）。`event_search` 在 PG 侧从 `timeline_events` 重建，不迁。
- **序列重置空表守卫**：现网 `images` 为 0 行，`MAX(id)` 为 NULL → `setval(seq, COALESCE(MAX(id),0)+1, false)`，否则下一次上传拿到坏 id。迁移测试 fixture 必须覆盖空表分支。
- **JSON parse-fidelity 校验**：JSON 初期仍 TEXT，应用读时容忍坏 JSON（回退 `[]`/`{}`），所以坏行能骗过「抽样 DTO 一致」，却会在后续 JSONB 化（`::jsonb` 转换，见 §8.5）时硬失败——那时 SQLite 已判 stale。规范：加载校验阶段对每行 `columns_json/extra_json/attachments_json/related_event_ids_json/body_json` 跑 `json.loads()`，报告解析失败，**在切换前**修好。
- 其余校验：逐表行数、每 topic 的 count/min/max/favorite/deleted、随机抽样详情 DTO、外键无 orphan。

### 8.5 JSONB 硬化（blocker，顺序前置）
- **TEXT→JSONB 不是低风险的收尾**。三个共享反序列化器（`deserialize_json_list` / `deserialize_json_dict` / `deserialize_body_json`）**硬假设值是 JSON 字符串并 `json.loads`**。一旦列变 JSONB，psycopg 回传已解析对象，这些函数在读路径 `TypeError`（其中两个还不捕获 `TypeError`）——事件序列化 500、搜索 payload 构建失败、属性归一化崩。
- 规范：进入 JSONB **之前**，把三者重构为统一容忍式 `coerce`（`isinstance dict/list→原样；str/bytes→try json.loads；else→fallback`），异常统一为 `(JSONDecodeError, TypeError, ValueError)`；写侧同时决定序列化方式。加 dialect 测试：经 JSONB 列往返 `event_to_dict` / `build_search_payload` / `normalize_extra`，用测试而非散文锁定 `str|dict|list` 契约。

### 8.6 搜索：别用 pg_trgm 顶替 FTS5（中文场景）
- `pg_trgm` 索引 3-gram；中文 1–2 字查询产不出可用 trigram，退化为对 `search_text` 的顺序扫描——正是本设计要消灭的读时全表扫描，还在 1M 行上。且它并不比现有 FTS5 更好（两者都不解决 CJK 中段子串）。
- 规范：用为 CJK 设计的方案（`pgroonga` / `zhparser` / n-gram 全文配置），或把「中文搜索质量」作为进入搜索替换阶段前必须先解决的一等问题。加测试：2 字 CJK 查询返回预期行**且**命中索引（`EXPLAIN`）。

### 8.7 连接 / 驱动 / 池
- 保持**同步**引擎（路由是同步的，单写者别引入 asyncpg 的复杂度）；显式小池（`pool_size=5, pool_pre_ping=True`）；按后端剥离 `session.py` 里 SQLite-only 的 `connect_args={"check_same_thread": False}`。

### 8.8 部署 / 备份 / 切换 / 回滚（调和矛盾）
- 「把 `DATABASE_URL` 指回 SQLite」**不是**干净回滚：应用在 sqlite:// 上启动会跑 `ensure_timeline_event_schema` 的 `UPDATE/ALTER/CREATE INDEX`、可能重建表、`DELETE`+重灌 FTS 并 `commit`——**回滚动作本身会改写回滚目标文件**。
- 规范二选一并写明：要么回滚从**冻结前的 SQLite 备份**恢复、绝不拿迁移源文件启动应用；要么先证明启动期写入对该文件只读/幂等再信任它。切换窗口：写冻结 → 最终只读迁移 → 校验（含 §8.3/8.4）→ 切 `DATABASE_URL` → smoke → 开放写入；开放写入后 SQLite 视为 stale，只允许 PG restore / forward repair。
- 切换前必须先更新并演练 runbook，不得留到切换后。

---

## 9. Testing Strategy（修订）

- **核心 API 测试必须也跑在 PG 上**（若进入 Track B）。上一版让 `test_timeline_api.py` 永远只跑 SQLite in-memory，而本迁移真正的风险（JSONB 解析、NULLS LAST 排序、tz 时间戳、boolean、sequence）全是 SQLite 表达不出的方言差异——会假绿后逃逸到生产。做法：`conftest` 的 `db_session` fixture 按环境变量参数化双后端，完整既有套件在 CI 对 PG 跑。
- Track A 全部测试在 SQLite 上即可（DB-agnostic）：A0 分页、A1 read model 一致性、A2 分页 + DTO 字段、A3 派生列一致性。
- 百万级基准（Track A 交付即做，Track B 触发判据）：100k / 1M 合成数据，核心读接口记录 p50/p95 + payload bytes + SQL plan；重点是「不全量加载」「命中索引/read model」。

---

## 10. Implementation Order（PR 拆分，给 codex）

**Track A（现在做，每步独立可回滚）**：

1. `fix: paginate undated (NULL date_key) events correctly` + 测试（A0）
2. `perf: add topic_stats read model; drop full-table GROUP BY on /api/topics|/api/bookshelves`（A1）
3. `perf: add write-time preview_text/search_text derived columns + rebuild`（A3）
4. `perf: split event list/detail DTO, default pagination, FE opt-in`（A2；排在 A3 后，因轻 DTO 依赖 A3 的 `preview_text` 列）
5. `perf: narrow endpoints (era-stats/favorites/property-usage) off /api/index`（A4）
6. `chore: 100k/1M synthetic benchmark harness`（验收 + Track B 判据）

**Track B（不实现，触发后另开）**：Alembic skeleton + startup gating → 加载器（by-name/时间戳/FTS 排除/JSON 校验）→ deserializer 容忍化 → JSONB → CJK 搜索 → 连接池 → 部署/切换/回滚。

---

## 11. Open Questions

**已定（本轮敲定，已写入正文）**：

- 左栏计数改为**只计 live**，顺带修正 §2.2 的含软删 miscount（见 §6·A1）。
- **`topic_era_stats` 纳入首批交付**（见 §6·A4）。

**仍开放**：

- 百万级数据主要来自导入还是长期累积（影响 rebuild / 基准设计）。
- （仅 Track B 触发后）生产 PG 形态：本机 Docker / systemd / 托管；中文搜索是否需高于 FTS5。

---

## 12. 附录 — 评审结论追溯（22 findings）

本版对应处理：blocker①②（诊断/排期）→ §0/§3/§5/§6 两轨拆分与 A1 前置；blocker③（时间戳）→ §8.3；cursor NULL → §4；启动 gating → §8.1；Alembic drift → §8.2；加载器/序列/FTS/JSON 校验 → §8.4；JSONB deserializer → §8.5；派生列同步 → §6·A3；pg_trgm/CJK → §8.6；连接池 → §8.7；回滚矛盾 → §8.8；测试假绿 → §9；per-row DTO 成本 → §2.2/§6·A2；property_usage 基数 → §6·A4；list DTO 丢 body 破坏前端搜索 → §6·A2（补 `searchText`）；已存在索引/分页被当待办 → §2.1 校正。评审驳回 2 条（NULLS-LAST-in-DDL 重复项、「1M 事件歧义」过度解读），未纳入。

---

## 13. 参考（设计依据）

Track A 的 read-model 不是自创，而是增量视图维护（IVM）的标准做法；以下主源支撑 §6·A1 / A4 的各处选择：

- **Counting algorithm / 自维护聚合** — Gupta, Mumick & Subrahmanian, "Maintaining Views Incrementally," SIGMOD 1993 — <https://dl.acm.org/doi/10.1145/170036.170066>（每组计数、±1、Cnt=0 删组行）
- **MIN/MAX 为何是唯一难点** — DBSP, VLDB 2023 / Feldera — <https://arxiv.org/pdf/2203.16684>（COUNT/SUM 群可逆→删即减；MIN/MAX 无逆→唯一可能回读底层的字段）
- **生产参考实现** — pg_ivm（`__ivm_count__` 每组计数 + 只在删极值时重算）— <https://github.com/sraoss/pg_ivm>
- **SQLite MIN/MAX 边界 seek + 覆盖索引 + COUNT 非 O(1)** — SQLite Query Optimizer Overview — <https://sqlite.org/optoverview.html>
- **SQLite 汇总表/触发器物化视图**（本设计改在三写入口用应用代码维护，理由见 A1）— <https://www.hisqlboy.com/blog/simulating-materialized-views-sqlite>
- **counter_cache / reset_counters**（计数列 + 回填修复；绕过 hook 即失同步）— Rails — <https://api.rubyonrails.org/classes/ActiveRecord/CounterCache/ClassMethods.html>
- **同类 UI 实证**（树形侧栏计数：事件驱动 + 祖先链失效 + debounce；反面教材：勿重新遍历子节点）— Obsidian `file-explorer-note-count` — <https://github.com/ozntel/file-explorer-note-count>
- **验收判据「写路径 O(delta) 非 O(#events)」** — Turso live materialized views（仅借判据；其本体 not production-ready）— <https://turso.tech/blog/introducing-real-time-data-with-materialized-views-in-turso>
- **过度设计（已排除）**：Materialize / RisingWave / ksqlDB / Feldera 服务端 / Noria·ReadySet —— 面向 Kafka 级多写者集群，与单文件应用差数个数量级；仅借 Noria「upquery-on-miss」自愈思路。
