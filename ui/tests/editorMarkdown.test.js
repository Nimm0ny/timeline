import test from "node:test";
import assert from "node:assert/strict";

import {
  attachmentIconName,
  attachmentKind,
  buildAttachmentMarkdown,
  buildBlockInsertion,
  filterRelatedEventCandidates,
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

  const results = filterRelatedEventCandidates(candidates, {
    currentId: 1,
    selectedIds: [4],
    query: "1840",
  });

  assert.deepEqual(results.map((event) => event.id), [3]);
});
