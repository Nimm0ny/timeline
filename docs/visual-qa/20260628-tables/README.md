# 视觉 QA · GFM 表格（写·二期 round 2）

日期：2026-06-28 ｜ 视口：1920×1080 ｜ 构建：`index-CFvlay75.js` / `MarkdownLiveEditor-6Mr-nfpq.js`

## 范围

读模式渲染器 + CM6 live preview 支持 GFM 表格，守 §9 读↔编辑零位移。架构复刻「围栏代码块」：
`markdownPreview.scanTables()` 为读渲染器与 CM 编辑器共用的单一真源；`renderTableToHtml()`
两端共用产出同一 `<table class="md-table">`；CM 侧 `markdownTableField()`（StateField）在光标不
在表内时以块级 widget 渲染整表（跨行 replace 只能由 StateField 提供），光标落入则显原文（管道符可编辑）。

## 截图

| 文件 | 状态 |
| --- | --- |
| `1920-table-read.png` | 读模式：`<table>` 渲染（表头底色、对齐 :-- / :-: / --:、单元格行内 markdown） |
| `1920-table-edit-widget.png` | 编辑态·光标在表外：块级 widget 渲染整表，与读模式逐字节同 HTML |
| `1920-table-edit-raw.png` | 编辑态·光标落入表内：转原文（`\| 朝代 \| 起讫 \| 备注 \|` 管道符可编辑） |
| `1920-table-read-clown.png` | clown 预设：边框 #dfe2e5 + 偶数行斑马 #f8f8f8 + 行内码粉色 |

## 零位移实测（playwright getComputedStyle / getBoundingClientRect）

默认预设，读 `.markdown-body .md-table` vs 编辑 `.cm-md-table-widget .md-table`：

| 项 | 读 | 编辑 widget |
| --- | --- | --- |
| 外接尺寸 | 250.13 × 107.58 | 250.13 × 107.58 |
| font-size / line-height | 14px / 22.4px | 14px / 22.4px |
| th padding / border / bg | 6px 12px / 1px solid / `--bg-surface-2` | 同 |
| 列对齐（:-- / :-: / --:） | left / center / right | left / center / right |

clown 预设下读↔编辑同样一致（同围栏代码块、行内码的 §5 同步思路）：

| 项 | 读 | 编辑 widget |
| --- | --- | --- |
| td 边框色 | rgb(223,226,229) #dfe2e5 | rgb(223,226,229) #dfe2e5 |
| 偶数行斑马 | rgb(248,248,248) #f8f8f8 | rgb(248,248,248) #f8f8f8 |
| 表头底色 | rgb(245,244,242) | rgb(245,244,242) |
| 表高 | 107.58 | 107.58 |

console 0 errors / 0 warnings。点击 widget 单元格 → 该源行落光标转原文（`data-pos`）。

## 关键点

- **CM6 ViewPlugin 按 `scanTables` 行集跳过**（`if (inSkippedTable(node.from)) return false;`），
  而非依赖 Lezer 的 `Table` 节点名。原因（subagent review P1）：`scanTables` 比 Lezer 宽松时
  （列数不齐、空表头），Lezer 不产 Table 节点 → ViewPlugin 装饰单元格内 EmphasisMark 等
  inline replace，与 StateField 的块级 replace 重叠 → CM 抛错。用同一真源（scanTables）判定
  两端，杜绝发散。实测：`*斜* | 句\n\| --- \|`、`\`码\` | 句\n\| --- \|` 等过去会崩的输入，
  现编辑器正常挂载、0 console error，那几行按普通正文显示。
- **`scanTables` 收紧到 GFM 语义**：分隔行列数须等于表头列数，且表头至少一个非空单元格——
  否则普通含 `|` 的正文（后跟一行 dash）会被误判成表。
- clown 表格固定样式（边框 #dfe2e5/斑马 #f8f8f8）只命中读态 `.markdown-body table`，按
  editor-cm6-design §5 方向 A 同步到 `.markdown-live-editor .cm-md-table-widget`，非新增颜色。
- 语言语法高亮（代码块/表格）刻意不做：需重型 highlighter，违 editor-cm6-design §1。

## 已知小限制（非崩溃）

- 正文**整篇仅一个表格、无任何其它行**时：读模式渲染表，编辑模式因光标只能落在表内 →
  显原文（管道符可编辑）。此为退化边角（真实笔记有 headline + 周边正文），非崩溃、不丢数据；
  已实测 0 console error。后续若需可改 active 判定，暂缓。
