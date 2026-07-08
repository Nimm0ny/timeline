# 视觉 / 性能 QA · 2026-07-08 · W5b-1 画布嵌笔记视口裁剪 + T0/T1 分档

- Task: `docs/notes-app-pivot-design.md` §7.3/§7.7 — 画布 embed 卡视口裁剪 + 保真分档（本刀 T0 壳 / T1 预览 + hidden）。
- Design ref: 计划 `W5b-1`（裁剪机制 = T2/T3 地基）。
- 前端 dev server: `http://localhost:5174/?topic=2&event=209&mode=view`（Vite）。
- 后端: `http://localhost:8000`（FastAPI，`data/timeline.db` 由 JSON 种子构建，3 本子 / 208 笔记）。
- Viewport: `1440x900`（桌面布局；画布 host 实测 `1172x804`）。

## Fixture（N=200，§7.7 硬性）

- 临时画布笔记 **id 209**（`QA-200-embeds`，QA 后 permanent-delete）。
- **200 张 embed 卡**，20×10 网格，间距 320×220（内容域 ~6400×2180），引用 **60 个真实笔记**（topic 2 古代史的 entry），循环填满 200 卡。
- 生成器：`make_qa_canvas.py`（本目录，可复现）——`POST /api/topics/2/events`，`noteType:"canvas"` + 200 embed 节点的 `bodyJson` 快照。

## 方法

- URL 深链直开画布；经 Vue 组件内部句柄拿到 X6 `graph`，用 `graph.zoomTo()/translate()/centerContent()` 确定性驱动缩放/平移（X6 的 `mousewheel` 只认 trusted 事件，合成 wheel 无效）。
- 每步测：`.cv-embed-card` 的 `is-hidden`/`is-shell`/无标记（=preview）计数、`getComputedStyle().display`、`getClientRects()`、渲染宽度；`preview_network` 数 batch-preview；后端 access log 数 events 写请求。

## 结果 · 分档随缩放/平移正确切换

| 视图 | hidden（离屏 display:none） | shell（屏上 <140px，仅标题+chip） | preview（屏上 ≥140px，全貌） | 卡渲染宽 |
|---|---|---|---|---|
| zoom 1，centerContent | 136 | 0 | 64 | 240px |
| zoom 1，平移 (+1400,+700) | 185 | 0 | 15 | 240px |
| zoom 0.5，centerContent | 40 | 160 | 0 | 120px |
| zoom 0.5（角缩放） | 70 | 130 | 0 | 120px |

- **hidden**：`getComputedStyle(card).display === 'none'`、`getClientRects().length === 0` → 离屏卡零布局零绘制（节点仍 mounted，未卸载）。
- **shell**：宽 120px（<140 阈），有标题、**无预览行**（`.cv-embed-preview` 经 v-if 收掉），保留容器 chip。
- **preview**：宽 240px，标题 + 预览行 + chip；标题为 batch-preview 现取的真实笔记名（如「陈胜吴广起义」「西周建立」）。
- 缩小（0.5）→ 更多卡入视口但全降 shell（便宜）；平移 → 可见集实时改（152→185 hidden）。均在手势 settle（120ms 防抖）后一次性重算。

## 关键不变量（全部核实通过）

1. **开图成本 O(1)**：每次开画布 **1 次** `POST /api/events/batch-preview`（60 去重 id）；**无 per-card GET**。pan/zoom 期间 **0 fetch**。（`preview_network` 核实）
2. **pan/zoom 零 DB 写**（§5.5 铁律）：整轮缩放/平移后端 access log **无任何** `PUT/DELETE /api/events` 或画布 `POST`（唯一 events 写 = fixture 的 create）；笔记 209 `updatedAt` 保持创建时刻不变。→ 档位走 reactive `canvasTierStore`、不碰 `node.data`，故不触发 history:change / save。
3. **分档默认 fail-open**：`getCardTier` 未命中 → 卡默认 `preview`，绝不空白。

## QA 抓到并已修的缺陷（§7.7 QA 的价值实证）

- **`recomputeTiers` 读错 zoom API**：`g.getZoom?.() ?? 1` —— X6 无 `getZoom`（`typeof g.getZoom === 'undefined'`，getter 是 `g.zoom()`）→ 可选链吞掉、zoom **恒为 1**。后果：任何非 1 缩放下 shell 档**永不触发**、离屏判定错位。单测因直接喂 zoom 而未暴露，**唯有 N=200 浏览器 QA 抓到**。
- 修复：`recomputeTiers` 改用 `g.zoom?.() ?? 1`。修后 zoom 0.5 → shell 由 0 变 130–160，见上表。
- **附带发现（本刀未修，已登记）**：既有 `currentView()`（W5-core，mindmap 亦同）同样用 `g.getZoom?.()` → 视口 zoom 从不持久化（translate 持久、zoom 每次 reload 回落 1）。属独立的 viewport-persistence 缺陷，与裁剪正确性无关，另开小刀统一修（canvas+mindmap 一致），不夹带本刀。

## 验收命令

```bash
node --test ui/tests/*.test.js     # 212 pass（+6 computeEmbedTier）
npm run build                      # ✓
npm run agent:check                # ✓ 58 files
python -m pytest tests/test_links.py   # 14 pass（画布/embed 后端未改，回归）
```

## 归档说明（截图）

本会话 preview 环境无 headless 截图工具（无 playwright/puppeteer），`preview_screenshot` 只回传图像、不能落盘。故本 QA 以**定量分档计数 + 网络/后端日志证据 + 可复现 fixture 脚本**为归档主体（上表即视觉状态的量化真相）。两档视觉状态（zoom 1 preview 板、zoom 0.5 shell 板）已在会话内 `preview_screenshot` 实时核对：preview 板每卡脊+标题+预览+「古代史」chip；shell 板卡缩小、仅标题+chip、无预览行。用 `make_qa_canvas.py` + 上述深链可 1:1 复现。
