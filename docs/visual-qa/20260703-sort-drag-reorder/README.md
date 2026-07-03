# Visual QA · 中栏排序 · 拖拽重排 level（drag-reorder sort levels）

- **任务**：`docs/center-sort-design.md §11「仍未做」` 的「拖拽重排 level」——多级排序编辑器的层顺序（= 优先级）此前只能「移除+重加」，现支持抓手拖拽重排。
- **固定 URL**：`http://localhost:8000`（:8000 生产构建，避 vite 动态 chunk HMR 缓存坑）；经左栏「收藏」标签 →「全部收藏」进入跨本收藏（恒扁平 list，多级编辑器可达，sort 走 `tl-sort:favorites` 哨兵，**零 DB 写**）。
- **视口**：`1920×1080`
- **验证命令**：`node --test "ui/tests/*.test.js"` → 147 pass（+3 `reorderSortLevels`）· `node tools/qa/agent-guard.mjs` → passed(46) · `npm run build` → ok。

## 截图

| 文件 | 状态 |
|---|---|
| `sort-popover-grips.png` | 排序 popover 两级（标题 / 收藏时间），每级左侧 `grip` 抓手 + 方向 caret + × 移除；底部「添加排序层」剩「时间」 |

## 驱动验证结论（合成 MouseEvent，真实 DOM）

- **抓手门控**：单级时无 grip / 无 ×；加「标题」成二级后两行均现 grip + ×（符合「≥2 级才可重排/移除」）。
- **拖拽重排**：合成 `mousedown(grip) → mousemove ×2 → mouseup`（上移 34px ≈ 1 行高 32px），二级「标题」升为主级：`tl-sort:favorites` 由 `[{favorited,-1},{title,1}]` → `[{title,1},{favorited,-1}]`；**各级方向保持不变**（无误翻转）；DOM 行序同步更新。
- **click / drag 分离**（结构性保证：grip 是 flip 按钮的**兄弟**非子元素）：
  - 点「标题」flip 按钮 → 方向 `1 → -1`（翻向仍生效）。
  - 点「标题」grip（`mousedown→mouseup` 原地、无位移）→ 方向不变（grip `@click.stop` + 非 flip 目标，不触发翻向）。
- **控制台**：0 error / 0 warning。

## §9 不变量 / 兼容

- 纯图标：新增 `grip`（Lucide `GripVertical`）经 `TimelineLucideIcon` 集中注册；令牌取色（`--text-faint/--text-muted/--accent-soft/--icon-menu` 等，无魔法值）；行高不变；单一 popover 层不变。
- 纯前端显示层，不动数据契约（sort 仍 `tl-sort:` localStorage，后端未触碰）。拖拽仅**落盘一次**（drop 时 emit），不在拖拽途中逐步写。
