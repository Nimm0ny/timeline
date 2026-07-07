---
type: plan
status: define-first
owner: codex
created: 2026-07-07
source: 用户 2026-07-07 会话（中栏优先、右栏其次、移动端最后；本文件只定义加载性能专项）
参考: AGENTS.md；docs/agent-frontend-hardness.md；docs/mobile-web-design.md；docs/p6-experience-overhaul-design.md（历史背景）；现状代码以 ui/src/pages/TimelinePage.vue、ui/src/components/timeline-notes/TimelineFeed.vue、ui/src/composables/useTimelineStore.js、ui/src/components/timeline-notes/EventDetailPane.vue、ui/src/utils/timelineNotes.js、ui/src/utils/markdownPreview.js 为准
---

# 编年 · 中栏 / 右栏 / 移动端加载性能专项设计

> 本文件是当前“加载性能”工作的唯一实施基线，范围只覆盖中栏所有视图的加载与滚动、右栏详情切换、以及移动端单栏形态下的同类问题。视觉基准、交互基准、数据契约上位约束仍分别以 `AGENTS.md`、`docs/agent-frontend-hardness.md`、`docs/mobile-web-design.md` 为准。
>
> 本文件不改写上位基准；当它们与本文件冲突时，按 **用户当前要求 → AGENTS.md §9 → docs/mobile-web-design.md → docs/agent-frontend-hardness.md → 本文件 → 当前代码** 裁决。

---

## 0. Define-First

- **Goal**
  - 优先解决中栏所有视图的加载、滚动和大数据量渲染开销。
  - 在不改后端产品接口的前提下，降低右栏详情切换延迟与重复渲染成本。
  - 把同一套性能策略收口到移动端单栏主屏 / 详情全屏形态，不额外造一套移动专用架构。
- **Non-goals**
  - 不改 Obsidian 三栏 / 移动端视觉基准，不重做版式。
  - 不修改 `/api/index`、`/api/events/{id}`、`/api/topics/{id}/events` 的 DTO 形状。
  - 不引入 Pinia、状态机库、虚拟滚动以外的新 UI/状态基础设施。
  - 不顺手重构视图系统，不借机改排序、属性、收藏、搜索产品语义。
  - 不把 `content-visibility` 或 CSS 技巧当作虚拟化的替代品。
- **Scope**
  - 主要代码面限定为：
    - `ui/src/components/timeline-notes/TimelineFeed.vue`
    - `ui/src/pages/TimelinePage.vue`
    - `ui/src/composables/useTimelineStore.js`
    - `ui/src/components/timeline-notes/EventDetailPane.vue`
    - `ui/src/utils/timelineNotes.js`
    - `ui/src/utils/markdownPreview.js`
    - `ui/src/styles/timeline-notes.css`
  - 新增文件限定为：
    - `ui/src/composables/useFeedVirtualRows.js`
    - `ui/tests/feedVirtualRows.test.js`
    - `tools/bench_timeline_loading.py`
- **Verification**
  - 结构性验证：DOM 数量、虚拟窗口、缓存容量、移动端滚动恢复。
  - 自动化验证：`agent:check / build / test:ui / pytest`。
  - 手工验收：固定 fixture、`topic=4` 大本 smoke、临时 5000 条性能本、桌面与移动端视觉 QA、手工 Performance trace。

---

## 1. 当前代码真相（2026-07-07）

以下结论均来自当前仓库代码与已归档 QA 记录，实施时不得再沿用旧文档中已过期的加载链判断。

### 1.1 已存在的地基

- 后端已经有 `GET /api/index`，返回 `topics + events` 轻量索引；不是待新增接口。
- 后端已经有 `GET /api/events/{id}`，右栏详情可以懒加载；不是待新增接口。
- `GET /api/topics/{id}/events` 已是 cursor 分页，默认第一页 `limit=100`，不是全量列表。
- `ui/src/composables/useTimelineStore.js` 已有：
  - `eventsIndex`
  - `detailCache`
  - topic page state / `hasMore` / `nextCursor`
  - topic 请求去重
