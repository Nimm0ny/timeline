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
