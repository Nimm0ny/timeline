import test from "node:test";
import assert from "node:assert/strict";

import {
  collectMarkdownImageTokens,
  filesFromEvent,
  lineRangesForDocumentRanges,
  rangeIntersectsLine,
} from "../src/utils/cmMarkdownLivePreview.js";
import { EditorState } from "@codemirror/state";

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

test("filesFromEvent preserves non-image files for parent validation", () => {
  const textFile = { name: "note.txt", type: "text/plain" };
  const imageFile = { name: "chart.png", type: "image/png" };

  assert.deepEqual(
    filesFromEvent({ dataTransfer: { files: [textFile, imageFile, null] } }, "dataTransfer"),
    [textFile, imageFile],
  );
});
