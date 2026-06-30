// X6 mindmap helpers: snapshot compatibility, layout, markdown bridge, and
// graph-cell serialization. Kept separate so the Vue wrapper stays focused on
// lifecycle and editor interactions.

export const X6_MINDMAP_FORMAT = "x6-mindmap-v1";

export const NODE_SIZES = [
  { w: 128, h: 38 },
  { w: 108, h: 32 },
  { w: 92, h: 28 },
];

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

export function buildX6SeedSnapshot(text = "中心主题", options = {}) {
  const tree = { data: { text: extractText(text) || "中心主题" }, children: [] };
  const { cells } = treeToX6Cells(tree, { colors: options.colors, direction: options.direction || "LR" });
  return {
    _fmt: X6_MINDMAP_FORMAT,
    cells,
    background: options.background || "",
    layout: options.layout || "free",
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
      },
    });

    if (parentId) {
      cells.push(makeEdge(parentId, id, options.colors || {}));
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

export function makeEdge(sourceId, targetId, colors = {}) {
  return {
    shape: "edge",
    id: `e-${sourceId}-${targetId}`,
    source: { cell: sourceId },
    target: { cell: targetId },
    data: { _isMindEdge: true },
    attrs: {
      line: {
        stroke: colors.line || "#d8d4cc",
        strokeWidth: 1.5,
        targetMarker: null,
      },
    },
    router: { name: "er", args: { direction: "H" } },
    connector: { name: "smooth" },
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
  const span = (id) => {
    const node = nodeMap.get(id);
    if (!node) return 0;
    const kids = childIds.get(id) || [];
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
    const kids = childIds.get(id) || [];
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
  const span = (id) => {
    const node = nodeMap.get(id);
    if (!node) return 0;
    const kids = childIds.get(id) || [];
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
    const kids = childIds.get(id) || [];
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
      root.data.text = nodeText;
      continue;
    }

    const node = { data: { text: nodeText }, children: [] };
    while (stack.length > 1 && stack[stack.length - 1].depth >= depth) stack.pop();
    stack[stack.length - 1].node.children.push(node);
    stack.push({ node, depth });
  }

  return root.data.text ? root : null;
}

export function x6CellsToMarkdown(cells) {
  const tree = x6SnapshotToTree(cells);
  if (!tree) return "";

  const lines = [];
  const walk = (node, depth) => {
    const text = extractText(node?.data?.text || "");
    if (!text) return;
    lines.push(depth === 0 ? `# ${text}` : `${"  ".repeat(depth - 1)}- ${text}`);
    (node.children || []).forEach((child) => walk(child, depth + 1));
  };

  walk(tree, 0);
  return `${lines.join("\n")}${lines.length ? "\n" : ""}`;
}
