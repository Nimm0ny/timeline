import test from "node:test";
import assert from "node:assert/strict";

import {
  X6_CANVAS_FORMAT,
  isX6CanvasSnapshot,
  buildCanvasSeedSnapshot,
  buildCardNode,
  canvasSnapshotText,
  makeCanvasEdge,
  EMBED_CARD_SHAPE,
  EMBED_DEFAULT_WIDTH,
  EMBED_DEFAULT_HEIGHT,
  buildEmbedCardNode,
  isEmbedCard,
  embedNoteIdsFromSnapshot,
  computeEmbedTier,
  EMBED_TIER,
  EMBED_READABLE_PX,
  EMBED_MARGIN_RATIO,
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

test("buildEmbedCardNode tags a Vue-shape embed card with noteId and the fixed embed size", () => {
  const node = buildEmbedCardNode({ x: 40, y: 60, noteId: 7, headline: "标题", preview: "预览" });
  assert.equal(node.shape, EMBED_CARD_SHAPE);
  assert.equal(node.data.kind, "embed");
  assert.equal(node.data.noteId, 7);
  assert.equal(node.width, EMBED_DEFAULT_WIDTH);
  assert.equal(node.height, EMBED_DEFAULT_HEIGHT);
  // headline/preview ride in data — the pre-fetch display fallback + the backend search text;
  // the live title/preview come from the reactive embed store at render time.
  assert.equal(node.data.headline, "标题");
  assert.equal(node.data.preview, "预览");
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

// ---- W5b viewport culling · computeEmbedTier ----
// Card is the fixed embed size; a 1000x600 host. Screen mapping is X6's matrix: local*zoom + t.
const BBOX = { x: 0, y: 0, width: EMBED_DEFAULT_WIDTH, height: EMBED_DEFAULT_HEIGHT }; // 240x120
const HOST = { hostWidth: 1000, hostHeight: 600 };

test("computeEmbedTier: on-screen and readable → preview", () => {
  const tier = computeEmbedTier({ bbox: { ...BBOX, x: 100, y: 100 }, tx: 0, ty: 0, zoom: 1, ...HOST });
  assert.equal(tier, EMBED_TIER.PREVIEW);
});

test("computeEmbedTier: on-screen but zoomed too small → shell", () => {
  // zoom 0.5 → on-screen width 120 < readable 140.
  const tier = computeEmbedTier({ bbox: { ...BBOX, x: 100, y: 100 }, tx: 0, ty: 0, zoom: 0.5, ...HOST });
  assert.equal(tier, EMBED_TIER.SHELL);
  // Right at the readable threshold width stays preview (240*0.6 = 144 ≥ 140).
  assert.equal(
    computeEmbedTier({ bbox: { ...BBOX, x: 0, y: 0 }, zoom: 0.6, ...HOST }),
    EMBED_TIER.PREVIEW
  );
});

test("computeEmbedTier: far off-screen (either axis) → hidden", () => {
  // Far right: left 5000 > hostWidth 1000 + margin 500.
  assert.equal(
    computeEmbedTier({ bbox: { ...BBOX, x: 5000, y: 100 }, zoom: 1, ...HOST }),
    EMBED_TIER.HIDDEN
  );
  // Far below: top 2000 > hostHeight 600 + margin 300.
  assert.equal(
    computeEmbedTier({ bbox: { ...BBOX, x: 100, y: 2000 }, zoom: 1, ...HOST }),
    EMBED_TIER.HIDDEN
  );
  // Panned far off the left via a large negative translate: right edge past -margin.
  assert.equal(
    computeEmbedTier({ bbox: { ...BBOX, x: 100, y: 100 }, tx: -2000, zoom: 1, ...HOST }),
    EMBED_TIER.HIDDEN
  );
});

test("computeEmbedTier: the margin ring keeps a just-off-viewport card non-hidden", () => {
  // hostWidth 1000, default margin ratio 0.5 → ring extends to x=1500.
  // Card left at 1200 (off the literal viewport but inside the ring) → still classified.
  assert.equal(
    computeEmbedTier({ bbox: { ...BBOX, x: 1200, y: 100 }, zoom: 1, ...HOST }),
    EMBED_TIER.PREVIEW
  );
  // Push its left past the ring (1600 > 1500) → hidden. Tight boundary pair with the above.
  assert.equal(
    computeEmbedTier({ bbox: { ...BBOX, x: 1600, y: 100 }, zoom: 1, ...HOST }),
    EMBED_TIER.HIDDEN
  );
  // marginRatio 0 removes the ring → the 1200 card is now hidden.
  assert.equal(
    computeEmbedTier({ bbox: { ...BBOX, x: 1200, y: 100 }, zoom: 1, marginRatio: 0, ...HOST }),
    EMBED_TIER.HIDDEN
  );
});

test("computeEmbedTier: readablePx / marginRatio thresholds are honoured", () => {
  // A 120px-wide render (zoom 0.5) counts as readable when readablePx is lowered to 100.
  assert.equal(
    computeEmbedTier({ bbox: { ...BBOX, x: 0, y: 0 }, zoom: 0.5, readablePx: 100, ...HOST }),
    EMBED_TIER.PREVIEW
  );
  assert.equal(EMBED_READABLE_PX, 140);
  assert.equal(EMBED_MARGIN_RATIO, 0.5);
});

test("computeEmbedTier: fails open to preview on missing / malformed bbox / host", () => {
  assert.equal(computeEmbedTier({}), EMBED_TIER.PREVIEW);
  assert.equal(computeEmbedTier(), EMBED_TIER.PREVIEW);
  assert.equal(computeEmbedTier({ bbox: BBOX, hostWidth: 0, hostHeight: 600 }), EMBED_TIER.PREVIEW);
  // NaN geometry must fail OPEN (preview), never closed (hidden → blank card).
  assert.equal(computeEmbedTier({ bbox: { x: NaN, y: 0, width: 240, height: 120 }, ...HOST }), EMBED_TIER.PREVIEW);
  assert.equal(computeEmbedTier({ bbox: BBOX, tx: NaN, ...HOST }), EMBED_TIER.PREVIEW);
});
