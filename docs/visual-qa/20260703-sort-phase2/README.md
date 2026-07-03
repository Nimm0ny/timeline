# Visual QA · 中栏排序 Phase 2（分组维度 / 多级排序 / 收藏时间）

- **任务**：docs/center-sort-design.md §11 三项落地 —— ① 分组维度 era/year/month、② 多级排序（primary+secondary…）、③ 收藏时间排序 + 收藏恒扁平。
- **固定 URL**：`http://127.0.0.1:8798/?topic=1`（笔记本「党史」）；收藏经左栏「收藏」标签 → 「全部收藏」进入。
- **视口**：`1920×1080`
- **验证命令**：`node --test "ui/tests/*.test.js"` → 144 pass · `node tools/qa/agent-guard.mjs` → passed(46) · `npm run build` → ok。

## 截图

| 文件 | 状态 |
|---|---|
| `1920-timeline-groupby-popover.png` | 时间线排序 popover：分组[时期/年/月] + 方向[时间正序/倒序] |
| `1920-table-multisort.png` | 表格多级排序：时间 + 类型 两级，两列头各带 caret，底部「添加排序层」 |
| `1920-favorites-flat-sort.png` | 收藏（跨本）恒扁平列表，排序 popover = 收藏时间/时间/标题，默认收藏时间倒序 |

## 驱动验证结论（真实 DOM）

- **① 分组维度**：时间线 popover 显示「分组 时期/年/月」+「方向」两段。切「年」→ era 组变年份桶 `1840/1856/1858/1860`；`localStorage.tl-groupby:1=year` 持久化。undated 归「未定时间」桶（单测锁）。
- **② 多级排序**：表格 popover = 当前层「时间」+「添加排序层 标题/类型/标签/新属性…」。点「类型」追加 → `tl-sort:1=[{time,1},{type,1}]`，**两列头（时间/类型）同时带 caret**。点「事件」列头 → **替换**为单一主排序 `[{title,1}]`（fork A：列头点击=替换主排序，不追加）。
- **③ 收藏扁平**：左栏「收藏 → 全部收藏」→ 标题「收藏（跨本）」、`.view-list`（无 `.era` 分组）；排序 popover 仅 时间/标题/**收藏时间**；默认激活「收藏时间」（倒序，最近收藏在顶）。
- **控制台**：0 error / 0 warning。

## §9 不变量 / 兼容

- 单一 popover 层：排序（含分组段）并入 `activePopover`；纯图标（`arrowUpDown/outline/calendar/chevron*/close/plusSign` 均已注册）；令牌取色；行高不变。
- 排序状态从「单 `{field,dir}`」升级为「有序 level 数组」；`normalizeSortLevels` 兼容读取旧的单对象 localStorage（Phase 1 的 `tl-sort:` 值），零迁移。
- 逻辑归属：comparator/clamp/分组/持久化在 utils+page，中栏组件只收 props / emit。

## 已知偏差 / 收尾

- 分组维度仅时间线/大纲（分组视图）可见；扁平视图无「分组」段。
- 收藏排序落 `tl-sort:favorites`（sentinel owner），与笔记本 `tl-sort:{id}` 隔离。
- QA 收尾：已把 topic 1 的 `displayStyle` 经 API 复位为 `timeline`，并清除本次写入的 `tl-sort:1 / tl-groupby:1 / tl-sort:favorites`。
