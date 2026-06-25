# 阶段 0 · 边界先定

## 1. 现有后端栈

- Web 框架：`FastAPI`
- ORM：`SQLAlchemy`
- 数据库：本地 `SQLite`
- 静态资源：
  - 构建后的前端由 FastAPI catch-all 路由返回
  - 图片文件走 `/images/*`
- 鉴权：
  - 已移除（本地优先 / 开源，无登录）；所有写接口无需令牌直接生效
- 启动行为：
  - 应用启动时会执行 legacy migration
- 兼容面：
  - 旧 compat HTTP surface（data-files / data-meta / events?topicId= / export / upload / images 别名）已移除；导出统一走 `/api/topics/{id}/export`，启动期 legacy 数据迁移仍保留

现状判断：
- 后端已经具备 timeline 事件的基础 CRUD。
- 现有问题不在“缺能力”，而在“响应契约不够贴近三栏前端”。
- 本轮不顺手重构用户、主题、导入导出、主题系统，只动三栏界面真正依赖的字段。

## 2. 数据模型

### Category / Topic

当前后端实体名是 `Topic`，在前端语义上等价于左栏分类项。

字段：
- `id`: number
- `name`: string
- `title`: string
- `subtitle`: string
- `created_at`: datetime
- `updated_at`: datetime

关系：
- `Topic 1 -> N TimelineEvent`

前端需要的派生字段：
- `eventCount`
- `minDateKey`
- `maxDateKey`
- `minDate`
- `maxDate`

### Event

当前后端实体名是 `TimelineEvent`。

字段：
- `id`: number
- `topic_id`: number
- `date_key`: number
- `date_year`: number
- `date_month`: number
- `date_day`: number
- `headline`: string
- `era`: string
- `body_markdown`: string | null
- `tags_json`: string | null
- `attachments_json`: string | null
- `related_event_ids_json`: string | null
- `image_id`: number | null
- `created_at`: datetime
- `updated_at`: datetime
- `favorite`: boolean
- `deleted_at`: datetime | null

保留的兼容字段：
- `year`
- `sort_key`

关系：
- `TimelineEvent N -> 1 Topic`
- `TimelineEvent 1 -> N EventItem`
- `TimelineEvent N -> 0..1 ImageAsset`

### EventItem

字段：
- `id`: number
- `event_id`: number
- `tag`: string
- `text`: string
- `sort_order`: number

前端语义：
- 这是 legacy 兼容层，不再是右栏主正文来源
- 旧数据可继续读出
- `body_markdown` 缺失时，可回退用它生成降级正文
- `items[]` 的数组顺序就是持久化顺序，会写回 `sort_order`

### Markdown / Attachment / Relation 扩展

为支持右栏阅读 / 编辑面板，本轮要把事件内容升级为“主正文 + 次级结构”。

新增事件层字段语义：
- `body_markdown`
  - 右栏主阅读内容
  - 编辑态以 Markdown 输入
  - 阅读态实时渲染
- `tags_json`
  - 顶层标签数组
  - 不再完全依赖 `EventItem.tag` 推断
- `attachments_json`
  - 附件数组
  - 允许图片、PDF、一般文件
- `related_event_ids_json`
  - 关联其他事件 id
  - 用于右栏“关联笔记”

保守策略：
- 继续保留 `EventItem`
- `body_markdown` 缺失时，可由旧 `items[]` 拼出降级阅读内容
- 旧数据不做一次性大迁移

附件契约补充：
- 保存时写 `attachments`
- 读取时返回可直接渲染/下载的 `url`
- 图片附件额外返回 `imageUrl`

关联笔记契约补充：
- 保存时写 `relatedEventIds`
- 读取时返回 `relatedEvents[]`
- `relatedEvents[]` 里必须带最小可展示信息，而不是只给 id

## 3. Web 端前端真正需要的 DTO

### TopicListItem

左栏专题列表最小契约：

```ts
type TopicListItem = {
  id: number;
  name: string;
  title: string;
  subtitle: string;
  updatedAt: string | null;
  eventCount: number;
  minDateKey: number | null;
  maxDateKey: number | null;
  minDate: string | null;
  maxDate: string | null;
};
```

### TimelineEventDto

中栏卡片 + 右栏详情/编辑最小契约：

```ts
type TimelineEventDto = {
  id: number;
  nodeType: "event";
  dateKey: number;
  sortKey: number;
  isoDate: string;
  dateParts: {
    year: number;
    month: number;
    day: number;
  };
  headline: string;
  displayLabel: string;
  legacyYear: string;
  era: string;
  image: string | null;
  imageUrl: string | null;
  bodyMarkdown: string;
  tags: string[];
  attachments: Array<{
    id: number | null;
    name: string;
    filename: string;
    mimeType: string | null;
    url: string;
    imageUrl: string | null;
  }>;
  relatedEventIds: number[];
  relatedEvents: Array<{
    id: number;
    headline: string;
    displayLabel: string;
  }>;
  createdAt: string;
  updatedAt: string;
  favorite: boolean;
  deletedAt: string | null;
  items: Array<{
    tag: string;
    text: string;
  }>;
};
```

### SaveEventDto

右栏编辑保存最小契约：

