import test from "node:test";
import assert from "node:assert/strict";

import {
  activeLineRangesSignature,
  collectMarkdownImageTokens,
  collectMarkdownImageTokensFromDoc,
  filesFromEvent,
  lineRangesForDocumentRanges,
  markdownImageBlockWidgetField,
  rangeIntersectsLine,
} from "../src/utils/cmMarkdownLivePreview.js";
import { EditorSelection, EditorState } from "@codemirror/state";

function imageDecorationRanges(state, field) {
  const ranges = [];
  state.field(field).decorations.between(0, state.doc.length, (from, to, value) => {
    ranges.push({
      from,
      to,
      block: Boolean(value.spec?.block),
    });
  });
  return ranges;
}

test("markdown image tokens collect alt text, source, and document positions", () => {
  const markdown = ["Intro", "![chart](/images/chart.png)", "After ![map](/images/map.webp) text"].join("\n");

  const tokens = collectMarkdownImageTokens(markdown);

  assert.deepEqual(
    tokens.map((token) => ({
      from: token.from,
      to: token.to,
      alt: token.alt,
      src: token.src,
    })),
    [
      { from: 6, to: 33, alt: "chart", src: "/images/chart.png" },
      { from: 40, to: 64, alt: "map", src: "/images/map.webp" },
    ],
  );
});

test("document-backed markdown image token collection matches string-backed positions", () => {
  const markdown = ["Intro", "![chart](/images/chart.png)", "After ![map](/images/map.webp) text"].join("\n");
  const state = EditorState.create({ doc: markdown });

  assert.deepEqual(collectMarkdownImageTokensFromDoc(state.doc), collectMarkdownImageTokens(markdown));
});

test("document-backed token collection follows CodeMirror normalized line offsets", () => {
  const state = EditorState.create({ doc: "alpha\r\n![chart](/images/chart.png)\r\n" });
  const normalizedMarkdown = state.doc.toString();

  assert.equal(normalizedMarkdown, "alpha\n![chart](/images/chart.png)\n");
  assert.deepEqual(collectMarkdownImageTokensFromDoc(state.doc), collectMarkdownImageTokens(normalizedMarkdown));
});

test("markdown image tokens skip active lines so source remains editable", () => {
  const markdown = "![kept](/kept.png)\n![active](/active.png)";
  const activeLineRanges = [{ from: 19, to: markdown.length }];

  const tokens = collectMarkdownImageTokens(markdown, activeLineRanges);

  assert.deepEqual(
    tokens.map((token) => token.alt),
    ["kept"],
  );
});

test("markdown image tokens skip image lines covered by a multi-line selection", () => {
  const markdown = ["alpha", "![middle](/middle.png)", "omega"].join("\n");
  const state = EditorState.create({ doc: markdown });
  const activeLineRanges = lineRangesForDocumentRanges(state.doc, [{ from: 2, to: markdown.length - 2 }]);

  const tokens = collectMarkdownImageTokens(markdown, activeLineRanges);

  assert.deepEqual(tokens, []);
});

test("markdown image tokens ignore plain links", () => {
  const markdown = "[file](/file.pdf)\n![image](/image.png)";

  const tokens = collectMarkdownImageTokens(markdown);

  assert.deepEqual(
    tokens.map((token) => token.src),
    ["/image.png"],
  );
});

test("rangeIntersectsLine treats caret positions as active line intersections", () => {
  assert.equal(rangeIntersectsLine({ from: 5, to: 5 }, 0, 10), true);
  assert.equal(rangeIntersectsLine({ from: 11, to: 11 }, 0, 10), false);
});

test("active line signature stays stable for caret movement inside the same line", () => {
  const markdown = ["alpha beta", "![image](/image.png)", "omega"].join("\n");
  const state = EditorState.create({ doc: markdown });
  const firstCaretRanges = lineRangesForDocumentRanges(state.doc, [{ from: 1, to: 1 }]);
  const secondCaretRanges = lineRangesForDocumentRanges(state.doc, [{ from: 5, to: 5 }]);
  const nextLineRanges = lineRangesForDocumentRanges(state.doc, [{ from: 12, to: 12 }]);

  assert.equal(activeLineRangesSignature(firstCaretRanges), activeLineRangesSignature(secondCaretRanges));
  assert.notEqual(activeLineRangesSignature(firstCaretRanges), activeLineRangesSignature(nextLineRanges));
});

test("markdown image widget field reveals source on the active image line", () => {
  const field = markdownImageBlockWidgetField();
  let state = EditorState.create({
    doc: ["intro", "![image](/image.png)", "outro"].join("\n"),
    extensions: [field],
  });

  assert.deepEqual(imageDecorationRanges(state, field), [{ from: 6, to: 26, block: true }]);

  state = state.update({ selection: EditorSelection.cursor(8) }).state;
  assert.deepEqual(imageDecorationRanges(state, field), []);

  state = state.update({ selection: EditorSelection.cursor(0) }).state;
  assert.deepEqual(imageDecorationRanges(state, field), [{ from: 6, to: 26, block: true }]);
});

test("markdown image widget field keeps an edited active image line in source mode", () => {
  const field = markdownImageBlockWidgetField();
  let state = EditorState.create({
    doc: ["intro", "![image](/image.png)", "outro"].join("\n"),
    selection: EditorSelection.cursor(8),
    extensions: [field],
  });

  assert.deepEqual(imageDecorationRanges(state, field), []);

  state = state.update({
    changes: { from: 12, insert: "-edited" },
    selection: EditorSelection.cursor(19),
  }).state;

  assert.deepEqual(imageDecorationRanges(state, field), []);

  state = state.update({ selection: EditorSelection.cursor(0) }).state;
  assert.deepEqual(imageDecorationRanges(state, field), [{ from: 6, to: 33, block: true }]);
});

test("filesFromEvent preserves non-image files for parent validation", () => {
  const textFile = { name: "note.txt", type: "text/plain" };
  const imageFile = { name: "chart.png", type: "image/png" };

  assert.deepEqual(
    filesFromEvent({ dataTransfer: { files: [textFile, imageFile, null] } }, "dataTransfer"),
    [textFile, imageFile],
  );
});