- `ui/src/components/timeline-notes/EventDetailPane.vue` 已经会提前预热 `MarkdownLiveEditor` 的异步 chunk。
- 移动端单栏壳已经存在：
  - `useViewport()`
  - `MobileTopBar`
  - 左抽屉
  - `mobile-detail-open`
  - 详情全屏返回
- `docs/visual-qa/20260706-lazy-topic-loading/README.md` 已证明：
  - `topic=4` 大本当前首屏只渲染第一页 `100` 条，而不是一次挂满 `929` 条。
  - 左栏不会因 topic 切换而 blank。

### 1.2 当前瓶颈

- `ui/src/pages/TimelinePage.vue`
  - `filterEvents()` 会对当前结果集做全量 filter + search + sort。
  - `groupedEvents` 再把结果交给 `groupTimelineEvents()` 二次排序 / 分组。
- `ui/src/utils/timelineNotes.js`
  - `matchesEventSearch()` 在运行时仍会拼接正文、属性、附件文本；没有优先使用已有 `searchText` 作为主路径。
- `ui/src/components/timeline-notes/TimelineFeed.vue`
  - 各视图都在模板层直接 `v-for` 渲染全部行或卡片。
  - 模板内反复调用 `resolvePropertyChips()`、`buildEventPreview()`、`visibleColumns()` 等 helper。
  - `board`、`gallery` 虽然不是线性列表，但仍是全量真实 DOM。
- `ui/src/components/timeline-notes/EventDetailPane.vue`
  - 阅读态 `renderMarkdownToHtml()` 为同步纯函数，无结果缓存。
  - 详情请求只靠 `detailRequestSeq` 防止旧响应覆盖，不会取消旧请求。
- `detailCache` 目前是无上限 `Map`，长会话没有驱逐策略。

### 1.3 当前移动端边界

- 当前移动端 `effectiveView()` 强制返回 `timeline`，因此手机主屏并不会进入 `table / board / gallery / list / outline`。
- 本专项的“中栏所有视图”含义是：
  - **桌面 / 紧凑桌面**：覆盖全部视图。
  - **移动端**：继承同一套基础设施，但实际主屏只走 `timeline` 视图。

---

## 2. 总体策略与依赖

### 2.1 波次顺序

1. **中栏**
   - 共享虚拟化基础设施。
   - 视图级渲染投影。
   - 计算去重与大数据 smoke。
2. **右栏**
   - 请求取消。
   - LRU 详情缓存。
   - Markdown 渲染缓存。
   - 低优先级预取。
3. **移动端**
   - 行高 / overscan / 预取数量差异化。
   - 详情开合前后的滚动恢复。

### 2.2 依赖决策

- 首波虚拟化库固定为 `@tanstack/vue-virtual`。
- 不再比较 `vue-virtual-scroller`、`virtua`、`@vueuse/core` 等方案。
- **注意**：当前 `AGENTS.md §9` 只预批 `CodeMirror 6` 与 `AntV X6`。本专项虽已选定 `@tanstack/vue-virtual` 作为首选实现，但在依赖例外完成前不得开工编码。若例外未获批准，本文件仅作为依赖例外申请与实现基线，不允许在实现中临时改用其他未登记依赖。

### 2.3 统一原则

- 不改现有产品接口，不新增后端性能接口。
- 不改任何视图的视觉结构与交互语义，只改渲染策略和数据准备方式。
- 所有虚拟化都必须保留：
  - 选中事件高亮
  - 日期定位滚动
  - 当前 `load-more`
  - 右栏打开 / 关闭
  - 移动端返回列表位置

---

## 3. 中栏方案（第一优先级，覆盖所有桌面视图）

### 3.1 新增共享基础：`useFeedVirtualRows.js`

新增 `ui/src/composables/useFeedVirtualRows.js`，它是首波唯一新增的前端性能基础设施，职责固定如下：

- 输入：
  - `view`
  - `groups`
  - `sort`
  - `columns`
  - `mobile`
  - `containerEl`
  - `selectedEventId`
  - `hasMore / loadingMore / loading`
- 输出：
  - 统一的虚拟窗口描述
  - 视图需要渲染的可见 items
  - 顶部 / 底部 spacer 尺寸
  - `scrollToEvent(eventId)`
  - `rememberScroll()` / `restoreScroll()`
  - `shouldTriggerLoadMore()`