```ts
type SaveEventDto = {
  dateYear: number;
  dateMonth: number;
  dateDay: number;
  headline: string;
  era: string;
  image: string | null;
  bodyMarkdown: string;
  tags: string[];
  attachments: Array<{
    id: number | null;
    name: string;
    filename: string;
    mimeType: string | null;
  }>;
  relatedEventIds: number[];
  favorite?: boolean;
  deletedAt?: string | null;
  items: Array<{
    tag: string;
    text: string;
  }>;
};
```

状态更新可以使用窄 payload：

```ts
type EventStatePatch = {
  favorite?: boolean;
  deletedAt?: string | null;
};
```

删除事件后只允许恢复或永久删除；回收站内不允许编辑正文、标签、附件、关联项或收藏状态。

## 4. API 契约

### Read

- `GET /api/config`
  - 用途：品牌名等极少量界面文案

- `GET /api/topics`
  - 用途：左栏分类列表
  - 返回：`TopicListItem[]`

- `GET /api/topics/:topicId/meta`
  - 用途：当前专题标题、副标题、时间边界
  - 返回：单个 `TopicListItem` 扩展对象

- `GET /api/topics/:topicId/events`
  - 用途：中栏时间线与右栏详情数据源
  - 目标正式契约：
  ```ts
  {
    items: TimelineEventDto[];
    bounds: {
      eventCount: number;
      minDateKey: number | null;
      maxDateKey: number | null;
      minDate: string | null;
      maxDate: string | null;
    };
    hasMore: boolean;
    nextCursor: string | null;
  }
  ```
  - 现状说明：
    - 当前主路由已统一返回上面的包装对象
    - 旧的裸数组（legacy）形态曾由已移除的 compat surface 提供，现已无对应路由

### Write

- `POST /api/topics`
  - 用途：新建专题
  - 请求：`{ name: string }`

- `POST /api/topics/:topicId/events`
  - 用途：新建事件
  - 请求：`SaveEventDto`

- `PUT /api/events/:eventId`
  - 用途：更新事件
  - 请求：`SaveEventDto | EventStatePatch`

- `POST /api/media/upload`
  - 用途：上传图片或一般附件
  - 返回：
  ```ts
  {
    id: number;
    filename: string;
    originalName: string;
    mimeType: string | null;
    url: string;
    imageUrl: string | null;
  }
  ```

- `DELETE /api/media/by-filename/:filename`
  - 用途：删除未被引用的临时图片
  - 现状说明：
    - 旧 `/api/images/:filename` 兼容别名已移除
    - web 端正式契约以 `/api/media/by-filename/:filename` 为准

## 5.1 关联笔记显示 / 选择约束

web 首版约束：

- 阅读态不接受“只有 id 没标题”的关联对象
- 读 DTO 必须给出 `relatedEvents[]`
- 写 DTO 仍只提交 `relatedEventIds[]`

选择来源：

- 首版允许直接从当前 topic 的事件全集中选择
- 因为当前 web 主页面默认会加载当前专题完整事件列表
- 因此首版不额外引入专用“关联搜索接口”
- 如果后续 topic 事件流改成懒加载，再补正式候选搜索接口

## 5. 本轮后端只改这些

### 已纳入边界的改动

1. `GET /api/topics` 返回统计字段
说明：
左栏必须直接拿到分类摘要，避免前端额外请求每个 topic 的 `/meta`。

2. 事件 DTO 增加 `imageUrl`
说明：
右栏详情和编辑视图不应该自己拼 `/images/${filename}`。

3. 事件分页响应增加 `hasMore` 和 `nextCursor`
说明：
这是前端真实需要的分页契约，不应再靠 `items.length === limit` 猜测。

4. 明确 `items[]` 顺序与 `sort_order` 对应
说明：
右栏编辑保存必须知道数组顺序会被持久化，否则编辑器拖改顺序没有契约基础。

5. 事件正文升级为 Markdown 主正文
说明：
右栏需求已经明确为“阅读视图 / 编辑视图可切换，Markdown 实时渲染”，所以正文不能再只靠 `items[]` 承载。

6. 事件补顶层标签、附件、关联事件字段
说明：
右栏要支持标签、附件、关联笔记，这三项必须成为正式 DTO，而不是后续 UI 拼装。

### 明确不做

- 不改用户模型
- 不新增第三种导入导出结构；当前仅兼容 legacy array 和 v2 object，导出为 `schemaVersion: 2` 结构化 payload
- 不改主题系统
- 不新增或改造 summary / analytics 接口
- 保留现有 `/api/topics/:topicId/summary` 作为 legacy surface，不纳入本轮 web 端主流程
- 不顺手清理所有 legacy 字段
- 不主动扩展 compat surface，只在文档中标注它是旧接口面
- 不把 Markdown 编辑器做成完整文档产品；只做右栏阅读/编辑闭环

## 6. 为什么这些边界足够支撑三栏前端

- 左栏只需要专题摘要，不需要独立统计页。
- 中栏只需要事件流，不需要横向 summary 轨道或导出布局数据。
- 右栏详情和编辑共用同一份事件 DTO 与保存 DTO，不需要第二套 editor-only 接口。
- 右栏真正的核心从现在起是：
  - 主正文 `bodyMarkdown`
  - 次级标签 `tags`
  - 次级附件 `attachments`
  - 次级关联笔记 `relatedEventIds`
- 当前后端已经有结构化日期、条目和图片引用，足以支撑 web 端首版。
- 当前真正还没钉死的是“正式契约”和“legacy 兼容形态”的分界，而不是底层能力本身。
