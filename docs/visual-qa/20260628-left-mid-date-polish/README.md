# Visual QA — 左/中栏打磨 + 日期假精度修复（2026-06-28）

## 任务
1. **左栏·分期按时间排**：笔记本的分期(era)子列表由「按数量降序」改为「按时间」，复用中栏 `compareTimelineEvents` 排序逻辑，左/中两处顺序 1:1 一致（贴合「编年/by-year」定位）。
2. **中栏·空列自动收起**：某属性列在全表(含回收站)无任何值时，从时间线表格隐藏（表头+网格同步），不再显示成一整列「—」；列设置仍列出该列、任一事件填值即恢复。配套把单元格判空统一为 trim（空白→「—」、数字 `0` 保留可见）。
3. **日期假精度修复**：年精度事件（`month==1 && day==1`，迁移对年精度数据的默认值）在中栏与右栏只显年（如 `1840` / `1840年`）；全日期与「真·1号」（`1921-07-23`、`1927-08-01` 南昌起义）保留；公元前年份显示「公元前N」。读态与编辑态日期触发器一致。

## 截图（构建产物，后端 `:8000` 直出 `frontend/`，视口 1920×1080）
- `1920-view-after.png` — `?topic=1&event=1&mode=view`：左栏时序分期 + 中栏年份日期/无空「类型」列 + 右栏「日期 1840年」。
- `1920-edit-after.png` — `?topic=1&event=1&mode=edit`：编辑态，日期触发器同显「1840年」；无边框无工具栏的无感编辑器，读↔编辑零位移。
- `1920-bc-dates-after.png` — `?topic=2` 古代史：BC 事件时间列显「公元前1700000」等。

## 验证
- `npm run test:ui` → **62 通过**（含新增 `emptyTimelineColumnKeys`/`eventColumnHasValue`、`eventColumnValue` 判空一致、日期格式化测试）
- `npm run agent:check` → 通过（42 文件）
- `npm run build` → 干净（`index-CsHKY1ts.js`）
- `python -m pytest tests/test_timeline_api.py tests/test_date_utils.py` → 14 通过
- 独立 subagent review 两轮：**P0 无**；2×P1 已修（单元格判空三处一致 + 数字 `0` 不再被当空）；2×P2 已修（`draftDisplayDate` 非数字输入保护 + 测试补 displayLabel 回退分支）
- playwright-cli 实测 **0 console error**

## 已知偏差 / 范围外
- 古代史(`topic=2`) **标题列仍含冗余日期文本**（headline 内嵌日期，迁移遗留的数据质量问题；§10 不为视觉问题做数据迁移）——与本次显示修复无关，留作独立数据清理。
- era 副标题对 BC 仍显原始数字（如 `-1700000---700000`），属既有 `extractYearLabel` 行为，未纳入本次范围。
- 月精度数据（`day==1, month>1`）在存储上与「真·1号」无法区分，**刻意不折叠**以免误伤建军节(8-1)/建党(7-1)/开国大典(10-1)等真实日期。