### 3.2 统一常量

- 线性视图事件行高：
  - 桌面 `33px`
  - 移动 `44px`
- 分组头高度：
  - 桌面 `40px`
  - 移动 `44px`
- overscan：
  - 线性视图桌面 `12`
  - 线性视图移动 `8`
  - gallery 行桌面 `6`
  - gallery 行移动 `4`
  - board 单列卡片桌面 `8`
- load-more 触发：
  - 剩余虚拟项数 `<= 12` 时触发
  - 仅在 `hasMore && !loading && !loadingMore` 时生效

### 3.3 线性视图：`timeline / table / list / outline`

四个视图统一走“纵向虚拟行”。

#### 3.3.1 行模型

- 先在投影层把数据压平成：
  - `group-header`
  - `event-row`
- `timeline / outline` 保留分组头。
- `table / list` 若当前是扁平结果，则只生成 `event-row`。

#### 3.3.2 渲染要求

- 模板层只渲染虚拟窗口内的 items。
- 顶部 / 底部通过 spacer 占位，不允许继续真实挂载全部结果。
- `scrollIntoView()` 全部收敛到 composable 的 `scrollToEvent()`。
- `load-more` 判断不再读完整 `scrollHeight - scrollTop - clientHeight`，而是读虚拟窗口尾部位置。

#### 3.3.3 计算收敛

以下计算不得继续在模板里对同一事件重复执行：

- `resolvePropertyChips()`
- `buildEventPreview()`
- `eventColumnValue()` 的重复派生
- `visibleColumns()`

实现要求：

- 在投影层为 `event-row` 预生成：
  - `previewText`
  - `rowChips`
  - `resolvedColumnValues`
  - `attachmentFlag`
  - `noteTypeFlag`
- 模板只读投影结果，不再临时重算。

### 3.4 `gallery`：按卡片行虚拟化

`gallery` 不做逐卡片 virtualizer，固定采用“按卡片行虚拟化”。

#### 3.4.1 分块方式

- 根据容器宽度与当前 CSS `grid-template-columns: repeat(auto-fill, minmax(196px, 1fr))` 规则，实时计算每行卡片数。
- 先把事件切成 `row chunks`，每个 chunk 代表一行卡片。
- virtualizer 的单位是“行”，不是卡片。

#### 3.4.2 高度策略

- 卡片缩略图固定 `4:3`。
- 初始行高估值：
  - `thumbHeight + 96px`
- 首轮 mount 后允许按真实卡片高度回写当前 breakpoint + 当前列数下的行高缓存。
- 同一 viewport 宽度区间内优先复用最近一次测量，不重复抖动。

### 3.5 `board`：横向真实列 + 列内纵向虚拟化

`board` 保持当前横向列结构，不做列级虚拟化。

#### 3.5.1 固定策略

- `board` 每一列继续真实存在。
- sticky 列头继续真实渲染。
- 每列 `bd-col-body` 内各自挂一个纵向 virtualizer。

#### 3.5.2 高度策略

- 卡片初始估高固定为 `112px`。
- 每列首轮 mount 后，以当前列真实卡片高度回写本列缓存。
- 单列只保留窗口内卡片与 overscan，不允许继续全量挂满。

### 3.6 中栏大数据验收口径

- `topic=4` 与临时性能本都必须满足：
  - 不一次性渲染全部行 / 卡片。
  - `timeline / table / list / outline`
    - 桌面事件 DOM `<= 160`
    - 移动事件 DOM `<= 110`
  - `gallery`
    - 桌面卡片 DOM `<= 120`
    - 移动卡片 DOM `<= 80`
  - `board`
    - 单列卡片 DOM `<= 40`
    - 视口内所有列合计 `<= 160`

---

## 4. 右栏方案（第二优先级）

### 4.1 请求取消

- `ui/src/composables/useApi.js` 的 `request()` 现状已会把额外 fetch options 透传到底层 `fetch`；本专项不要求改它的基础行为。
- 需要补的是调用链：
  - `api.getEvent(id, options)` 支持接收 `{ signal }`
  - `useTimelineStore.ensureEventDetail(eventId, options)` 支持把 `{ signal }` 传给 `api.getEvent()`
