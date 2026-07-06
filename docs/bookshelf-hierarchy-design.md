# 书架层级设计 · 书架 > 笔记本 > 分组

> 本文定义「书架（bookshelf）」作为左栏中 **笔记本（Topic）的上级文件夹层** 的实现方案。
> 当前用户已明确拍板：
> - `书架` 图标使用 `LibraryBig`
> - `笔记本` 图标使用 `NotebookText`
> - `全部笔记` 视图图标改为 `BookOpenText`
> - 求是相关内容不合并成单一超大笔记本，而是归入同一书架 `求是` 下的多个笔记本
>
> 在本设计覆盖范围内，裁决顺序仍严格遵守仓库根规则：
> `用户当前明确要求 > AGENTS.md 工程流程/禁止项/硬约束 > 当前强制 spec/prototype > agent-frontend-hardness > 本文与其他 docs > 现有代码`
>
> 与 `docs/p6-experience-overhaul-design.md` 中“笔记本平铺、不做层级”的旧决策冲突时，以本文为准。

## 0. Define-First

- **Goal**
  - 在左栏引入 `书架 > 笔记本 > 分组(era)` 三层信息架构。
  - 保持现有 `Topic` 与 `TimelineEvent` 主体模型可持续演进，不把求是网所有文章压成一个难以浏览的超大笔记本。
  - 让远端已导入的 `求是网-*` / `求是杂志-*` 笔记本可以统一挂到书架 `求是` 下。

- **Non-goals**
  - 本轮不做多级书架嵌套。
  - 本轮不做笔记本之间拖拽排序。
  - 本轮不做“把求是网所有专题强行合并成一个笔记本”。
  - 本轮不改中栏主布局，不改右栏阅读/编辑结构。
  - 本轮不把时代(`era`)升级成数据库中的独立实体。

- **Scope**
  - 新增 `Bookshelf` 数据模型和 `Topic.bookshelf_id`。
  - 新增书架相关 API，并为现有 topic DTO 补充书架字段。
  - 左栏从 `topic -> era` 改为 `bookshelf -> topic -> era`。
  - 统一左栏/来源 chip/视图图标语义。
  - 为求是导入路径提供明确的书架归属规则。

- **Acceptance**
  - 左栏可展示至少一个书架及其下的多个笔记本。
  - `求是` 书架下能容纳 `求是网-*`、`求是杂志-*` 多个笔记本。
  - 现有 topic 数据不丢失；旧笔记本在迁移后仍能正常进入中栏和右栏。
  - “全部笔记”“书架”“笔记本”图标语义不冲突。

- **Verification**
  - 后端：topic 列表 / topic meta / 创建 / 更新归属 / 删除 的 pytest 覆盖。
  - 前端：左栏书架展开、笔记本切换、era 过滤、多选与 hover 操作不回归。
  - 视觉：`1920×1080` fixture 下验证三层树结构、缩进、图标、hover/active 态和行高不变。

## 1. 问题陈述

当前系统顶层只有 `Topic`，在用户心智中它既承担“笔记本”的角色，也被拿来表达更大的资料集合。对于求是导入场景，这会立刻带来两个问题：

1. 如果把求是网所有专题强行导入一个 `Topic`，中栏时间线会变成高密度混合列表，可读性显著下降。
2. 如果继续按 `求是网-理论 / 求是网-经济 / 求是杂志-2026年第13期` 拆为多个 `Topic`，左栏缺少一个能把这些相关笔记本组织在一起的更高层容器。

因此需要显式引入 `书架` 层。它的职责不是替代笔记本，而是承载“资料集合/来源体系”。

## 2. 信息架构

目标层级固定为三层：

1. **书架（Bookshelf）**
   - 作为左栏顶层容器。
   - 表示一组相关笔记本的上级文件夹。
   - 例：`求是`、`编年`

2. **笔记本（Topic）**
   - 继续作为事件的直接拥有者。
   - 中栏/右栏数据加载、创建事件、导入导出仍以 `Topic` 为边界。
   - 例：`求是网-理论`、`求是杂志-2026年第13期`

3. **分组（Era / Year / Month）**
   - 仍由事件上的 `era` 或现有 groupBy 机制承载。
   - 不升级为独立数据库对象。
   - 在求是杂志场景中，`era` 可继续作为 “2026年第13期” 这种组名。

结论：

- **书架不是事件容器，笔记本才是事件容器。**
- `Bookshelf` 只管“组织笔记本”，不直接拥有事件。

## 3. 图标语义方案

### 3.1 图标映射

统一在 `TimelineLucideIcon.vue` 中维护以下映射：

| 语义 | key | Lucide |
| --- | --- | --- |
| 品牌 | `book` | `BookOpen` |
| 书架 | `bookshelf` | `LibraryBig` |
| 笔记本 | `notebook` | `NotebookText` |
| 全部笔记 | `allNotes` | `BookOpenText` |

### 3.2 替换原则

- 左栏 ribbon 当前“笔记本”按钮不再用 `folder`，改为 `bookshelf`。
- 左栏树中的笔记本节点不再用 `folder`，统一改为 `notebook`。
- 中栏来源 chip 已经使用 `NotebookText`，保留不变。
- 现有 `library` 图标不再承担“全部笔记”视图含义，避免与“书架”语义冲突。

