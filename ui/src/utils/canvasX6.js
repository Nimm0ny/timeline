// X6 canvas helpers: a free-form board (Obsidian-canvas style) persisted as an X6
// snapshot — the same storage contract as the mindmap ({ _fmt, cells, background,
// view }), but a FLAT graph: free text cards + hand-drawn connectors, no tree, no
// auto-layout, no reparent. Shares the mindmap's pure text/escape helper; the visual
// primitives differ (wrapped cards vs single-line tree nodes), so they live here.
import { extractText } from "./mindmapX6.js";

export const X6_CANVAS_FORMAT = "x6-canvas-v1";
export const CARD_DEFAULT_WIDTH = 200;
export const CARD_DEFAULT_HEIGHT = 88;
const CARD_PORT_RADIUS = 5;

export function isX6CanvasSnapshot(value) {
  return Boolean(value && typeof value === "object" && value._fmt === X6_CANVAS_FORMAT && Array.isArray(value.cells));
}

// A per-session unique card id (matches the mindmap's random-suffix scheme). Snapshot
// persistence keeps the id stable once written, so edges stay wired across reloads.
export function nextCardId() {
  return `c-${Math.random().toString(36).slice(2, 9)}`;
}

// Ports are magnetic so an edge can be dragged card→card from any side. They render
// invisibly until the card is hovered (opacity toggled in CSS: .cv-canvas .x6-port),
// keeping the board clean while still connectable.
export function buildCardPorts() {
  const attrs = {
    circle: { r: CARD_PORT_RADIUS, magnet: true, stroke: "#7b68d9", strokeWidth: 1, fill: "#ffffff" },
  };
  return {
    groups: {
      top: { position: "top", attrs },
      right: { position: "right", attrs },
      bottom: { position: "bottom", attrs },
      left: { position: "left", attrs },
    },
    items: [
      { id: "top", group: "top" },
      { id: "right", group: "right" },
      { id: "bottom", group: "bottom" },
      { id: "left", group: "left" },
    ],
  };
}

export function buildCardAttrs(text, colors = {}, overrides = {}) {
  const { card = "#ffffff", text: textColor = "#3a3733", line = "#d8d4cc" } = colors;
  const { fontSize, fontWeight, color, fill } = overrides;
  const fontFamily = (typeof document !== "undefined" && getComputedStyle(document.body).fontFamily) || "sans-serif";
  return {
    body: {
      rx: 10,
      ry: 10,
      fill: fill || card,
      stroke: line,
      strokeWidth: 1.5,
      cursor: "move",
    },
    label: {
      text: text || "",
      fill: color || textColor,
      fontSize: fontSize || 13,
      fontWeight: fontWeight || "normal",
      fontFamily,
      // Wrap to the card box; ellipsis keeps an overflowing card tidy (auto-grow /
      // resize is post-MVP — cards are a fixed size for now).
      textWrap: { width: -16, height: -12, ellipsis: true },
      textAnchor: "middle",
      textVerticalAnchor: "middle",
      refX: "50%",
      refY: "50%",
    },
  };
}

export function buildCardNode({ id, x, y, text = "", width = CARD_DEFAULT_WIDTH, height = CARD_DEFAULT_HEIGHT, colors = {}, overrides = {} }) {
  return {
    id: id || nextCardId(),
    shape: "rect",
    x,
    y,
    width,
    height,
    ports: buildCardPorts(),
    attrs: buildCardAttrs(text, colors, overrides),
    data: { text, kind: "card" },
    zIndex: 2,
  };
}

// Edge template for the interactive connector; X6 fills source/target from the drag.
// A small arrowhead reads the connection as a direction on the board.
export function makeCanvasEdge(colors = {}) {
  return {
    shape: "edge",
    data: { _isCanvasEdge: true },
    attrs: {
      line: {
        stroke: colors.line || "#b8b2a6",
        strokeWidth: 1.5,
        targetMarker: { name: "block", size: 6 },
      },
    },
    connector: { name: "rounded", args: { radius: 12 } },
    router: { name: "normal" },
    zIndex: 0,
  };
}

