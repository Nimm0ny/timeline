import test from "node:test";
import assert from "node:assert/strict";

import {
  X6_CANVAS_FORMAT,
  isX6CanvasSnapshot,
  buildCanvasSeedSnapshot,
  buildCardNode,
  canvasSnapshotText,
  makeCanvasEdge,
  EMBED_DEFAULT_WIDTH,
  EMBED_DEFAULT_HEIGHT,
  buildEmbedCardNode,
  isEmbedCard,
  embedNoteIdsFromSnapshot,
} from "../src/utils/canvasX6.js";

test("isX6CanvasSnapshot only accepts the tagged canvas shape", () => {
  assert.equal(isX6CanvasSnapshot({ _fmt: X6_CANVAS_FORMAT, cells: [] }), true);
  assert.equal(isX6CanvasSnapshot({ _fmt: "x6-mindmap-v1", cells: [] }), false);
  assert.equal(isX6CanvasSnapshot({ cells: [] }), false);
  assert.equal(isX6CanvasSnapshot(null), false);
});

test("buildCanvasSeedSnapshot seeds one tagged card with 4 ports", () => {
  const seed = buildCanvasSeedSnapshot();
  assert.equal(seed._fmt, X6_CANVAS_FORMAT);
  assert.equal(seed.cells.length, 1);
  assert.equal(seed.cells[0].shape, "rect");
  assert.equal(seed.cells[0].data.kind, "card");
  assert.equal(seed.cells[0].ports.items.length, 4);
});

test("buildCardNode carries text into data + label and mints an id when omitted", () => {
  const node = buildCardNode({ x: 10, y: 20, text: "想法" });
  assert.equal(node.data.text, "想法");
  assert.equal(node.attrs.label.text, "想法");
  assert.match(node.id, /^c-/);
  const explicit = buildCardNode({ id: "c-fixed", x: 0, y: 0, text: "x" });
  assert.equal(explicit.id, "c-fixed");
});

test("canvasSnapshotText concatenates card text (html-stripped) and skips edges", () => {
  const snapshot = {
    _fmt: X6_CANVAS_FORMAT,
    cells: [
      { id: "n1", shape: "rect", data: { text: "<p>甲</p>" }, attrs: { label: { text: "<p>甲</p>" } } },
      { id: "n2", shape: "rect", data: {}, attrs: { label: { text: "乙" } } },
      { id: "e1", shape: "edge", data: { _isCanvasEdge: true } },
    ],
  };
  assert.equal(canvasSnapshotText(snapshot), "甲 乙");
  assert.equal(canvasSnapshotText(null), "");
});

test("makeCanvasEdge is a directed connector with no fixed endpoints", () => {
  const edge = makeCanvasEdge({ line: "#000000" });
  assert.equal(edge.shape, "edge");
  assert.equal(edge.data._isCanvasEdge, true);
  assert.equal(edge.attrs.line.stroke, "#000000");
  assert.ok(edge.attrs.line.targetMarker);
  assert.equal(edge.source, undefined);
});

test("buildEmbedCardNode tags an embed card with noteId and the fixed embed size", () => {
  const node = buildEmbedCardNode({ x: 40, y: 60, noteId: 7, headline: "标题", preview: "预览" });
  assert.equal(node.data.kind, "embed");
  assert.equal(node.data.noteId, 7);
  assert.equal(node.width, EMBED_DEFAULT_WIDTH);
  assert.equal(node.height, EMBED_DEFAULT_HEIGHT);
  // headline/preview reach both the rendered labels and data (for batch-preview refresh).
  assert.equal(node.attrs.label.text, "标题");
  assert.equal(node.attrs.preview.text, "预览");
  assert.equal(node.ports.items.length, 4);
  assert.match(node.id, /^c-/);
  const explicit = buildEmbedCardNode({ id: "c-embed", x: 0, y: 0, noteId: 1 });
  assert.equal(explicit.id, "c-embed");
});

test("isEmbedCard is true only for embed cards (raw JSON or live cell), false for cards and edges", () => {
  assert.equal(isEmbedCard(buildEmbedCardNode({ x: 0, y: 0, noteId: 3 })), true);
  // a live X6-style cell exposing getData()
  assert.equal(isEmbedCard({ getData: () => ({ kind: "embed", noteId: 3 }) }), true);
  assert.equal(isEmbedCard(buildCardNode({ x: 0, y: 0, text: "卡片" })), false);
  assert.equal(isEmbedCard(makeCanvasEdge()), false);
  assert.equal(isEmbedCard(null), false);
});

test("embedNoteIdsFromSnapshot collects + dedupes embed noteIds and ignores other cells", () => {
  const snapshot = {
    _fmt: X6_CANVAS_FORMAT,
    cells: [
      buildEmbedCardNode({ id: "c-a", x: 0, y: 0, noteId: 10 }),
      buildEmbedCardNode({ id: "c-b", x: 0, y: 0, noteId: 10 }), // same note, embedded twice
      buildEmbedCardNode({ id: "c-c", x: 0, y: 0, noteId: 22 }),
      buildCardNode({ x: 0, y: 0, text: "普通卡片" }), // non-embed card
      makeCanvasEdge(), // edge
    ],
  };
  assert.deepEqual(embedNoteIdsFromSnapshot(snapshot), [10, 22]);
  // a bare cells array is accepted too
  assert.deepEqual(embedNoteIdsFromSnapshot(snapshot.cells), [10, 22]);
  // empty / nullish inputs
  assert.deepEqual(embedNoteIdsFromSnapshot(null), []);
  assert.deepEqual(embedNoteIdsFromSnapshot({ cells: [] }), []);
});