- `TimelinePage.vue` 只保留一个在途详情请求 controller：
  - 新选择到来时先 `abort()` 旧请求。
  - 旧请求被取消时不得写 `detailError`，也不得弹错误 toast。

### 4.2 `detailCache` 改为固定上限 LRU

- `useTimelineStore.js` 的 `detailCache` 不再是无上限 `Map`。
- 固定容量 `40`。
- 命中时刷新最近访问顺序。
- 驱逐时不得驱逐当前 `selectedEventId` 对应事件。

### 4.3 Markdown 渲染缓存

- `renderMarkdownToHtml()` 增加模块级 LRU 缓存。
- key 固定为：
  - `eventId + updatedAt + bodyMarkdown`
- 固定容量 `100`。
- 命中缓存时不得重新执行 Markdown 纯文本扫描、表格扫描、围栏扫描。

### 4.4 详情预取

- 调度顺序固定：
  - `requestIdleCallback`
  - 不可用时 `setTimeout(120)`
- 桌面预取：
  - 当前可见列表里，已选事件前后各 `2` 条
- 移动预取：
  - 当前可见列表里，仅后继 `1` 条
- 预取只拉详情，不自动切换选中态，不写 toast。

### 4.5 右栏性能门槛

- `detailCache.size <= 40`
- 详情切换：
  - 缓存命中 `<= 150ms`
  - 未命中 `<= 450ms`
- 快速切换多条记录时，最后一次选择必须稳定落在正确正文，不允许被已取消请求回写覆盖。

---

## 5. 移动端方案（第三优先级）

### 5.1 复用策略

- 移动端复用桌面同一批虚拟化基础设施，不新增移动专用 virtualizer 实现。
- 移动端只允许调整：
  - 行高
  - overscan
  - 预取数量
  - 滚动恢复策略

### 5.2 滚动恢复

- 详情全屏打开前，记录 feed 当前 `scrollTop`。
- 详情关闭后，恢复到打开前位置。
- 验收容差固定为 `±44px`。

### 5.3 移动端边界

- 继续遵守 `docs/mobile-web-design.md`：
  - 主屏是中栏
  - 左抽屉不改
  - 详情全屏不改
- 当前移动主屏强制 `timeline`，因此移动端专项验收只覆盖：
  - 时间线主屏滚动
  - 点行进入全屏详情
  - 返回后恢复位置

---

## 6. 代码改动边界与第一波不做

### 6.1 第一波显式改动边界

- 主要代码面：
  - `TimelineFeed.vue`
  - `TimelinePage.vue`
  - `useTimelineStore.js`
  - `EventDetailPane.vue`
  - `timelineNotes.js`
  - `markdownPreview.js`
  - `timeline-notes.css`
- 新增文件：
  - `ui/src/composables/useFeedVirtualRows.js`
  - `ui/tests/feedVirtualRows.test.js`
  - `tools/bench_timeline_loading.py`
- 新增依赖：
  - `@tanstack/vue-virtual`

### 6.2 第一波显式不做

- 不新增后端性能接口。
- 不修改 `/api/index`、`/api/events/{id}`、`/api/topics/{id}/events` DTO 形状。
- 不改 `board / gallery` 的视觉结构，只改它们的渲染策略。
- 不引入产品级性能监控或埋点系统。
- 不改移动端强制 `timeline` 的产品策略。

### 6.3 `tools/bench_timeline_loading.py`

该工具是专项验收脚本，不是产品代码。职责固定如下：

- 创建临时 notebook：`zzPerfTimelineQA`
- 生成至少 `5000` 条事件
- 覆盖：
  - timeline
  - table
  - list
  - gallery
  - board
  - outline
- 输出固定验收 URL
- 提供清理流程说明，不污染用户现有笔记本

---

## 7. 测试、验收与性能门槛

### 7.1 自动化硬门槛

```bash
cmd /c npm run agent:check
cmd /c npm run build
cmd /c npm run test:ui
python -m pytest tests/test_timeline_api.py tests/test_date_utils.py tests/test_note_types_capabilities.py
```

### 7.2 新增测试项

#### 前端

