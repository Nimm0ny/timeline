import test from "node:test";
import assert from "node:assert/strict";

import {
  attachmentIconName,
  attachmentKind,
  buildAttachmentMarkdown,
  buildBlockInsertion,
  filterRelatedNoteCandidates,
  markdownListContinuation,
  selectionTouchesRange,
  wrapMarkdownAtRange,
} from "../src/utils/editorMarkdown.js";

test("attachment helpers detect image and file markdown shapes", () => {
  const image = {
    name: "chart.png",
    filename: "chart.png",
    mimeType: "image/png",
    url: "/images/chart.png",
    imageUrl: "/images/chart.png",
  };
  const pdf = {
    name: "source.pdf",
    filename: "source.pdf",
    mimeType: "application/pdf",
    url: "/images/source.pdf",
  };

  assert.equal(attachmentKind(image), "image");
  assert.equal(attachmentIconName(image), "image");
  assert.equal(buildAttachmentMarkdown(image), "![chart.png](/images/chart.png)");
  assert.equal(attachmentKind(pdf), "pdf");
  assert.equal(attachmentIconName(pdf), "file");
  assert.equal(buildAttachmentMarkdown(pdf), "[source.pdf](/images/source.pdf)");
});

test("attachment markdown escapes labels that would break markdown", () => {
  const image = {
    name: "chart [draft]\ncopy.png",
    filename: "chart.png",
    mimeType: "image/png",
    url: "/images/chart.png",
  };

  assert.equal(buildAttachmentMarkdown(image), "![chart \\[draft\\] copy.png](/images/chart.png)");
});

test("markdown insertion helpers preserve cursor intent", () => {
  const wrapped = wrapMarkdownAtRange("alpha beta", 6, 10, "**", "**");
  assert.equal(wrapped.text, "alpha **beta**");
  assert.equal(wrapped.cursorStart, 8);
  assert.equal(wrapped.cursorEnd, 12);

  const inserted = buildBlockInsertion("alpha", 5, 5, "![chart](/chart.png)");
  assert.equal(inserted.text, "alpha\n\n![chart](/chart.png)");
  assert.equal(inserted.cursorStart, inserted.text.length);
});

test("related event search excludes unavailable candidates and matches metadata", () => {
  const candidates = [
    { id: 1, headline: "Current", tags: ["war"] },
    { id: 2, headline: "Deleted", deletedAt: "2026-01-01T00:00:00Z" },
    { id: 3, headline: "Trade Conflict", displayLabel: "1840-06-01 Trade Conflict", tags: ["war"] },
    { id: 4, headline: "Republic Revolution", era: "Modern China", tags: ["politics"] },
  ];

  const results = filterRelatedNoteCandidates(candidates, {
    currentId: 1,
    selectedIds: [4],
    query: "1840",
  });

  assert.deepEqual(results.map((event) => event.id), [3]);
});

test("markdown list continuation extends unordered, ordered, task, and quote lines", () => {
  assert.deepEqual(markdownListContinuation("- 列表项"), { isEmpty: false, prefix: "- " });
  assert.deepEqual(markdownListContinuation("* 星号项"), { isEmpty: false, prefix: "* " });
  assert.deepEqual(markdownListContinuation("  - 缩进项"), { isEmpty: false, prefix: "  - " });
  assert.deepEqual(markdownListContinuation("- [ ] 待办"), { isEmpty: false, prefix: "- [ ] " });
  assert.deepEqual(markdownListContinuation("3. 第三条"), { isEmpty: false, prefix: "4. " });
  assert.deepEqual(markdownListContinuation("> 引用句"), { isEmpty: false, prefix: "> " });
});

test("selectionTouchesRange reveals constructs the cursor is on or adjacent to", () => {
  // Empty cursor inside and at both inclusive boundaries reveals (Typora feel).
  assert.equal(selectionTouchesRange([{ from: 7, to: 7 }], 5, 10), true);
  assert.equal(selectionTouchesRange([{ from: 5, to: 5 }], 5, 10), true);
  assert.equal(selectionTouchesRange([{ from: 10, to: 10 }], 5, 10), true);
  // Just outside either edge stays concealed.
  assert.equal(selectionTouchesRange([{ from: 4, to: 4 }], 5, 10), false);
  assert.equal(selectionTouchesRange([{ from: 11, to: 11 }], 5, 10), false);
  // Multi-cursor: any range touching is enough.
  assert.equal(selectionTouchesRange([{ from: 0, to: 1 }, { from: 9, to: 12 }], 5, 10), true);
  // from/to order is normalized; bad input is safe.
  assert.equal(selectionTouchesRange([{ from: 6, to: 6 }], 10, 5), true);
  assert.equal(selectionTouchesRange([], 5, 10), false);
  assert.equal(selectionTouchesRange(null, 5, 10), false);
});

test("markdown list continuation flags empty items so callers can exit the structure", () => {
  assert.equal(markdownListContinuation("- ").isEmpty, true);
  assert.equal(markdownListContinuation("1. ").isEmpty, true);
  assert.equal(markdownListContinuation("> ").isEmpty, true);
  assert.equal(markdownListContinuation("普通段落"), null);
  assert.equal(markdownListContinuation(""), null);
});