### 3.3 视觉目标

- 书架行一眼看出是“集合容器”。
- 笔记本行一眼看出是“可进入的资料册”。
- “全部笔记”仍然是一个视图，不被误解为容器节点。

## 4. 数据结构

### 4.1 新增实体：Bookshelf

新增表 `bookshelves`：

```ts
type Bookshelf = {
  id: number;
  name: string;
  title: string;
  createdAt: string;
  updatedAt: string;
};
```

字段建议：

- `id`: 主键
- `name`: 唯一、稳定键，供 API 和迁移使用
- `title`: 展示名
- `created_at`
- `updated_at`

本轮不加：

- `color`
- `icon`
- `sort_order`
- `parent_id`

### 4.2 Topic 增量字段

`Topic` 新增：

```ts
bookshelf_id: number | null
```

关系：

- `Bookshelf 1 -> N Topic`
- `Topic 1 -> N TimelineEvent`

设计选择：

- 允许 `null` 只是为了迁移过程更安全。
- 迁移完成后，业务上必须保证每个 topic 都有 bookshelf。
- `null` 仅允许作为数据库迁移窗口内的**内部临时状态**存在，不允许成为公开业务状态。

### 4.3 不改 Event 归属

`TimelineEvent` 仍然只归属于 `Topic`，不增加 `bookshelf_id` 冗余列。

原因：

- 避免双重归属带来的写时一致性问题。
- 事件跨书架移动时只需要移动 topic 归属，而不是批量改 event。

## 5. 后端 API 方案

### 5.1 现有 topic DTO 增量

`GET /api/topics`、`GET /api/topics/{id}`、`GET /api/topics/{id}/meta` 在现有字段上新增：

```ts
{
  bookshelfId: number | null;
  bookshelfName: string | null;
  bookshelfTitle: string | null;
}
```

这样前端即使暂时不调用独立 `bookshelves` 接口，也能先完成左栏分组渲染。

### 5.2 新增书架接口

建议新增：

- `GET /api/bookshelves`
- `POST /api/bookshelves`
- `PUT /api/bookshelves/{id}`
- `DELETE /api/bookshelves/{id}`（**仅空书架允许删除**，见下）

最小 DTO：

```ts
type BookshelfListItem = {
  id: number;
  name: string;
  title: string;
  topicCount: number;
  eventCount: number;
};
```

删除契约必须明确为：

- 若书架下仍有任何 topic，`DELETE /api/bookshelves/{id}` 返回 `409`。
- 本轮**不做**“删除书架时自动级联删除 topic”。
- 本轮**不做**“删除书架时自动迁移到其他书架”。

原因：

- 当前 `Topic` 删除会级联其全部事件，若书架删除语义不钉死，后续实现者容易误用同类 destructive 路径。
- 现阶段书架删除不是高频操作，宁可强制先清空/迁走，也不要冒 orphan topic 或级联删事件的风险。

### 5.3 Topic 归属更新

建议沿用现有 meta 更新入口：

- `PUT /api/topics/{id}/meta`

新增字段：

```ts
{
  bookshelfId?: number;
}
```

原因：

- 改动面最小。
- 避免再造一个只为移动归属存在的单独路由。

约束：

- 当 `bookshelfId` 出现在公开写接口里时，必须是一个存在的 bookshelf id。
- `bookshelfId = null` 对公开 API 返回 `400`，不允许用它把 topic 变成“未归属笔记本”。
- 如果未来要支持“移回默认书架”，应显式传默认书架 id，而不是传 `null`。

## 6. 迁移与初始化策略

### 6.1 默认书架

迁移时自动创建默认书架：

- `name = default`
- `title = 编年`

所有旧 topic 默认挂到 `编年`。

### 6.2 求是专项归档

远端或本地若已有这些笔记本：

- `求是网-*`
- `求是杂志-*`

迁移或导入后统一归到书架：

- `name = qstheory`
- `title = 求是`

### 6.3 幂等要求

迁移必须满足：

- 重跑不重复创建默认书架。
- 旧 topic 若已有关联书架，不覆盖。
- `求是` 书架存在时不重复创建。

## 7. 左栏 UI 改造

### 7.1 Ribbon

当前“笔记本”tab 改名为更贴近层级的表达：

- 保留按钮位置不变
- 图标：`bookshelf`
- tooltip：`书架`

其它 ribbon 暂不重排。

### 7.2 树结构

当前：

```text
笔记本
  近代史
    近代中国
    更早
```

改为：

```text
书架
  求是
    求是网-理论
      网评
      深度调研
    求是杂志-2026年第13期
      2026年第13期
  编年
    党史
      …
```

### 7.3 交互规则

- 点击书架：
  - 仅展开/折叠
  - 不直接切换中栏数据
- 点击笔记本：
  - 切换 `activeTopicId`
  - 中栏与右栏按现有逻辑工作
- 点击 era：
  - 继续按现有逻辑做笔记本内过滤

### 7.4 行操作

本轮只开放：

