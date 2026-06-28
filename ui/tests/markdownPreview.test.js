import test from "node:test";
import assert from "node:assert/strict";

import { plainTextFromMarkdown, renderMarkdownToHtml } from "../src/utils/markdownPreview.js";

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

test("plainTextFromMarkdown strips strikethrough tildes", () => {
  assert.equal(plainTextFromMarkdown("~~删~~ 文本"), "删 文本");
});
