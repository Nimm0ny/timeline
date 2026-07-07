import test from "node:test";
import assert from "node:assert/strict";

import {
  clearMarkdownRenderCache,
  markdownRenderCacheSize,
  plainTextFromMarkdown,
  renderCachedMarkdownToHtml,
  renderMarkdownToHtml,
  renderTableToHtml,
  scanFencedCodeBlocks,
  scanTables,
} from "../src/utils/markdownPreview.js";

test("renderMarkdownToHtml renders headings h1..h6, bold, italic, strikethrough, code", () => {
  assert.equal(renderMarkdownToHtml("# 标题"), "<h1>标题</h1>");
  assert.equal(renderMarkdownToHtml("###### 六级"), "<h6>六级</h6>");
  assert.equal(
    renderMarkdownToHtml("正文 **粗** *斜* ~~删~~ `码`"),
    "<p>正文 <strong>粗</strong> <em>斜</em> <del>删</del> <code>码</code></p>"
  );
});

test("renderMarkdownToHtml renders horizontal rules from --- / *** / ___", () => {
  assert.equal(renderMarkdownToHtml("---"), "<hr>");
  assert.equal(renderMarkdownToHtml("***"), "<hr>");
  assert.equal(renderMarkdownToHtml("___"), "<hr>");
  // A bold/em line is not a rule.
  assert.equal(renderMarkdownToHtml("***粗斜***"), "<p><em><strong>粗斜</strong></em></p>");
});

test("renderMarkdownToHtml groups ordered and unordered lists into ol/ul", () => {
  assert.equal(renderMarkdownToHtml("- 甲\n- 乙"), "<ul><li>甲</li><li>乙</li></ul>");
  assert.equal(renderMarkdownToHtml("1. 甲\n2. 乙"), "<ol><li>甲</li><li>乙</li></ol>");
  // Switching list type closes the previous list.
  assert.equal(
    renderMarkdownToHtml("- 甲\n1. 乙"),
    "<ul><li>甲</li></ul><ol><li>乙</li></ol>"
  );
});

test("renderMarkdownToHtml renders task list items with a checkbox state", () => {
  const html = renderMarkdownToHtml("- [ ] 未完成\n- [x] 完成");
  assert.match(html, /^<ul>/);
  assert.match(html, /<li class="md-task-item"><span class="md-task" role="checkbox" aria-checked="false"><\/span>未完成<\/li>/);
  assert.match(html, /<li class="md-task-item"><span class="md-task" data-checked="true" role="checkbox" aria-checked="true"><\/span>完成<\/li>/);
});

test("renderMarkdownToHtml keeps blockquotes and escapes raw html", () => {
  assert.equal(renderMarkdownToHtml("> 引用"), "<blockquote>引用</blockquote>");
  assert.equal(renderMarkdownToHtml("<script>"), "<p>&lt;script&gt;</p>");
});

test("renderMarkdownToHtml neutralizes script-bearing link schemes (XSS guard)", () => {
  // javascript: / vbscript: / data: links drop the anchor, render label as text.
  assert.equal(renderMarkdownToHtml("[x](javascript:void0)"), "<p>x</p>");
  assert.equal(renderMarkdownToHtml("[y](VBScript:x)"), "<p>y</p>");
  assert.equal(renderMarkdownToHtml("[z](data:text/html)"), "<p>z</p>");
  // Whitespace-obfuscated scheme is still caught.
  assert.equal(renderMarkdownToHtml("[w](java\tscript:void)"), "<p>w</p>");
  // Safe http(s) links keep their anchor.
  assert.equal(
    renderMarkdownToHtml("[ok](https://example.com)"),
    '<p><a class="timeline-markdown-link" href="https://example.com" target="_blank" rel="noopener noreferrer">ok</a></p>'
  );
});

