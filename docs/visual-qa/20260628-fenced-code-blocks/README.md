# Visual QA — 围栏代码块 读模式补齐 + 读↔编辑一致（2026-06-28）

「写·二期」第一块。实地排查后发现的**真 bug**：读模式渲染器 `markdownPreview.renderMarkdownToHtml`
**完全不支持围栏代码块**（``` / ~~~），写代码块时围栏符号字面化、各行拆成独立 `<p>`、缩进/空白丢失；
而编辑器 CM6 的 GFM 解析器认识围栏结构 → **读↔编辑发散**，违反 AGENTS §9。

## 改动
1. **共享真源**：`markdownPreview.scanFencedCodeBlocks(text)` 纯函数（0 基行号描述），读渲染器与
   CM 编辑器**共用**，保证两端对「哪几行是代码块」判定一致——读↔编辑零位移的前提。
2. **读模式**（`renderMarkdownToHtml`）：消费 scanner 输出代码块 → `<pre class="md-code-block"><code>`，
   HTML 转义、块内不套 inline markdown / 不当列表标题、空白靠 CSS `white-space: pre-wrap`、未闭合围栏消费到文末。
3. **编辑模式**（CM6）：新增 `markdownCodeBlockField`（**StateField**，非 ViewPlugin——跨行 replace
   只能由 StateField 提供，否则 `RangeError: Decorations that replace line breaks may not be specified via plugins`）。
   逐行 `cm-md-code-line` 背景拼成盒；**光标不在块内时折叠开/闭围栏行**（跨行 replace 收「前换行+围栏文本」，
   首/末内容行仍是视觉行首），与读模式 `<pre>`（无围栏、仅内容）行数一致；光标进块则显原文（可编辑围栏）→ 贴 Obsidian。
4. **CSS**：`--tn-font-mono` 等宽栈（读 `pre.md-code-block code` 与编辑 `.cm-md-code-line` 共用）+
   `font-size:13px / line-height:21px / 上下各 10px padding` 逐项对齐 → 读盒高 `21N+20`。
5. **明确不做**：语言语法**着色**（需引重型 highlighter，违反 editor-cm6-design §1）；表格、脚注（后续 follow-up）。

## 截图（构建产物，后端 :8000 直出，视口 1920×1080；临时事件验后已永久删除）
- `1920-codeblock-read.png` — 读模式：代码块灰底盒、等宽、缩进/内部空行保留、`<b>` 转义、`**not bold**` 字面不加粗。
- `1920-codeblock-edit-folded.png` — 编辑态光标在块外：围栏折叠，盒内仅 6 行内容，与读模式几乎一致（WYSIWYG）。
- `1920-codeblock-edit-active.png` — 编辑态光标在块内：` ```js `/` ``` ` 围栏显现并入盒、可编辑。

## 实测（playwright-cli，:8000 构建版）
- 读盒高 146 = `21×6 + 20`（CSS 数学吻合）；编辑折叠盒 151（5 文本行各 +1px 字形取整）——
  5px 差远在既有 read↔edit 容差内，且被「编辑态空行 28px vs 读 margin 13px」的固有段落差（上下各 15px）淹没。
- 光标进块 → 6 行变 8 行（围栏显现）；移出 → 回折 6 行。全程 **0 console error**。块内键入正常。

## 验收
- `test:ui` 65 通过（+`renderMarkdownToHtml` 围栏 + `scanFencedCodeBlocks` 行号专项）、`agent:check` 通过
  （`--tn-font-mono` 过字体 token guard）、`build` 干净（`index-pFTXBvBL.js`）、`pytest` 14 通过。
- 独立 subagent review。

## 范围外 / 已知
- 文首即代码块（无前置行）折叠退回收「围栏+后换行」，首行盒装饰在该极少见情形下从略；正常（块前有文本/空行）走「前换行+围栏」零损。
- 代码块刻意用 `--bg-surface-2` 子背景（与内联码一致），读↔编辑同款；不加语言色。