// A fresh board seeds one card so the surface isn't blank on first open (mirrors the
// mindmap seeding its root). The card text is placeholder content the user overwrites.
export function buildCanvasSeedSnapshot(colors = {}) {
  return {
    _fmt: X6_CANVAS_FORMAT,
    cells: [buildCardNode({ x: 160, y: 120, text: "新卡片", colors })],
    background: "",
    view: null,
  };
}

// Text of a canvas snapshot for FE-side preview parity; the backend has its own walker
// (collect_x6_snapshot_text) over the same cell shape.
export function canvasSnapshotText(value) {
  const cells = Array.isArray(value) ? value : isX6CanvasSnapshot(value) ? value.cells : null;
  if (!cells?.length) return "";
  return cells
    .filter((cell) => cell && cell.shape !== "edge")
    .map((cell) => extractText(cell?.data?.text) || extractText(cell?.attrs?.label?.text))
    .filter(Boolean)
    .join(" ");
}

// Repaint every card + edge from a freshly-resolved theme palette so the board follows
// a runtime light/dark/contrast switch, preserving each card's per-node overrides
// (data.fill / data.color / fontSize / fontWeight). Mirrors the mindmap's
// applyColorsToGraph but with the flat, uniform card look.
export function applyCanvasColors(graph, colors = {}) {
  if (!graph) return;
  const { card = "#ffffff", text: textColor = "#3a3733", line = "#d8d4cc" } = colors;
  const fontFamily = (typeof document !== "undefined" && getComputedStyle(document.body).fontFamily) || "sans-serif";
  graph.getNodes().forEach((node) => {
    // Embed cards are Vue/DOM nodes that theme themselves from CSS vars — skip the SVG repaint
    // (they have no body/label attrs to set, and touching them would be a no-op at best).
    if (isEmbedCard(node)) return;
    const data = node.getData() || {};
    node.attr("body/fill", data.fill || card);
    node.attr("body/stroke", line);
    node.attr("label/fill", data.color || textColor);
    node.attr("label/fontFamily", fontFamily);
    if (data.fontSize) node.attr("label/fontSize", data.fontSize);
    if (data.fontWeight) node.attr("label/fontWeight", data.fontWeight);
  });
  graph.getEdges().forEach((edge) => {
    edge.attr("line/stroke", colors.line || "#b8b2a6");
  });
}

// ---- W5 note-embed cards -------------------------------------------------------
// A second card kind on the same flat board: an embedded reference to another note
// (data.kind === "embed", data.noteId). It renders as a real DOM node via
// @antv/x6-vue-shape (EmbedCardNode.vue, bound to the shape in embedCardShape.js) so it can
// carry rich, theme-aware content — an accent spine + the live note title over a preview
// line — and later grow to the full-markdown / in-place-edit tiers (§7.2). This file stays
// Vue-free: it only builds the snapshot node; the shape↔component binding lives in
// embedCardShape.js. headline/preview ride in data as the pre-fetch display fallback and as
// the backend walker's search text (§5.5 seam #4); the live values come from the reactive
// embed store on canvas open.
export const EMBED_CARD_SHAPE = "embed-card";
export const EMBED_DEFAULT_WIDTH = 240;
export const EMBED_DEFAULT_HEIGHT = 120;

// An embed card node for the X6 snapshot. Fixed EMBED_DEFAULT_* size; reuses the shared
// magnetic ports so it wires to text cards and other embeds exactly like buildCardNode.
export function buildEmbedCardNode({ id, x, y, noteId, headline = "", preview = "" }) {
  return {
    id: id || nextCardId(),
    shape: EMBED_CARD_SHAPE,
    x,
    y,
    width: EMBED_DEFAULT_WIDTH,
    height: EMBED_DEFAULT_HEIGHT,
    ports: buildCardPorts(),
    data: { kind: "embed", noteId, headline, preview },
    zIndex: 2,
  };
}

