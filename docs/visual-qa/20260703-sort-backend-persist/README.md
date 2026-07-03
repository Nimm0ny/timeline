# QA · 中栏排序 · 后端持久化 / 跨设备同步（Wave-sort-4）

- **任务**：`docs/center-sort-design.md §12` —— sort/groupBy 从 localStorage 迁到后端（跨设备）。**无视觉变化**（排序/分组外观不变），故只做功能 QA，不归档截图。
- **固定 URL**：`http://localhost:8000`（:8000 生产构建）。
- **验证命令**：`pytest tests/test_note_types_capabilities.py tests/test_timeline_api.py` → 26 pass（+`test_sort_and_group_by_normalizers`、+`test_update_sort_and_group_by_persist_and_normalize`、迁移测扩到 sort_json/group_by）· `node tools/qa/agent-guard.mjs` 46 · `node --test` 147 · `build` ok。

## 后端契约（curl 往复，topic 1）

- `GET /meta` 带 `sort`(有序 level 数组) + `groupBy`；新本子默认 `[{time,1}]` / `era`。
- `PUT {sort:[{title,-1},{time,1}], groupBy:"year"}` → 返回并 `GET` 再读一致（持久）。
- **规整**：`PUT {sort:[{time,9},{time,-1}], groupBy:"decade"}` → `[{time,1}]` / `era`（dir 越界→+1、重复字段去重、未知维度→era）。
- **迁移**：启动期幂等 ALTER 给真库 `topics` 加 `sort_json`(默认`[]`)/`group_by`(默认`era`)，5 个既有本子全部 backfill 默认（零行为变化）；迁移前已备份 `data/timeline.db.bak-sortgroupby-*`。

## 前端（Playwright，合成事件 + 真实 DOM）

- **每本 groupBy**：topic 1 时间线排序 popover 点「年」→ 前端 `PUT /api/topics/1/meta {groupBy:"year"}`（curl 即读到 year）；`localStorage` 无 `tl-sort/tl-groupby` 键（已迁走）。
- **跨设备（关键）**：`localStorage.clear()` + reload + 重选 topic 1 → 排序 popover「年」仍 active。localStorage 全清后 groupBy 仍在 = **由后端加载**，非本地缓存。
- **收藏 sort（app_config 路径）**：收藏视图排序 popover 加「标题」级 → 前端 `PUT /api/config {favoritesSort:[{favorited,-1},{title,1}]}`（curl 即读到）；`localStorage.clear()` + reload + 重进收藏 → 排序 popover 仍显 `收藏时间 + 标题`（**由 app_config 加载**）。
- **控制台**：0 error（QA 中 `at UtilityScript` 报错均为 eval 侧「中文字面量经 bash→playwright-cli 偶发编码丢失导致 `.find` undefined→throw」，非应用错误；改用图标 class 选择器后消失）。

## 清理

- QA 中改动的 topic 1 groupBy/sort、config.favoritesSort **均已复原为默认**（`sort_json='[]'`、`group_by='era'`、`favoritesSort=[{favorited,-1}]`）；5 个本子回到迁移直后的纯默认态。DB 备份保留（§6 不删）。

## 数据契约 / 兼容

- 新列 `Topic.sort_json`(TEXT `'[]'`) + `Topic.group_by`(VARCHAR(32) `'era'`)，全默认零破坏；`app_config` 加 `favoritesSort`（跨本收藏无归属本子）。
- 干净切换：不再读 `tl-sort:`/`tl-groupby:` localStorage（功能今日才建、无迁移必要）。后端为 SSOT。