- 书架：
  - 展开/折叠
  - 第二阶段再做重命名/删除/新建笔记本
- 笔记本：
  - 保留现有 hover 操作（更多、在此新建）

原因：

- 避免书架层和笔记本层的删除/迁移逻辑同时爆炸。

## 8. 导入策略

### 8.1 求是网

不合并成单一笔记本，继续按专题拆：

- `求是网-理论`
- `求是网-经济`
- `求是网-社会`
- …

统一归入书架 `求是`。

注意：

- 现有 `schemaVersion: 2` 导入/导出 payload **不携带 bookshelf 元数据**。
- 因此本轮不扩展导出 schema；采用**导入后再归属书架**的路径。
- 具体做法：
  1. 先创建 topic；
  2. 再通过 `PUT /api/topics/{id}/meta { bookshelfId }` 把该 topic 放入目标书架。
- 这意味着：topic 的导出文件仍然是“单笔记本内容包”，**不是**“书架快照”。

### 8.2 求是杂志

继续“单独笔记本，按期分组”的策略：

- 笔记本：`求是杂志-2026年第13期`
- 分组：`2026年第13期`

统一归入书架 `求是`。

同样采用“先导入 topic，再显式设置 `bookshelfId`”的策略；不把书架归属写入现有 topic 导出文件。

### 8.3 为什么不做“求是网全合一笔记本”

因为那会导致：

- 中栏时间线混合多个专题，阅读负担高
- 收藏、搜索、筛选的语义边界变差
- 后续导入更多文章时单本体量过大，影响交互体验

书架层正是为了解决“同一来源体系下的多笔记本组织”问题，不需要再用“超大笔记本”替代。

## 9. 文件级实施映射

### 前端

- `ui/src/components/timeline-notes/TimelineLucideIcon.vue`
  - 新增 `bookshelf`、`allNotes`
  - 统一左栏与 chip 图标语义

- `ui/src/components/timeline-notes/TopicSidebar.vue`
  - 从 `topic -> era` 改为 `bookshelf -> topic -> era`
  - 左栏笔记本图标从 `folder` 改为 `notebook`
  - 增加书架行渲染、展开状态、计数展示

- `ui/src/components/timeline-notes/NotebookChip.vue`
  - 保持 `NotebookText`
  - 可选补充书架信息 tooltip

- `ui/src/pages/TimelinePage.vue`
  - 按 bookshelf 对 topics 分组
  - 持久化书架展开状态

- `ui/src/styles/timeline-notes.css`
  - 新增书架行、三级缩进、图标尺寸和 hover/active 规范

### 后端

- `backend/app/models/entities.py`
  - 新增 `Bookshelf`
  - `Topic.bookshelf_id`

- `backend/app/services/timeline.py`
  - `list_topics()` 返回书架字段
  - `create_topic()` 默认挂默认书架
  - `topic_to_dict()` / `get_topic_meta()` 透出 bookshelf

- `backend/app/api/topics.py`
  - `PUT /api/topics/{id}/meta` 支持 `bookshelfId`

- `backend/app/api/bookshelves.py`
  - 新增书架 CRUD

- `backend/app/main.py`
  - 注册 `bookshelves` 路由

- `backend/app/services/legacy_migration.py`
  - 启动期幂等迁移 `bookshelves` 表和 `topics.bookshelf_id`

## 10. 分阶段实施顺序

### Phase A · 图标语义统一

- 加 `bookshelf` / `allNotes`
- 左栏笔记本节点从 `folder` 改 `notebook`
- 目标：先把图标语义理顺，不引入数据结构变化

### Phase B · 后端书架模型

- 加表、加列、迁移、topic DTO 补字段
- 目标：前端已经能拿到 bookshelf 信息

### Phase C · 左栏树改造

- `bookshelf -> topic -> era`
- 书架展开/折叠 + topic 切换 + era 过滤

### Phase D · 求是迁移

- 现有远端 `求是网-*` / `求是杂志-*` 迁到书架 `求是`
- 抓取脚本和导入助手补 `bookshelfId`

### Phase E · 书架管理

- 书架新建/重命名/删除
- topic 移动到其他书架

## 11. 风险与回归点

- 左栏树层级更深，必须严格守住行高不变、hover 不回流、展开动画不抖。
- 当前 favorites/search 等跨本视图可能默认还是按扁平 topic 列表工作，需要检查是否需要书架来源文案。
- 书架删除若连带删除 topic，风险高；本轮不做级联破坏操作。
- 旧文档中关于“笔记本平铺、不做层级”的描述必须视为废弃，不得再按旧决策实施。

## 12. 提交前自检

- [ ] 图标语义已统一：书架/笔记本/全部笔记三者不混用
- [ ] 旧 topic 迁移后全部有 bookshelf
- [ ] `求是` 书架下包含 `求是网-*` 和 `求是杂志-*`
- [ ] 左栏点击书架不误切中栏
- [ ] 点击笔记本和 era 的现有行为不回归
- [ ] `GET /api/topics` / `GET /api/bookshelves` / `PUT topic meta` 契约有测试
- [ ] 1920×1080 左栏视觉 QA 截图归档
