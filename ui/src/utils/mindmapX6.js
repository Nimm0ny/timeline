// X6 mindmap helpers: snapshot compatibility, layout, markdown bridge, and
// graph-cell serialization. Kept separate so the Vue wrapper stays focused on
// lifecycle and editor interactions.

export const X6_MINDMAP_FORMAT = "x6-mindmap-v1";
export const DEFAULT_EDGE_ROUTING = "smart-orthogonal";
export const DEFAULT_EDGE_STYLE = "rounded";
export const MINDMAP_EDGE_STYLES = [
  { key: "polyline", label: "直角", routing: DEFAULT_EDGE_ROUTING },
  { key: "rounded", label: "圆角", routing: DEFAULT_EDGE_ROUTING },
  { key: "smooth", label: "平滑曲线", routing: DEFAULT_EDGE_ROUTING },
];

export const NODE_SIZES = [
  { w: 128, h: 38 },
  { w: 108, h: 32 },
  { w: 92, h: 28 },
];

// Curated node markers surfaced in the "节点信息" picker. `key` is a name registered
// in LucideIcon; a node stores at most one marker in data.icon. Markers are
// presentation with no clean markdown form, so — like colour/font-size — they live
// only in the JSON snapshot and are dropped by a .md export.
export const MINDMAP_NODE_ICONS = [
  { key: "star", label: "重点" },
  { key: "flag", label: "标记" },
  { key: "check", label: "完成" },
  { key: "alert", label: "注意" },
  { key: "help", label: "疑问" },
  { key: "idea", label: "想法" },
  { key: "heart", label: "喜欢" },
  { key: "pin", label: "固定" },
];

const MINDMAP_NODE_ICON_KEYS = new Set(MINDMAP_NODE_ICONS.map((item) => item.key));

export function normalizeNodeIcon(icon) {
  const key = String(icon || "").trim();
  return MINDMAP_NODE_ICON_KEYS.has(key) ? key : "";
}

const NODE_PORT_RADIUS = 6;
const EDGE_STEP = 24;
const EDGE_DOGLEG = 36;

export function normalizeEdgeStyle(style) {
  const key = String(style || "").trim();
  if (key === "bezier") return "smooth";
  return MINDMAP_EDGE_STYLES.some((item) => item.key === key) ? key : DEFAULT_EDGE_STYLE;
}

export function edgeRoutingForStyle(style) {
  return DEFAULT_EDGE_ROUTING;
}

export function buildNodePorts() {
  return {
    groups: {
      top: {
        position: "top",
        attrs: { circle: { r: NODE_PORT_RADIUS, magnet: false, stroke: "transparent", fill: "transparent" } },
      },
      right: {
        position: "right",
        attrs: { circle: { r: NODE_PORT_RADIUS, magnet: false, stroke: "transparent", fill: "transparent" } },
      },
      bottom: {
        position: "bottom",
        attrs: { circle: { r: NODE_PORT_RADIUS, magnet: false, stroke: "transparent", fill: "transparent" } },
      },
      left: {
        position: "left",
        attrs: { circle: { r: NODE_PORT_RADIUS, magnet: false, stroke: "transparent", fill: "transparent" } },
      },
    },
    items: [
      { id: "top", group: "top" },
      { id: "right", group: "right" },
      { id: "bottom", group: "bottom" },
      { id: "left", group: "left" },
    ],
  };
}