test("renderMarkdownToHtml keeps markdown inside inline code literal", () => {
  assert.equal(renderMarkdownToHtml("`**x**`"), "<p><code>**x**</code></p>");
  assert.equal(renderMarkdownToHtml("`a~~b~~c`"), "<p><code>a~~b~~c</code></p>");
  // Code and real formatting coexist on one line.
  assert.equal(
    renderMarkdownToHtml("see `code` and **bold**"),
    "<p>see <code>code</code> and <strong>bold</strong></p>"
  );
});

test("renderMarkdownToHtml renders fenced code blocks verbatim", () => {
  // Language info → language-* class; content kept literal (no inline markdown).
  assert.equal(
    renderMarkdownToHtml("```js\nconst a = 1;\n```"),
    '<pre class="md-code-block"><code class="language-js">const a = 1;</code></pre>'
  );
  // No info string → bare <code>.
  assert.equal(
    renderMarkdownToHtml("```\nplain\n```"),
    '<pre class="md-code-block"><code>plain</code></pre>'
  );
  // Markdown inside a fence stays literal; HTML is escaped; indentation preserved.
  assert.equal(
    renderMarkdownToHtml("```\n**x** <b>\n  indented\n```"),
    '<pre class="md-code-block"><code>**x** &lt;b&gt;\n  indented</code></pre>'
  );
  // ~~~ fences work too.
  assert.equal(
    renderMarkdownToHtml("~~~\ny\n~~~"),
    '<pre class="md-code-block"><code>y</code></pre>'
  );
  // Unclosed fence consumes to end of document.
  assert.equal(
    renderMarkdownToHtml("```\na\nb"),
    '<pre class="md-code-block"><code>a\nb</code></pre>'
  );
  // A standalone ~~strike~~ line is NOT a fence (needs 3+ tildes to open).
  assert.equal(renderMarkdownToHtml("~~x~~"), "<p><del>x</del></p>");
});

test("scanFencedCodeBlocks reports block line ranges (the shared read/edit source)", () => {
  // Closed block with language → 0-based line ranges.
  assert.deepEqual(scanFencedCodeBlocks("```js\na\nb\n```"), [
    { openLine: 0, closeLine: 3, contentFromLine: 1, contentToLine: 2, hasContent: true, closed: true, lang: "js" },
  ]);
  // Unclosed block runs to the last line.
  assert.deepEqual(scanFencedCodeBlocks("```\nx"), [
    { openLine: 0, closeLine: null, contentFromLine: 1, contentToLine: 1, hasContent: true, closed: false, lang: "" },
  ]);
  // Empty block (```\n```) → no content lines.
  assert.deepEqual(scanFencedCodeBlocks("```\n```"), [
    { openLine: 0, closeLine: 1, contentFromLine: 1, contentToLine: 0, hasContent: false, closed: true, lang: "" },
  ]);
  // Two blocks separated by prose; offsets stay correct.
  const two = scanFencedCodeBlocks("p\n```\nc\n```\nq\n~~~\nd\n~~~");
  assert.equal(two.length, 2);
  assert.deepEqual([two[0].openLine, two[0].closeLine], [1, 3]);
  assert.deepEqual([two[1].openLine, two[1].closeLine], [5, 7]);
  // A standalone ~~strike~~ line is not a fence.
  assert.deepEqual(scanFencedCodeBlocks("~~x~~"), []);
});