// True only for an embed card, tolerating both raw snapshot JSON ({ data }) and a live
// X6 cell (getData()). Text cards ({ kind: "card" }) and edges return false.
export function isEmbedCard(cell) {
  if (!cell) return false;
  const data = typeof cell.getData === "function" ? cell.getData() : cell.data;
  return data?.kind === "embed";
}

// De-duplicated noteIds of every embed card in a canvas snapshot — the input to the
// one-round-trip batch preview fetch on canvas open. Accepts the tagged { _fmt, cells }
// snapshot, a plain { cells } object, or a bare cells array.
export function embedNoteIdsFromSnapshot(snapshot) {
  const cells = Array.isArray(snapshot) ? snapshot : Array.isArray(snapshot?.cells) ? snapshot.cells : null;
  if (!cells?.length) return [];
  const seen = new Set();
  const ids = [];
  for (const cell of cells) {
    if (!isEmbedCard(cell)) continue;
    const data = typeof cell.getData === "function" ? cell.getData() : cell.data;
    const noteId = data?.noteId;
    if (noteId == null || noteId === "") continue;
    const key = String(noteId);
    if (seen.has(key)) continue;
    seen.add(key);
    ids.push(noteId);
  }
  return ids;
}

// ---- W5b viewport culling · fidelity tiers -------------------------------------
// Embed cards render rich DOM (foreignObject + Vue), so a big board must NOT paint every
// card at once (§7.1 Obsidian pain). Each card is classified into a fidelity tier from its
// on-screen geometry; only readable, on-screen cards get the full preview. This file stays
// Vue-free so the decider is unit-tested directly; CanvasEditor feeds it live X6 numbers and
// writes results to the reactive canvasTierStore (which EmbedCardNode reads).
export const EMBED_TIER = { HIDDEN: "hidden", SHELL: "shell", PREVIEW: "preview" };
// On-screen width (in CSS px, i.e. after zoom) below which a card drops to the bare shell.
export const EMBED_READABLE_PX = 140;
// Viewport ring kept "on-screen" each side (fraction of the host), so a small pan doesn't
// pop cards in/out at the edge (§7.3). 0.5 = +50% of the viewport on every side.
export const EMBED_MARGIN_RATIO = 0.5;

// Pure fidelity-tier decision for ONE embed card (§7.2/§7.3). Inputs: the card's LOCAL bbox
// (X6 model coords, pre-transform — from node.getBBox()), the graph pan/zoom transform, and
// the host viewport size. Screen mapping is X6's client matrix(zoom,0,0,zoom,tx,ty):
// screenX = localX*zoom + tx. Returns "hidden" (off-screen ring), "shell" (on-screen but
// narrower than readablePx), or "preview" (on-screen and readable). Fails open to "preview"
// on missing inputs so a card is never wrongly hidden.
// NOTE: the concurrent-rich budget cap (§7.3) is a batch/recompute concern (needs the whole
// set) and lands with the T2 full-markdown tier; a single-card decider can't enforce it.
export function computeEmbedTier({
  bbox,
  tx = 0,
  ty = 0,
  zoom = 1,
  hostWidth,
  hostHeight,
  marginRatio = EMBED_MARGIN_RATIO,
  readablePx = EMBED_READABLE_PX,
} = {}) {
  if (!bbox || !(hostWidth > 0) || !(hostHeight > 0)) return EMBED_TIER.PREVIEW;
  const left = bbox.x * zoom + tx;
  const top = bbox.y * zoom + ty;
  const width = bbox.width * zoom;
  const height = bbox.height * zoom;
  // Malformed geometry (NaN) must fail OPEN to preview — never silently hide a card.
  if (!Number.isFinite(left) || !Number.isFinite(top) || !Number.isFinite(width) || !Number.isFinite(height)) {
    return EMBED_TIER.PREVIEW;
  }
  const mx = hostWidth * marginRatio;
  const my = hostHeight * marginRatio;
  const onScreen =
    left + width >= -mx && left <= hostWidth + mx && top + height >= -my && top <= hostHeight + my;
  if (!onScreen) return EMBED_TIER.HIDDEN;
  if (width < readablePx) return EMBED_TIER.SHELL;
  return EMBED_TIER.PREVIEW;
}