export function extractText(raw) {
  if (!raw) return "";
  return String(raw)
    .replace(/<[^>]+>/g, "")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&")
    .replace(/&nbsp;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function isX6MindmapSnapshot(value) {
  return Boolean(value && typeof value === "object" && value._fmt === X6_MINDMAP_FORMAT && Array.isArray(value.cells));
}

function sizeFor(level) {
  return NODE_SIZES[Math.min(level, NODE_SIZES.length - 1)];
}

function oppositeSide(side) {
  if (side === "left") return "right";
  if (side === "right") return "left";
  if (side === "top") return "bottom";
  return "top";
}

function stepFromSide(point, side, distance = EDGE_STEP) {
  if (side === "left") return { x: point.x - distance, y: point.y };
  if (side === "right") return { x: point.x + distance, y: point.y };
  if (side === "top") return { x: point.x, y: point.y - distance };
  return { x: point.x, y: point.y + distance };
}

function boxFromNode(node = {}) {
  const x = Number(node?.x || 0);
  const y = Number(node?.y || 0);
  const width = Number(node?.width || 0);
  const height = Number(node?.height || 0);
  return {
    id: node?.id,
    x,
    y,
    width,
    height,
    left: x,
    right: x + width,
    top: y,
    bottom: y + height,
    centerX: x + width / 2,
    centerY: y + height / 2,
  };
}

function portPoint(box, side) {
  if (side === "left") return { x: box.left, y: box.centerY };
  if (side === "right") return { x: box.right, y: box.centerY };
  if (side === "top") return { x: box.centerX, y: box.top };
  return { x: box.centerX, y: box.bottom };
}

function samePoint(left, right) {
  return left && right && left.x === right.x && left.y === right.y;
}

function isCollinear(a, b, c) {
  return (a.x === b.x && b.x === c.x) || (a.y === b.y && b.y === c.y);
}

function preservesDirection(a, b, c) {
  if (a.x === b.x && b.x === c.x) {
    return (b.y - a.y) * (c.y - b.y) >= 0;
  }
  if (a.y === b.y && b.y === c.y) {
    return (b.x - a.x) * (c.x - b.x) >= 0;
  }
  return false;
}

function simplifyPoints(points) {
  const simplified = [];
  for (const point of points) {
    if (!point) continue;
    if (simplified.length && samePoint(simplified[simplified.length - 1], point)) continue;
    if (
      simplified.length >= 2 &&
      isCollinear(simplified[simplified.length - 2], simplified[simplified.length - 1], point) &&
      preservesDirection(simplified[simplified.length - 2], simplified[simplified.length - 1], point)
    ) {
      simplified[simplified.length - 1] = point;
      continue;
    }
    simplified.push(point);
  }
  return simplified;
}

function segmentLength(a, b) {
  return Math.abs((a?.x || 0) - (b?.x || 0)) + Math.abs((a?.y || 0) - (b?.y || 0));
}

function normalizeSegment(a, b) {
  if (a.x === b.x) {
    return { kind: "v", axis: a.x, start: Math.min(a.y, b.y), end: Math.max(a.y, b.y) };
  }
  return { kind: "h", axis: a.y, start: Math.min(a.x, b.x), end: Math.max(a.x, b.x) };
}

function pathSegments(points) {
  const segments = [];
  for (let index = 1; index < points.length; index += 1) {
    const prev = points[index - 1];
    const next = points[index];
    if (!prev || !next || samePoint(prev, next)) continue;
    segments.push(normalizeSegment(prev, next));
  }
  return segments;
}

function inflateBox(box, padding) {
  return {
    left: box.left - padding,
    right: box.right + padding,
    top: box.top - padding,
    bottom: box.bottom + padding,
  };
}

function rangeOverlaps(aStart, aEnd, bStart, bEnd) {
  return Math.max(aStart, bStart) < Math.min(aEnd, bEnd);
}

function segmentHitsBox(segment, box) {
  if (segment.kind === "h") {
    return segment.axis > box.top && segment.axis < box.bottom && rangeOverlaps(segment.start, segment.end, box.left, box.right);
  }
  return segment.axis > box.left && segment.axis < box.right && rangeOverlaps(segment.start, segment.end, box.top, box.bottom);
}

function segmentNearBox(segment, box, padding = 12) {
  return segmentHitsBox(segment, inflateBox(box, padding)) && !segmentHitsBox(segment, box);
}

function overlapPenalty(segments, occupied) {
  return segments.reduce((penalty, segment) => {
    return (
      penalty +
      occupied.filter(
        (item) =>
          item.kind === segment.kind &&
          item.axis === segment.axis &&
          rangeOverlaps(item.start, item.end, segment.start, segment.end)
      ).length
    );
  }, 0);
}

function sidePairs(sourceBox, targetBox, preferredSourceSide = "", preferredTargetSide = "") {
  const pairs = [];
  const push = (sourceSide, targetSide) => {
    const signature = `${sourceSide}:${targetSide}`;
    if (pairs.some((item) => item.signature === signature)) return;
    pairs.push({ sourceSide, targetSide, signature });
  };

  if (preferredSourceSide && preferredTargetSide) push(preferredSourceSide, preferredTargetSide);
  else if (preferredSourceSide) push(preferredSourceSide, oppositeSide(preferredSourceSide));
  else if (preferredTargetSide) push(oppositeSide(preferredTargetSide), preferredTargetSide);

  const dx = targetBox.centerX - sourceBox.centerX;
  const dy = targetBox.centerY - sourceBox.centerY;
  if (Math.abs(dx) >= Math.abs(dy)) {
    if (dx >= 0) {
      push("right", "left");
      push("bottom", "left");
      push("top", "left");
      push("right", "top");
      push("right", "bottom");
    } else {
      push("left", "right");
      push("bottom", "right");
      push("top", "right");
      push("left", "top");
      push("left", "bottom");
    }
  } else if (dy >= 0) {
    push("bottom", "top");
    push("right", "top");
    push("left", "top");
    push("bottom", "left");
    push("bottom", "right");
  } else {
    push("top", "bottom");
    push("right", "bottom");
    push("left", "bottom");
    push("top", "left");
    push("top", "right");
  }
  return pairs;
}

function doglegX(sourceBox, targetBox, sourceSide, targetSide) {
  if (sourceSide === "right" && targetSide === "left") {
    if (sourceBox.right <= targetBox.left) return (sourceBox.right + targetBox.left) / 2;
    return Math.max(sourceBox.right, targetBox.right) + EDGE_DOGLEG;
  }
  if (sourceSide === "left" && targetSide === "right") {
    if (targetBox.right <= sourceBox.left) return (sourceBox.left + targetBox.right) / 2;
    return Math.min(sourceBox.left, targetBox.left) - EDGE_DOGLEG;
  }
  return (sourceBox.centerX + targetBox.centerX) / 2;
}

function doglegY(sourceBox, targetBox, sourceSide, targetSide) {
  if (sourceSide === "bottom" && targetSide === "top") {
    if (sourceBox.bottom <= targetBox.top) return (sourceBox.bottom + targetBox.top) / 2;
    return Math.max(sourceBox.bottom, targetBox.bottom) + EDGE_DOGLEG;
  }
  if (sourceSide === "top" && targetSide === "bottom") {
    if (targetBox.bottom <= sourceBox.top) return (sourceBox.top + targetBox.bottom) / 2;
    return Math.min(sourceBox.top, targetBox.top) - EDGE_DOGLEG;
  }
  return (sourceBox.centerY + targetBox.centerY) / 2;
}

function orthogonalCandidates(sourceBox, targetBox, sourceSide, targetSide) {
  const source = portPoint(sourceBox, sourceSide);
  const target = portPoint(targetBox, targetSide);
  const sourceExit = stepFromSide(source, sourceSide);
  const targetExit = stepFromSide(target, targetSide);
  const midX = doglegX(sourceBox, targetBox, sourceSide, targetSide);
  const midY = doglegY(sourceBox, targetBox, sourceSide, targetSide);
  const variants = [
    [source, sourceExit, { x: sourceExit.x, y: targetExit.y }, targetExit, target],
    [source, sourceExit, { x: targetExit.x, y: sourceExit.y }, targetExit, target],
    [source, sourceExit, { x: midX, y: sourceExit.y }, { x: midX, y: targetExit.y }, targetExit, target],
    [source, sourceExit, { x: sourceExit.x, y: midY }, { x: targetExit.x, y: midY }, targetExit, target],
  ];
  if (sourceExit.x === targetExit.x || sourceExit.y === targetExit.y) {
    variants.unshift([source, sourceExit, targetExit, target]);
  }
  return variants.map((points) => simplifyPoints(points)).filter((points) => points.length >= 2);
}

function x6NodeText(cell = {}) {
  return extractText(cell?.data?.text || cell?.attrs?.label?.text || "");
}

function x6CellGraph(cells) {
  const nodeMap = new Map();
  const childIds = new Map();
  const incoming = new Set();

  (Array.isArray(cells) ? cells : []).forEach((cell) => {
    if (cell?.source == null) {
      nodeMap.set(cell.id, cell);
      childIds.set(cell.id, []);
    }
  });

  (Array.isArray(cells) ? cells : []).forEach((cell) => {
    if (cell?.source == null) return;
    const sourceId = typeof cell.source === "string" ? cell.source : cell.source?.cell;
    const targetId = typeof cell.target === "string" ? cell.target : cell.target?.cell;
    if (!sourceId || !targetId || !childIds.has(sourceId) || !nodeMap.has(targetId)) return;
    childIds.get(sourceId).push(targetId);
    incoming.add(targetId);
  });

  return { nodeMap, childIds, incoming };
}

function compareNodePosition(left = {}, right = {}) {
  const top = (left.y ?? 0) - (right.y ?? 0);
  if (top !== 0) return top;
  return (left.x ?? 0) - (right.x ?? 0);
}

function rootIdFromGraph(nodeMap, incoming) {
  const ids = [...nodeMap.keys()];
  return ids.find((id) => !incoming.has(id)) || ids[0] || "";
}

function buildTreeFromGraph(rootId, nodeMap, childIds) {
  const walk = (id, level = 0) => {
    const cell = nodeMap.get(id);
    if (!cell) return null;
    const data = cell.data || {};
    const children = (childIds.get(id) || [])
      .slice()
      .sort((leftId, rightId) => compareNodePosition(nodeMap.get(leftId), nodeMap.get(rightId)))
      .map((childId) => walk(childId, level + 1))
      .filter(Boolean);
    return {
      data: {
        id,
        text: x6NodeText(cell),
        fontSize: data.fontSize || null,
        fontWeight: data.fontWeight || null,
        color: data.color || null,
        note: data.note || "",
        hyperlink: data.hyperlink || "",
        tag: Array.isArray(data.tag) ? [...data.tag] : [],
        icon: normalizeNodeIcon(data.icon),
        level,
      },
      children,
    };
  };

  return rootId ? walk(rootId, 0) : null;
}

export function x6SnapshotToTree(value) {
  const cells = Array.isArray(value) ? value : isX6MindmapSnapshot(value) ? value.cells : null;
  if (!cells?.length) return null;
  const { nodeMap, childIds, incoming } = x6CellGraph(cells);
  return buildTreeFromGraph(rootIdFromGraph(nodeMap, incoming), nodeMap, childIds);
}

export function computeMindmapRoute(sourceNode, targetNode, options = {}) {
  const sourceBox = boxFromNode(sourceNode);
  const targetBox = boxFromNode(targetNode);
  const style = normalizeEdgeStyle(options.edgeStyle);
  const preferredSourceSide = String(options.preferredSourceSide || "").trim();
  const preferredTargetSide = String(options.preferredTargetSide || "").trim();
  const nodeBoxes = (Array.isArray(options.nodeBoxes) ? options.nodeBoxes : [])
    .map((box) => (box?.left != null && box?.right != null && box?.top != null && box?.bottom != null ? box : boxFromNode(box)))
    .filter((box) => box?.id && box.id !== sourceBox.id && box.id !== targetBox.id);
  const occupied = Array.isArray(options.occupiedSegments) ? options.occupiedSegments : [];
  const candidates = sidePairs(sourceBox, targetBox, preferredSourceSide, preferredTargetSide);
  let best = null;

  for (const pair of candidates) {
    for (const points of orthogonalCandidates(sourceBox, targetBox, pair.sourceSide, pair.targetSide)) {
      const segments = pathSegments(points);
      const bends = Math.max(0, points.length - 2);
      const length = segments.reduce((total, segment) => total + Math.abs(segment.end - segment.start), 0);
      const penalty =
        bends * 24 +
        segments.reduce(
          (score, segment) =>
            score +
            nodeBoxes.filter((box) => segmentHitsBox(segment, box)).length * 1000 +
            nodeBoxes.filter((box) => segmentNearBox(segment, box)).length * 80,
          0
        ) +
        overlapPenalty(segments, occupied) * 40;
      const candidate = {
        ...pair,
        points,
        vertices: points.slice(1, -1),
        segments,
        score: length + penalty,
      };
      if (!best || candidate.score < best.score) best = candidate;
    }
  }

  return (
    best || {
      sourceSide: preferredSourceSide || "right",
      targetSide: preferredTargetSide || "left",
      points: [],
      vertices: [],
      segments: [],
      score: 0,
    }
  );
}

export function buildX6SeedSnapshot(text = "中心主题", options = {}) {
  const tree = { data: { text: extractText(text) || "中心主题" }, children: [] };
  const edgeStyle = normalizeEdgeStyle(options.edgeStyle);
  const { cells } = treeToX6Cells(tree, {
    colors: options.colors,
    direction: options.direction || "LR",
    edgeStyle,
  });
  return {
    _fmt: X6_MINDMAP_FORMAT,
    cells,
    background: options.background || "",
    layout: options.layout || "free",
    edgeRouting: options.edgeRouting || edgeRoutingForStyle(edgeStyle),
    edgeStyle,
    view: options.view || null,
  };
}

export function treeToX6Cells(treeRoot, options = {}) {
  const cells = [];
  let rootId = "";
  const uid = () => `n-${Math.random().toString(36).slice(2, 9)}`;

  const walk = (node, parentId, level) => {
    const id = String(node?.data?.id || uid());
    if (level === 0) rootId = id;
    const text = extractText(node?.data?.text || "");
    const { w, h } = sizeFor(level);

    cells.push({
      id,
      shape: "rect",
      x: 0,
      y: 0,
      width: w,
      height: h,
      ports: buildNodePorts(),
      attrs: buildNodeAttrs(level, text, {
        fontSize: node?.data?.fontSize,
        fontWeight: node?.data?.fontWeight,
        color: node?.data?.color,
      }, options.colors || {}),
      data: {
        text,
        level,
        fontSize: node?.data?.fontSize || null,
        fontWeight: node?.data?.fontWeight || null,
        color: node?.data?.color || null,
        note: node?.data?.note || "",
        hyperlink: node?.data?.hyperlink || "",
        tag: Array.isArray(node?.data?.tag) ? [...node.data.tag] : [],
        icon: normalizeNodeIcon(node?.data?.icon),
      },
    });

    if (parentId) {
      cells.push(makeEdge(parentId, id, options.colors || {}, { edgeStyle: options.edgeStyle }));
    }

    (node?.children || []).forEach((child) => walk(child, id, level + 1));
  };

  walk(treeRoot, "", 0);

  const positions = computeTreeLayout(rootId, cells, { direction: options.direction || "LR" });
  cells.forEach((cell) => {
    if (cell?.source != null || !positions[cell.id]) return;
    cell.x = positions[cell.id].x;
    cell.y = positions[cell.id].y;
  });

  return { cells, rootId };
}

export function buildNodeAttrs(level, text, overrides = {}, colors = {}) {
  const {
    accent = "#7b68d9",
    accentSoft = "rgba(123,104,217,0.12)",
    text: textColor = "#3a3733",
    textStrong = "#2a2722",
    line = "#d8d4cc",
  } = colors;
  const { fontSize, fontWeight, color } = overrides;

  let bodyFill = "transparent";
  let defaultTextColor = textColor;
  let rx = 4;
  if (level === 0) {
    bodyFill = accent;
    defaultTextColor = "#ffffff";
    rx = 8;
  } else if (level === 1) {
    bodyFill = accentSoft;
    defaultTextColor = textStrong;
    rx = 6;
  }

  const baseFontSize = level === 0 ? 15 : level === 1 ? 13 : 12;
  const fontFamily = (typeof document !== "undefined" && getComputedStyle(document.body).fontFamily) || "sans-serif";

  return {
    body: {
      rx,
      ry: rx,
      fill: bodyFill,
      stroke: level >= 2 ? line : "none",
      strokeWidth: 1,
      cursor: "move",
    },
    label: {
      text: text || "",
      fill: color || defaultTextColor,
      fontSize: fontSize || baseFontSize,
      fontWeight: fontWeight || (level === 0 ? 600 : "normal"),
      fontFamily,
      textAnchor: "middle",
      textVerticalAnchor: "middle",
      refX: "50%",
      refY: "50%",
    },
  };
}

export function edgeConnectorForStyle(style) {
  const key = normalizeEdgeStyle(style);
  if (key === "polyline") return { name: "normal" };
  if (key === "smooth") return { name: "smooth" };
  return { name: "rounded", args: { radius: 14 } };
}

export function makeEdge(sourceId, targetId, colors = {}, options = {}) {
  const edgeStyle = normalizeEdgeStyle(options.edgeStyle);
  const sourceSide = options.sourceSide || "right";
  const targetSide = options.targetSide || "left";
  return {
    shape: "edge",
    id: `e-${sourceId}-${targetId}`,
    source: { cell: sourceId, port: sourceSide },
    target: { cell: targetId, port: targetSide },
    data: {
      _isMindEdge: true,
      preferredSourceSide: options.sourceSide || "",
      preferredTargetSide: options.targetSide || "",
      edgeStyle,
      edgeRouting: edgeRoutingForStyle(edgeStyle),
    },
    attrs: {
      line: {
        stroke: colors.line || "#d8d4cc",
        strokeWidth: 1.5,
        targetMarker: null,
      },
    },
    router: { name: "normal" },
    connector: edgeConnectorForStyle(edgeStyle),
    zIndex: -1,
  };
}

export function applyColorsToGraph(graph, colors) {
  if (!graph) return;
  graph.getNodes().forEach((node) => {
    const data = node.getData() || {};
    const level = data.level ?? 1;
    const {
      accent = "#7b68d9",
      accentSoft = "rgba(123,104,217,0.12)",
      text: textColor = "#3a3733",
      textStrong = "#2a2722",
      line = "#d8d4cc",
    } = colors;
    const fontFamily = (typeof document !== "undefined" && getComputedStyle(document.body).fontFamily) || "sans-serif";

    if (level === 0) {
      node.attr("body/fill", accent);
      node.attr("body/stroke", "none");
      node.attr("label/fill", data.color || "#ffffff");
    } else if (level === 1) {
      node.attr("body/fill", accentSoft);
      node.attr("body/stroke", "none");
      node.attr("label/fill", data.color || textStrong);
    } else {
      node.attr("body/fill", "transparent");
      node.attr("body/stroke", line);
      node.attr("label/fill", data.color || textColor);
    }

    node.attr("label/fontFamily", fontFamily);
    if (data.fontSize) node.attr("label/fontSize", data.fontSize);
    if (data.fontWeight) node.attr("label/fontWeight", data.fontWeight);
  });

  graph.getEdges().forEach((edge) => {
    edge.attr("line/stroke", colors.line || "#d8d4cc");
  });
}

function horizontalLayout(rootId, cells, options = {}) {
  const { hGap = 72, vGap = 12 } = options;
  const { nodeMap, childIds } = x6CellGraph(cells);
  // A collapsed node is laid out as a leaf so its hidden subtree takes no space.
  const kidsOf = (id) => (nodeMap.get(id)?.data?.collapsed ? [] : childIds.get(id) || []);
  const span = (id) => {
    const node = nodeMap.get(id);
    if (!node) return 0;
    const kids = kidsOf(id);
    const selfSpan = (node.height || 30) + vGap;
    if (!kids.length) return selfSpan;
    return Math.max(selfSpan, kids.reduce((total, childId) => total + span(childId), 0));
  };
  const positions = {};

  const place = (id, x, centerY) => {
    const node = nodeMap.get(id);
    if (!node) return;
    const width = node.width || 100;
    const height = node.height || 30;
    positions[id] = { x, y: centerY - height / 2 };
    const kids = kidsOf(id);
    if (!kids.length) return;
    const totalSpan = kids.reduce((total, childId) => total + span(childId), 0);
    let cursorY = centerY - totalSpan / 2;
    kids.forEach((childId) => {
      const childSpan = span(childId);
      place(childId, x + width + hGap, cursorY + childSpan / 2);
      cursorY += childSpan;
    });
  };

  place(rootId, 60, 320);
  return positions;
}

function mirrorLayout(positions, nodeMap) {
  const rightEdge = [...nodeMap.values()].reduce(
    (max, node) => Math.max(max, (positions[node.id]?.x || 0) + (node.width || 0)),
    0
  );
  return Object.fromEntries(
    Object.entries(positions).map(([id, pos]) => {
      const width = nodeMap.get(id)?.width || 0;
      return [id, { x: rightEdge - (pos.x + width), y: pos.y }];
    })
  );
}

function verticalLayout(rootId, cells, options = {}) {
  const { hGap = 20, vGap = 46 } = options;
  const { nodeMap, childIds } = x6CellGraph(cells);
  // A collapsed node is laid out as a leaf so its hidden subtree takes no space.
  const kidsOf = (id) => (nodeMap.get(id)?.data?.collapsed ? [] : childIds.get(id) || []);
  const span = (id) => {
    const node = nodeMap.get(id);
    if (!node) return 0;
    const kids = kidsOf(id);
    const selfSpan = (node.width || 100) + hGap;
    if (!kids.length) return selfSpan;
    return Math.max(selfSpan, kids.reduce((total, childId) => total + span(childId), 0));
  };
  const positions = {};

  const place = (id, centerX, y) => {
    const node = nodeMap.get(id);
    if (!node) return;
    const width = node.width || 100;
    const height = node.height || 30;
    positions[id] = { x: centerX - width / 2, y };
    const kids = kidsOf(id);
    if (!kids.length) return;
    const totalSpan = kids.reduce((total, childId) => total + span(childId), 0);
    let cursorX = centerX - totalSpan / 2;
    kids.forEach((childId) => {
      const childSpan = span(childId);
      place(childId, cursorX + childSpan / 2, y + height + vGap);
      cursorX += childSpan;
    });
  };

  place(rootId, 480, 80);
  return positions;
}

export function computeTreeLayout(rootId, cells, options = {}) {
  const direction = String(options.direction || "LR").toUpperCase();
  const { nodeMap } = x6CellGraph(cells);
  if (!rootId || !nodeMap.size) return {};
  if (direction === "TB") return verticalLayout(rootId, cells, options);
  const base = horizontalLayout(rootId, cells, options);
  return direction === "RL" ? mirrorLayout(base, nodeMap) : base;
}

export function relayout(graph, direction = "LR") {
  if (!graph || String(direction).toUpperCase() === "FREE") return;
  const cells = graph.toJSON().cells || [];
  const { nodeMap, incoming } = x6CellGraph(cells);
  const rootId = rootIdFromGraph(nodeMap, incoming);
  if (!rootId) return;
  const positions = computeTreeLayout(rootId, cells, { direction });

  graph.startBatch("layout");
  graph.getNodes().forEach((node) => {
    const pos = positions[node.id];
    if (pos) node.setPosition(pos.x, pos.y);
  });
  graph.stopBatch("layout");
}

// Decide whether a just-dropped node should become a child of another node. `nodes`
// is a normalised list [{ id, x, y, w, h, parentId }] built from the live graph.
// Returns the new parent's id, or "" for a plain move. Guards: the root (no parentId)
// never reparents; a drop on the current parent is a no-op; the moved node's own
// subtree (itself + descendants) is off-limits so a node can't be parented into its
// own branch (cycle); and the moved node's CENTRE must fall inside the target's box.
export function resolveReparentTarget(movedId, nodes) {
  const list = Array.isArray(nodes) ? nodes : [];
  const moved = list.find((node) => node.id === movedId);
  if (!moved || !moved.parentId) return "";
  const childrenOf = new Map();
  list.forEach((node) => {
    if (!node.parentId) return;
    if (!childrenOf.has(node.parentId)) childrenOf.set(node.parentId, []);
    childrenOf.get(node.parentId).push(node.id);
  });
  const forbidden = new Set([movedId]);
  const stack = [movedId];
  while (stack.length) {
    const id = stack.pop();
    (childrenOf.get(id) || []).forEach((child) => {
      if (!forbidden.has(child)) {
        forbidden.add(child);
        stack.push(child);
      }
    });
  }
  const cx = moved.x + moved.w / 2;
  const cy = moved.y + moved.h / 2;
  for (const node of list) {
    if (forbidden.has(node.id) || node.id === moved.parentId) continue;
    if (cx >= node.x && cx <= node.x + node.w && cy >= node.y && cy <= node.y + node.h) return node.id;
  }
  return "";
}

// --- Node metadata helpers (hyperlink / tags) ---
// A node hyperlink is rendered as a clickable <a>, so untrusted schemes must be
// neutralised. Known-safe schemes pass through; a bare domain/path is defaulted to
// https://; anything else (javascript:/data:/vbscript:/… ) also gets the https://
// prefix, which turns a script/data URI into an inert, non-navigating URL — the same
// approach the property system uses (see propertyHref).
export function sanitizeHyperlink(url) {
  const raw = String(url ?? "").trim();
  if (!raw) return "";
  if (/^(https?:\/\/|mailto:|tel:|ftp:\/\/)/i.test(raw)) return raw;
  if (raw.startsWith("#")) return raw;
  return `https://${raw.replace(/^\/+/, "")}`;
}

// Split a raw tag input into individual tags: break on commas/whitespace so tags are
// single tokens (matching how the markdown bridge tokenises them), strip a leading #,
// drop blanks. Order preserved; de-duplication is left to normalizeTags.
export function parseTagInput(raw) {
  return String(raw ?? "")
    .split(/[,\s]+/)
    .map((tag) => tag.trim().replace(/^#+/, ""))
    .filter(Boolean);
}

// Canonical tag list for storage: trim, strip a leading #, drop blanks, de-dup while
// keeping first-seen order.
export function normalizeTags(list) {
  const seen = new Set();
  const out = [];
  (Array.isArray(list) ? list : []).forEach((item) => {
    const tag = String(item ?? "").trim().replace(/^#+/, "");
    if (tag && !seen.has(tag)) {
      seen.add(tag);
      out.push(tag);
    }
  });
  return out;
}

// --- Markdown style bridge (clean route) ---
// Whole-node emphasis maps to native markdown so a mindmap survives an
// export -> import round-trip: bold <-> **text**, hyperlink <-> [text](url),
// tags <-> trailing #tag. Colour and font-size are presentation with no clean
// markdown form, so they live only in the JSON snapshot — a .md export drops
// them by design (JSON export is the lossless path).
function isBoldWeight(weight) {
  const value = String(weight ?? "").toLowerCase();
  return value === "bold" || Number(value) >= 600;
}

export function nodeTextToMarkdown(data = {}) {
  let label = extractText(data?.text || "");
  const url = String(data?.hyperlink || "").trim();
  if (label && url) label = `[${label}](${url})`;
  if (label && isBoldWeight(data?.fontWeight)) label = `**${label}**`;
  const tags = (Array.isArray(data?.tag) ? data.tag : [])
    // Strip inner # so a tag survives the decode class /#([^\s#]+)/ on re-import.
    .map((tag) => String(tag || "").trim().replace(/\s+/g, "-").replace(/#/g, ""))
    .filter(Boolean);
  // A tag-only node keeps a meaningful label (#tag) so neither it nor its subtree
  // is dropped by the "empty label" guard in x6CellsToMarkdown.
  if (tags.length) label = `${label ? `${label} ` : ""}${tags.map((tag) => `#${tag}`).join(" ")}`;
  return label.trim();
}

export function markdownToNodeData(raw) {
  let text = String(raw || "").trim();
  const data = {};
  const tags = [];
  let match;
  // Peel trailing #tags (Obsidian-style), right to left, so order is preserved.
  while ((match = text.match(/(?:^|\s)#([^\s#]+)$/))) {
    tags.unshift(match[1]);
    text = text.slice(0, match.index).trimEnd();
  }
  if (tags.length) data.tag = tags;
  // Whole-node bold (nodes carry one font-weight, so only a fully-wrapped label counts).
  const bold = text.match(/^\*\*([\s\S]+)\*\*$/) || text.match(/^__([\s\S]+)__$/);
  if (bold) {
    data.fontWeight = "bold";
    text = bold[1].trim();
  }
  // Whole-node hyperlink.
  const link = text.match(/^\[([\s\S]+?)\]\(([^)]+)\)$/);
  if (link) {
    data.hyperlink = link[2].trim();
    text = link[1].trim();
  }
  data.text = text;
  return data;
}

export function markdownToTree(text) {
  const lines = String(text || "").split("\n");
  if (!lines.length) return null;
  const root = { data: { text: "" }, children: [] };
  const stack = [{ node: root, depth: -1 }];

  for (const line of lines) {
    const headingMatch = line.match(/^(#{1,6})\s+(.+)/);
    const listMatch = line.match(/^(\s*)([-*+]|\d+\.)\s+(.+)/);
    let depth = 0;
    let nodeText = "";
    if (headingMatch) {
      depth = headingMatch[1].length - 1;
      nodeText = headingMatch[2].trim();
    } else if (listMatch) {
      depth = Math.floor(listMatch[1].length / 2) + 1;
      nodeText = listMatch[3].trim();
    } else {
      continue;
    }

    if (!root.data.text && depth === 0) {
      Object.assign(root.data, markdownToNodeData(nodeText));
      continue;
    }

    const node = { data: markdownToNodeData(nodeText), children: [] };
    while (stack.length > 1 && stack[stack.length - 1].depth >= depth) stack.pop();
    stack[stack.length - 1].node.children.push(node);
    stack.push({ node, depth });
  }

  // Keep the tree when the root carries text, children, or (tag-only heading) tags —
  // gating on root text alone would drop a whole document under a tag-only heading.
  const hasContent = Boolean(root.data.text) || root.children.length > 0 || (Array.isArray(root.data.tag) && root.data.tag.length > 0);
  return hasContent ? root : null;
}

export function x6CellsToMarkdown(cells) {
  const tree = x6SnapshotToTree(cells);
  if (!tree) return "";

  const lines = [];
  const walk = (node, depth) => {
    const label = nodeTextToMarkdown(node?.data);
    if (!label) return;
    lines.push(depth === 0 ? `# ${label}` : `${"  ".repeat(depth - 1)}- ${label}`);
    (node.children || []).forEach((child) => walk(child, depth + 1));
  };

  walk(tree, 0);
  return `${lines.join("\n")}${lines.length ? "\n" : ""}`;
}