test("renderMarkdownToHtml renders GFM tables (header + body, inline cells)", () => {
  // Basic 2x1 table.
  assert.equal(
    renderMarkdownToHtml("| A | B |\n| --- | --- |\n| 1 | 2 |"),
    '<table class="md-table"><thead><tr><th>A</th><th>B</th></tr></thead>' +
      "<tbody><tr><td>1</td><td>2</td></tr></tbody></table>"
  );
  // Column alignment from the delimiter row (:-- left, :-: center, --: right).
  assert.equal(
    renderMarkdownToHtml("| L | C | R |\n| :-- | :-: | --: |\n| a | b | c |"),
    '<table class="md-table"><thead><tr>' +
      '<th style="text-align:left">L</th><th style="text-align:center">C</th><th style="text-align:right">R</th>' +
      "</tr></thead><tbody><tr>" +
      '<td style="text-align:left">a</td><td style="text-align:center">b</td><td style="text-align:right">c</td>' +
      "</tr></tbody></table>"
  );
  // Cells run inline markdown; raw HTML is escaped.
  assert.equal(
    renderMarkdownToHtml("| H |\n| --- |\n| **b** `c` <x> |"),
    '<table class="md-table"><thead><tr><th>H</th></tr></thead>' +
      "<tbody><tr><td><strong>b</strong> <code>c</code> &lt;x&gt;</td></tr></tbody></table>"
  );
  // Escaped pipe (\|) stays a literal cell character, not a column separator.
  assert.equal(
    renderMarkdownToHtml("| a \\| b | c |\n| --- | --- |"),
    '<table class="md-table"><thead><tr><th>a | b</th><th>c</th></tr></thead></table>'
  );
  // Header + delimiter with no body rows → thead only.
  assert.equal(
    renderMarkdownToHtml("| A | B |\n| --- | --- |"),
    '<table class="md-table"><thead><tr><th>A</th><th>B</th></tr></thead></table>'
  );
  // A pipe line followed by `---` is NOT a table (delimiter needs a pipe); --- stays an <hr>.
  assert.equal(renderMarkdownToHtml("text | more\n---"), "<p>text | more</p><hr>");
  // Prose with a pipe + a dashes line is NOT a table when columns don't match (GFM).
  assert.equal(renderMarkdownToHtml("用了 a | b 写法\n| --- |"), "<p>用了 a | b 写法</p><p>| --- |</p>");
  // Table flows between surrounding blocks.
  assert.equal(
    renderMarkdownToHtml("前\n\n| A |\n| --- |\n| 1 |\n\n后"),
    '<p>前</p><table class="md-table"><thead><tr><th>A</th></tr></thead>' +
      "<tbody><tr><td>1</td></tr></tbody></table><p>后</p>"
  );
});

test("scanTables reports table line ranges (the shared read/edit source)", () => {
  // Closed table with body → 0-based line ranges + parsed structure.
  assert.deepEqual(scanTables("| A | B |\n| --- | --- |\n| 1 | 2 |"), [
    {
      fromLine: 0,
      toLine: 2,
      headerLine: 0,
      delimiterLine: 1,
      bodyFromLine: 2,
      bodyToLine: 2,
      aligns: [null, null],
      header: ["A", "B"],
      rows: [["1", "2"]],
    },
  ]);
  // Alignment parsed into the aligns array.
  assert.deepEqual(scanTables("| L | C | R |\n| :-- | :-: | --: |")[0].aligns, ["left", "center", "right"]);
  // No body rows → bodyFromLine null, toLine at the delimiter.
  const noBody = scanTables("| A |\n| --- |")[0];
  assert.deepEqual([noBody.fromLine, noBody.toLine, noBody.bodyFromLine], [0, 1, null]);
  // Two tables separated by a blank line; offsets stay correct.
  const two = scanTables("| A |\n| - |\n| 1 |\n\n| B |\n| - |\n| 2 |");
  assert.equal(two.length, 2);
  assert.deepEqual([two[0].fromLine, two[0].toLine], [0, 2]);
  assert.deepEqual([two[1].fromLine, two[1].toLine], [4, 6]);
  // A pipe table inside a fenced code block is NOT a table.
  assert.deepEqual(scanTables("```\n| A | B |\n| --- | --- |\n```"), []);
  // A pipe line without a delimiter row is not a table.
  assert.deepEqual(scanTables("| just | text |\nno delimiter here"), []);
  // GFM: delimiter column count must equal header column count, else not a table.
  assert.deepEqual(scanTables("| a | b |\n| --- |"), []);
  // An all-empty header row is not a table.
  assert.deepEqual(scanTables("|\n| --- |"), []);
});

test("renderTableToHtml embeds row positions for the CM widget (data-pos)", () => {
  // The read renderer omits data-pos; the CM widget passes rowPos to make rows clickable.
  const table = scanTables("| A |\n| --- |\n| 1 |")[0];
  assert.equal(
    renderTableToHtml(table, { rowPos: [0, 12] }),
    '<table class="md-table"><thead><tr data-pos="0"><th>A</th></tr></thead>' +
      '<tbody><tr data-pos="12"><td>1</td></tr></tbody></table>'
  );
});

