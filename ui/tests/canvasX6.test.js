import test from "node:test";
import assert from "node:assert/strict";

import {
  X6_CANVAS_FORMAT,
  isX6CanvasSnapshot,
  buildCanvasSeedSnapshot,
  buildCardNode,
  canvasSnapshotText,
  makeCanvasEdge,
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
