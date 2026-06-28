# Visual QA — 古代史标题清理 + era 副标题/时间列 BC 显示（2026-06-28）

接 `5e7ed15` 之后的 follow-up（用户要求把先前列为「范围外」的两项也做掉）。

## 任务
1. **古代史 headline 内嵌日期数据清理**：`"公元前1700000年01月01日 元谋人活动"` → `"元谋人活动"`。根因＝ seed `data/古代史.json` 的 `year` 字段把「日期+标题」揉在一起，而 `extract_headline_from_legacy_label` 依赖的 `DATE_LABEL_RE` **要求开头是 ASCII 数字**，遇「公元前」前缀直接不匹配、整串当 headline（党史「1856年…」开头是数字所以正常）。仅古代史(topic 2) 受影响，35/106 行。
   - **根因修复（后端）**：新增 `CJK_DATE_PREFIX_RE` + `extract_headline_from_legacy_label` 先剥 `[公元前|公元]?N年M月D日 ` 前缀再回落到既有 `DATE_LABEL_RE`（纯增量，非 CJK 串走原路径不变）。修复 fresh import（`legacy_migration.py:427`）与序列化回退（`timeline.py:387`）。
   - **本地 DB 清理**：现存 35 行脏 headline 经一次性脚本剥离（序列化直接用非空 `event.headline`，故解析器修复不回溯历史数据）。DB 已备份；dry-run 预览 35 行全对、0 误伤、清后 0 残留。`data/timeline.db` 被 gitignore → DB 改动是本地的。
2. **era 副标题 BC**：`buildEraSubtitle` 改用 `formatYearLabel` → 「公元前1700000–公元前700000」（不再「-1700000–-700000」）。
3. **时间列 BC 带月日**：`formatEventDate` 对负年带真实月/日用 CJK「公元前551年9月28日」（与详情 `formatEventDisplayDate` 一致），不再裸「-551-09-28」。

## 截图（构建产物，后端 :8000 直出，视口 1920×1080）
- `1920-gudaishi-after.png` — `?topic=2` 古代史：左栏分期时序（史前→新石器→夏→商→西周…）；中栏时间列「公元前N」/「公元前551年9月28日」、标题干净（元谋人活动…）；era 副标题「公元前N–公元前M · N条」。

## 验证
- `pytest` 14 通过（含扩充的 CJK headline 用例）、`test:ui` 63 通过（含 BC 日期 + era 副标题）、`agent:check` 通过、`build` 干净（`index-CARq1FO7.js`）。
- 独立 subagent review round 3。
- playwright-cli 实测 0 console error。

## 范围外 / 已知
- seed `data/古代史.json` 的 `year` 字段保留 legacy 合并格式——修正后的解析器在导入时会正确提取标题，无需改 JSON。
- AD 时间列仍为紧凑 ISO；BC 因无干净紧凑 ISO 改用 CJK（同列 AD=ISO / BC=CJK，各取其可读）。