- `ui/tests/feedVirtualRows.test.js`
  - 虚拟行展平
  - 分组头插入
  - `gallery` row chunking
  - `board` 每列 virtual window
  - 基于虚拟窗口的 `load-more`
  - 移动 / 桌面尺寸切换
- 扩展现有 `ui/tests/timelineNotes.test.js`
  - `matchesEventSearch()` 优先命中 `searchText`
- 扩展现有相关测试
  - 详情请求取消只保留最后一次选择
  - `detailCache` 的 LRU 驱逐
  - Markdown 渲染缓存命中 / 失效
  - 移动端详情开合后的滚动恢复

#### 后端

- 本专项第一波不新增产品契约测试。
- 若仅新增 `tools/bench_timeline_loading.py`，它不进入 `pytest`。

### 7.3 视觉 QA

- 固定 fixture：
  - `http://127.0.0.1:8798/?topic=1&event=1&mode=edit`
- 大本 smoke：
  - `http://127.0.0.1:8798/?topic=4&mode=view`
- 移动端：
  - `390x844` 主屏
  - `390x844` 全屏详情
- 临时性能本：
  - 由 `tools/bench_timeline_loading.py` 生成 `zzPerfTimelineQA`
  - 至少测 `5000` 条
- 截图归档目录固定为：
  - `docs/visual-qa/<YYYYMMDD>-loading-performance/`

### 7.4 结构性性能门槛

- `timeline / table / list / outline`（桌面 / 紧凑桌面）
  - 渲染中的事件 DOM 节点总数 `<= 160`
- `timeline`（移动主屏）
  - 渲染中的事件 DOM 节点总数 `<= 110`
- `gallery`（当前仅桌面可达）
  - 桌面卡片 DOM 总数 `<= 120`
- `board`（当前仅桌面可达）
  - 单列卡片 DOM `<= 40`
  - 当前视口内所有列合计 `<= 160`
- `topic=4` 和 `5000` 条性能本都不得一次性渲染全部行 / 卡片。
- `detailCache.size <= 40`
- 移动端关闭详情后，列表恢复位置误差 `<= 44px`

### 7.5 手工性能数字门槛

生产构建 + warm backend 下：

- `topic=4` 首次显示中栏可见内容 `<= 700ms`
- `5000` 条性能本首次显示中栏可见内容 `<= 1000ms`
- 详情切换：
  - 缓存命中 `<= 150ms`
  - 未命中 `<= 450ms`

`5s` 连续滚动 trace：

- 桌面无单个 Long Task `> 100ms`
- 移动无单个 Long Task `> 150ms`

这些数字属于专项验收门槛，只写入文档，不作为 `test:ui` 的 CI 断言。

### 7.6 手工测量协议

- 使用生产构建与 warm backend。
- Chrome DevTools Performance 或等效浏览器 trace 录制 `5s`。
- DOM 数量用浏览器控制台或临时调试脚本读取，不进入产品代码。
- 若实现需要补轻量 `performance.mark()`，只允许围绕：
  - 中栏首屏可见
  - 详情请求开始
  - 详情正文可读
  这三个节点，且不得演化为长期产品遥测。

---

## 8. Review Gate、收尾与实施假设

### 8.1 Review gate

本专项在正式代码落地时**必触发 review gate**，理由固定为：

- 新依赖
- 跨模块前端数据流
- 三栏视觉基准
- 移动端行为
- 性能验收路径变化

### 8.2 收尾要求

- 性能本必须可清理，不污染用户现有数据。
- QA 过程中若生成临时日志、trace、截图草稿，只允许保留最终归档物。
- 不清理任务前已存在的 `data/` 备份或用户数据库文件。

### 8.3 实施假设

- 本文件是当前专项的权威实现基线。
- `AGENTS.md`、`docs/agent-frontend-hardness.md`、`docs/mobile-web-design.md` 继续提供上位约束，但不承载本专项细节。
- 中栏第一波覆盖全部桌面视图，不是只做默认时间线。
- 第一波不改后端产品接口；如果某个视图在现有数据形状下无法达标，必须在实现文档或 review 中明确降为后续 wave，不允许在实现中临时扩接口。
- 性能本使用临时 notebook，不污染用户现有数据；脚本负责输出创建 / 清理说明。
