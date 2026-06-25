# Visual QA · 中栏工具条 + 弹层统一 + 编辑态黑框修复

- 日期：2026-06-25
- 任务分类：visual / interaction
- 改动文件：`ui/src/components/timeline-notes/TimelineFeed.vue`、`ColumnConfigPopover.vue`、`TimelineLucideIcon.vue`、`ui/src/styles/timeline-notes.css`、`ui/src/pages/TimelinePage.vue`、`docs/obsidian-minimal-implementation-spec.md`

## 验收 URL / 视口
- 构建产物经后端托管：`http://localhost:8000/?topic=1&event=1`（读态）、`...&mode=edit`（编辑态）。
- 实测视口：`innerWidth = 1912`、`innerHeight = 900`（窗口 1936×1117）。
- 偏差说明：物理屏为 `1920×1080`，浏览器 chrome 占用约 180px 高度，因此 CSS 视口高度无法达到 1080（最大约 900）。布局为高度自适应（`position:fixed; inset:0` + 内部滚动），900 高度下首屏无横向溢出、无元素重叠，验收有效。宽度 1912 ≈ 1920。

## 验证项与结果（构建产物 :8000 实测）
1. 工具条分组：查询/视图组（搜索·时间定位·列设置·显示预览）+ `.tl-divider` + 主操作「新建时间点」。窄栏标题省略不挤压按钮。✓
2. 单一锚点·互斥弹层：任一时刻 DOM 中只存在一个 `.tl-pop`；开「时间定位」后再开「列设置」会替换而非并存；点击中栏/Esc 关闭。✓
   - DOM 断言：`document.querySelectorAll('.tl-pop').length === 1`；切换工具后 `.tl-pop` 的 class 由 `tl-pop-locator` 变为 `tl-pop-columns`，旧内容不再存在。
3. 不溢出：列设置弹层 `getBoundingClientRect().right (≈1899) < 中栏 right (≈1912)`，未跨栏；窄栏下 `width = min(320px, calc(100%-20px))` 夹取。✓
4. 列设置弹层（列表式，去掉重复筛选）：无筛选段（`.tl-pop .pop-item.on` 不存在）；必选列 时间/事件 = 2 个 `disabled` 灰色眼睛；类型/标签 = 2 个可点眼睛；自定义列「新建列」可加行并渐进展开 5 个无边框字段。✓
   - 眼睛显隐实测：点 类型 眼睛 → 中栏列头 `时间/事件/类型/标签` 变为 `时间/事件/标签`（仅该列增删，无误伤）；该行加 `is-hidden` 置灰、图标转 `eye-off`；再点恢复。
5. 编辑态无感切换：编辑态正文 `.body-editable` 聚焦时 `getComputedStyle().outlineStyle === 'none'`、`border: 0px none`，黑框消失，阅读↔编辑零位移。✓

## 验证命令
- `npm run agent:check` → AGENTS guard passed (31 files)
- `npm run build` → 构建成功（无错误）
- `npm run test:ui` → 23/23 通过
- `python -m pytest tests/test_timeline_api.py tests/test_date_utils.py` → 9/9 通过

## 已知偏差 / 说明
- 截图文件未入库：claude-in-chrome 截图工具未暴露落盘路径、且本环境未安装 Playwright（安装会新增依赖，违反"不新增依赖"约束）。本次以构建产物 :8000 在 1912×900 下做了上述实时 DOM 断言 + 视觉核对（过程截图见交付会话）。如需正式 PNG 归档，可在后续单独安装 Playwright 以虚拟视口 1920×1080 补齐。
- 信息架构变更：主筛选从中栏移除（与左栏视图区重复），已同步更新 `docs/obsidian-minimal-implementation-spec.md` §2.1/§6.1/§7.2。
