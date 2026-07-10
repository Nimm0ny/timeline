# 视觉 QA · 响应式六视图解锁 + 紧凑桌面 overlay（2026-07-10）

基准：`docs/mobile-web-design.md` §7（六视图窄容器）/ §8（紧凑桌面右栏 overlay）。
视口：移动 375×812 · 紧凑桌面 900×700 · 断点边界 1025×700 · 桌面基准 1400×900。

## 移动 375×812（党史 / 中国历史）
- `m-bar2.png` — 工具条解锁后：时间定位 / **视图切换** / **排序** / 列设置 / 密度 / 多选，六按钮不挤。
- `m-views-pop.png` — 视图切换底部 sheet：六视图全列出（画廊按能力禁用置灰）。
- `m-table2.png` — 表格视图初始：全列保留（时间/事件/类型…），非阉割两列。
- `m-final-table2.png` — 表格横向平移后：「事件」标题列 sticky 钉左（hairline 分界、选中行紫底渐变复刻无接缝），「地点」列滚入可读。
- `m-board.png` — 看板泳道（268px 横滚，gutter 12px）。
- `m-list.png` — 列表视图（行内摘要已隐藏，标题/chips/日期承载行）。
- `m-outline.png` — 大纲视图（分组折叠原生可用）。
- `m-detail2.png` — 表格行点按 → 详情全屏滑入（返回/收藏/编辑/⋮ 完整）。

## 紧凑桌面 900×700（中国历史 · 9 自定义列）
- `c-overlay2.png` — 右栏 fixed overlay 浮于中栏（阴影分界、无右 resizer），底下中栏 condensed 投影时间+标题完整可读。
- `c-closed.png` — overlay 关闭：中栏全宽，9 列本自动 condensed（全列需求 1186px > 660px 可用），标题不再被 `minmax(0,1fr)` 压塌。

## 断点边界
- `edge-1025c.png` — 1025px：右栏回到 grid 轨道三栏并存，中栏 condensed 可读。

## 桌面基准回归 1400×900
- `d-final.png` — 党史 timeline 全列（时间/事件/类型/标签/新属性×2），与改动前逐像素一致，`>1024px` 零回归。

验证：`npm run test:ui` 221 全过；`npm run agent:check` 通过。