test("renderMarkdownToHtml renders footnotes (inline ref + definition line)", () => {
  // Inline reference → superscript marker (no anchor, in-place).
  assert.equal(
    renderMarkdownToHtml("正文[^1] 后"),
    '<p>正文<sup class="md-footnote-ref">1</sup> 后</p>'
  );
  // Definition line → footnote def block; label superscript + inline content.
  assert.equal(
    renderMarkdownToHtml("[^1]: 一条注释"),
    '<div class="md-footnote-def"><sup class="md-footnote-label">1</sup> 一条注释</div>'
  );
  // Definition content runs inline markdown.
  assert.equal(
    renderMarkdownToHtml("[^note]: 见 **重点**"),
    '<div class="md-footnote-def"><sup class="md-footnote-label">note</sup> 见 <strong>重点</strong></div>'
  );
  // Reference + definition together.
  assert.equal(
    renderMarkdownToHtml("观点[^1]\n\n[^1]: 依据"),
    '<p>观点<sup class="md-footnote-ref">1</sup></p>' +
      '<div class="md-footnote-def"><sup class="md-footnote-label">1</sup> 依据</div>'
  );
  // A real link is unaffected; a footnote ref coexists on the same line.
  assert.equal(
    renderMarkdownToHtml("[a](http://x) 与 [^1]"),
    '<p><a class="timeline-markdown-link" href="http://x" target="_blank" rel="noopener noreferrer">a</a>' +
      ' 与 <sup class="md-footnote-ref">1</sup></p>'
  );
  // Definition label and content are HTML-escaped (XSS guard).
  assert.equal(
    renderMarkdownToHtml("[^x]: <script>"),
    '<div class="md-footnote-def"><sup class="md-footnote-label">x</sup> &lt;script&gt;</div>'
  );
  // [^x](url) resolves as a link (link-first), NOT a footnote ref — matches the editor.
  assert.equal(
    renderMarkdownToHtml("见[^1](#fn1)"),
    '<p>见<a class="timeline-markdown-link" href="#fn1" target="_blank" rel="noopener noreferrer">^1</a></p>'
  );
  // An indented [^1]: line is NOT a definition (must be column 0); renders as a paragraph.
  assert.equal(renderMarkdownToHtml("   [^1]: x"), '<p><sup class="md-footnote-ref">1</sup>: x</p>');
  // No space after the colon → no forced space (matches the editor concealing only "]:").
  assert.equal(
    renderMarkdownToHtml("[^1]:x"),
    '<div class="md-footnote-def"><sup class="md-footnote-label">1</sup>x</div>'
  );
});

test("plainTextFromMarkdown strips strikethrough tildes", () => {
  assert.equal(plainTextFromMarkdown("~~删~~ 文本"), "删 文本");
});

test("plainTextFromMarkdown drops footnote ref/def markers (no raw ^1 in previews)", () => {
  assert.equal(plainTextFromMarkdown("观点[^1]后"), "观点后");
  assert.equal(plainTextFromMarkdown("[^1]: 一条注释"), "一条注释");
});

test("renderCachedMarkdownToHtml caches by event identity + updatedAt + body", () => {
  clearMarkdownRenderCache();
  const payload = { eventId: 1, updatedAt: "2026-07-07T00:00:00Z", bodyMarkdown: "# 标题" };
  const first = renderCachedMarkdownToHtml(payload);
  const second = renderCachedMarkdownToHtml(payload);

  assert.equal(first, "<h1>标题</h1>");
  assert.equal(second, "<h1>标题</h1>");
  assert.equal(markdownRenderCacheSize(), 1);

  renderCachedMarkdownToHtml({ ...payload, updatedAt: "2026-07-08T00:00:00Z" });
  assert.equal(markdownRenderCacheSize(), 2);
});
