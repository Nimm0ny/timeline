<script setup>
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from "vue";
import { Graph } from "@antv/x6";
import { History } from "@antv/x6-plugin-history";
import { Selection } from "@antv/x6-plugin-selection";
import TimelineLucideIcon from "@/components/timeline-notes/TimelineLucideIcon.vue";
import {
  buildNodeAttrs,
  buildNodePorts,
  buildX6SeedSnapshot,
  computeMindmapRoute,
  DEFAULT_EDGE_ROUTING,
  DEFAULT_EDGE_STYLE,
  applyColorsToGraph,
  edgeConnectorForStyle,
  edgeRoutingForStyle,
  isX6MindmapSnapshot,
  makeEdge,
  markdownToTree,
  NODE_SIZES,
  normalizeEdgeStyle,
  relayout,
  treeToX6Cells,
  X6_MINDMAP_FORMAT,
  x6CellsToMarkdown,
} from "@/utils/mindmapX6.js";
import { mindmapRootData } from "@/utils/timelineNotes.js";

const props = defineProps({
  noteId: { type: [Number, String], default: null },
  tree: { type: [Object, Array, null], default: null },
  title: { type: String, default: "" },
  readOnly: { type: Boolean, default: false },
});

const emit = defineEmits(["update", "ready", "active"]);

const FREE_LAYOUT_KEY = "free";
const INTERACTING_OPTIONS = {
  nodeMovable: true,
  magnetConnectable: false,
  edgeMovable: false,
  edgeLabelMovable: false,
};

const editorRef = ref(null);
const containerRef = ref(null);
const editOverlayRef = ref(null);
const graph = shallowRef(null);
const graphHistory = shallowRef(null);
const graphSelection = shallowRef(null);
const loading = ref(true);

let applyingLayout = false;
let currentBackground = "";
let currentLayout = FREE_LAYOUT_KEY;
let currentEdgeStyle = DEFAULT_EDGE_STYLE;
let currentEdgeRouting = DEFAULT_EDGE_ROUTING;
let editingNodeId = "";
let hoveredNodeId = "";
let syncingEdges = false;
let hoverClearTimer = null;
let resizeObserver = null;
let resizeTimer = null;
let saveTimer = null;
let savedJson = null;
let suppressSaves = false;
const sideControls = ref([]);

function seedTitle() {
  return props.title?.trim() || "中心主题";
}

function sizeFor(level) {
  return NODE_SIZES[Math.min(level, NODE_SIZES.length - 1)];
}

function readVar(name, fallback) {
  if (typeof window === "undefined") return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

function isDarkColor(color) {
  const raw = String(color || "").trim();
  const hex = raw.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (hex) {
    let value = hex[1];
    if (value.length === 3) value = value.split("").map((ch) => ch + ch).join("");
    const r = Number.parseInt(value.slice(0, 2), 16);
    const g = Number.parseInt(value.slice(2, 4), 16);
    const b = Number.parseInt(value.slice(4, 6), 16);
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255 < 0.5;
  }
  const rgb = raw.match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i);
  if (!rgb) return false;
  const [r, g, b] = rgb.slice(1, 4).map((part) => Number(part));
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255 < 0.5;
}

function readColors(background) {
  const explicit = background && background !== "transparent";
  const dark = isDarkColor(explicit ? background : readVar("--bg-surface", "#faf8f4"));
  return {
    accent: readVar("--accent", "#7b68d9"),
    accentSoft: dark ? "rgba(255,255,255,0.10)" : readVar("--accent-soft", "rgba(123,104,217,0.12)"),
    text: dark ? "#ece9e3" : readVar("--text", "#3a3733"),
    textStrong: dark ? "#ffffff" : readVar("--text-strong", "#2a2722"),
    line: dark ? "rgba(255,255,255,0.26)" : readVar("--border-strong", "#d8d4cc"),
  };
}

function clearHoverClearTimer() {
  if (hoverClearTimer) {
    clearTimeout(hoverClearTimer);
    hoverClearTimer = null;
  }
}

function scheduleHoverClear(nodeId = "") {
  clearHoverClearTimer();
  hoverClearTimer = setTimeout(() => {
    if (!nodeId || hoveredNodeId === nodeId) {
      hoveredNodeId = "";
      updateSideControls();
    }
  }, 120);
}

function serializeNodeBox(node) {
  const position = node.getPosition();
  const size = node.getSize();
  return { id: node.id, x: position.x, y: position.y, width: size.width, height: size.height };
}

function ensureNodePorts(node) {
  if (!node?.isNode?.()) return;
  if ((node.getPorts?.() || []).length) return;
  node.prop("ports", buildNodePorts());
}

function withHistorySuppressed(action) {
  const history = graphHistory.value;
  if (!history) {
    action();
    return;
  }
  const enabled = history.isEnabled();
  if (enabled) history.disable();
  try {
    action();
  } finally {
    if (enabled) history.enable();
  }
}

function syncEdgeStyleFromGraph() {
  const g = graph.value;
  if (!g) return;
  const edge = g.getEdges().find((item) => item.getData()?._isMindEdge);
  const data = edge?.getData?.() || {};
  currentEdgeStyle = normalizeEdgeStyle(data.edgeStyle || currentEdgeStyle);
  currentEdgeRouting = edgeRoutingForStyle(currentEdgeStyle);
}

function currentControlNode() {
  const g = graph.value;
  if (!g) return null;
  if (hoveredNodeId) {
    const hovered = g.getCellById(hoveredNodeId);
    if (hovered?.isNode?.()) return hovered;
  }
  const selected = selectedNodes()[0];
  if (selected?.isNode?.()) return selected;
  return null;
}

function controlSides(node) {
  if (!node?.isNode?.()) return [];
  return ["top", "right", "bottom", "left"];
}

function updateSideControls() {
  const g = graph.value;
  const host = editorRef.value;
  if (!g || !host || props.readOnly || editingNodeId) {
    sideControls.value = [];
    return;
  }
  const node = currentControlNode();
  if (!node?.isNode?.()) {
    sideControls.value = [];
    return;
  }

  const position = node.getPosition();
  const size = node.getSize();
  const rect = g.localToPage({ x: position.x, y: position.y, width: size.width, height: size.height });
  const hostRect = host.getBoundingClientRect();
  const cx = rect.x - hostRect.left + rect.width / 2;
  const cy = rect.y - hostRect.top + rect.height / 2;
  const inset = 12;
  sideControls.value = controlSides(node).map((side) => {
    if (side === "top") return { key: `${node.id}:top`, nodeId: node.id, side, x: cx, y: rect.y - hostRect.top - inset };
    if (side === "bottom") return { key: `${node.id}:bottom`, nodeId: node.id, side, x: cx, y: rect.y - hostRect.top + rect.height + inset };
    if (side === "left") return { key: `${node.id}:left`, nodeId: node.id, side, x: rect.x - hostRect.left - inset, y: cy };
    return { key: `${node.id}:right`, nodeId: node.id, side, x: rect.x - hostRect.left + rect.width + inset, y: cy };
  });
}

function refreshEdgeGeometry() {
  const g = graph.value;
  if (!g || syncingEdges) return;
  const nodes = g.getNodes().filter((node) => node.isNode?.());
  nodes.forEach(ensureNodePorts);
  const nodeBoxes = nodes.map(serializeNodeBox);
  const occupied = [];
  const edges = g
    .getEdges()
    .filter((edge) => edge.getData()?._isMindEdge)
    .sort((left, right) => {
      const leftSource = left.getSourceCell();
      const rightSource = right.getSourceCell();
      const leftPos = leftSource?.getPosition?.()?.y ?? 0;
      const rightPos = rightSource?.getPosition?.()?.y ?? 0;
      return leftPos - rightPos || String(left.id).localeCompare(String(right.id));
    });

  syncingEdges = true;
  withHistorySuppressed(() => {
    g.startBatch("mindmap-edges");
    try {
      edges.forEach((edge) => {
        const sourceNode = edge.getSourceCell();
        const targetNode = edge.getTargetCell();
        if (!sourceNode?.isNode?.() || !targetNode?.isNode?.()) return;
        const data = edge.getData() || {};
        const route = computeMindmapRoute(serializeNodeBox(sourceNode), serializeNodeBox(targetNode), {
          edgeStyle: currentEdgeStyle,
          preferredSourceSide: data.preferredSourceSide,
          preferredTargetSide: data.preferredTargetSide,
          nodeBoxes,
          occupiedSegments: occupied,
        });
        edge.setSource({ cell: sourceNode.id, port: route.sourceSide });
        edge.setTarget({ cell: targetNode.id, port: route.targetSide });
        edge.setRouter({ name: "normal" });
        edge.setConnector(edgeConnectorForStyle(currentEdgeStyle));
        edge.setVertices(route.vertices);
        edge.setData({
          ...data,
          _isMindEdge: true,
          preferredSourceSide: data.preferredSourceSide || route.sourceSide,
          preferredTargetSide: data.preferredTargetSide || route.targetSide,
          sourceSide: route.sourceSide,
          targetSide: route.targetSide,
          edgeStyle: currentEdgeStyle,
          edgeRouting: currentEdgeRouting,
        });
        occupied.push(...route.segments);
      });
    } finally {
      g.stopBatch("mindmap-edges");
    }
  });
  syncingEdges = false;
  updateSideControls();
}

function normalizeLayoutKey(layout) {
  const key = String(layout || "").trim();
  if (key === "organizationStructure") return key;
  if (key === "logicalStructureLeft") return key;
  if (key === "logicalStructure") return key;
  if (key === FREE_LAYOUT_KEY) return key;
  if (key === "mindMap" || key === "catalogOrganization" || key === "fishbone") return "logicalStructure";
  return FREE_LAYOUT_KEY;
}

function directionFromLayout(layout) {
  if (layout === "logicalStructureLeft") return "RL";
  if (layout === "organizationStructure") return "TB";
  return "LR";
}

function selectedNodes() {
  return graphSelection.value?.getSelectedCells()?.filter((cell) => cell.isNode?.()) ?? [];
}

function resizeGraph() {
  const host = containerRef.value;
  const g = graph.value;
  if (!host || !g) return;
  g.resize(host.clientWidth, host.clientHeight);
}

function cancelEdit() {
  editingNodeId = "";
  if (editOverlayRef.value) editOverlayRef.value.style.display = "none";
  updateSideControls();
}

function buildSnapshot() {
  const g = graph.value;
  if (!g) return null;
  const { tx = 0, ty = 0 } = g.translate?.() || {};
  return {
    _fmt: X6_MINDMAP_FORMAT,
    cells: g.toJSON().cells || [],
    background: currentBackground,
    layout: currentLayout,
    edgeRouting: currentEdgeRouting,
    edgeStyle: currentEdgeStyle,
    view: {
      tx,
      ty,
      zoom: g.getZoom?.() ?? 1,
    },
  };
}

function setSavedBaseline() {
  const snapshot = buildSnapshot();
  savedJson = snapshot ? JSON.stringify(snapshot) : null;
}

function flushSave() {
  if (props.readOnly || suppressSaves) return;
  if (saveTimer) {
    clearTimeout(saveTimer);
    saveTimer = null;
  }
  const snapshot = buildSnapshot();
  if (!snapshot) return;
  const json = JSON.stringify(snapshot);
  if (json === savedJson) return;
  savedJson = json;
  emit("update", { id: props.noteId, tree: snapshot });
}

function scheduleSave() {
  if (props.readOnly || suppressSaves) return;
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = setTimeout(flushSave, 500);
}

function scheduleResize() {
  if (resizeTimer) clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    resizeGraph();
    updateSideControls();
  }, 80);
}

function downloadFile(filename, text, mimeType) {
  const blob = new Blob([text], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

function showEditOverlay(node) {
  const g = graph.value;
  const host = editorRef.value;
  const overlay = editOverlayRef.value;
  if (!g || !host || !overlay || props.readOnly) return;

  const position = node.getPosition();
  const size = node.getSize();
  const rect = g.localToPage({ x: position.x, y: position.y, width: size.width, height: size.height });
  const hostRect = host.getBoundingClientRect();
  const scale = size.width ? rect.width / size.width : 1;

  editingNodeId = node.id;
  sideControls.value = [];
  overlay.style.left = `${rect.x - hostRect.left}px`;
  overlay.style.top = `${rect.y - hostRect.top}px`;
  overlay.style.width = `${rect.width}px`;
  overlay.style.height = `${rect.height}px`;
  overlay.style.fontSize = `${(Number(node.attr("label/fontSize")) || 13) * scale}px`;
  overlay.style.lineHeight = `${Math.max(rect.height - 2, 18)}px`;
  overlay.style.display = "block";
  overlay.value = node.getData()?.text || "";
  overlay.focus();
  overlay.select();
}

function commitEdit() {
  const g = graph.value;
  const overlay = editOverlayRef.value;
  if (!g || !overlay || !editingNodeId) return;
  const node = g.getCellById(editingNodeId);
  if (node?.isNode?.()) {
    const previous = node.getData()?.text || "";
    const next = overlay.value.trim() || previous;
    node.attr("label/text", next);
    node.setData({ ...(node.getData() || {}), text: next });
    scheduleSave();
  }
  cancelEdit();
}

function childPosition(parentNode, childSize, side = "right") {
  const parentPos = parentNode.getPosition();
  const parentSize = parentNode.getSize();
  const siblingCount =
    graph.value?.getOutgoingEdges(parentNode)?.filter((edge) => (edge.getData()?.preferredSourceSide || "right") === side).length || 0;
  const verticalOffset = siblingCount * (childSize.h + 18);
  const horizontalOffset = siblingCount * (childSize.w + 18);
  if (side === "left") {
    return {
      x: parentPos.x - childSize.w - 80,
      y: parentPos.y + (parentSize.height - childSize.h) / 2 + verticalOffset,
    };
  }
  if (side === "top") {
    return {
      x: parentPos.x + (parentSize.width - childSize.w) / 2 + horizontalOffset,
      y: parentPos.y - childSize.h - 60,
    };
  }
  if (side === "bottom") {
    return {
      x: parentPos.x + (parentSize.width - childSize.w) / 2 + horizontalOffset,
      y: parentPos.y + parentSize.height + 60,
    };
  }
  return {
    x: parentPos.x + parentSize.width + 80,
    y: parentPos.y + (parentSize.height - childSize.h) / 2 + verticalOffset,
  };
}

function collectSubtreeNodes(rootNode) {
  const g = graph.value;
  if (!g || !rootNode?.isNode?.()) return [];
  const queue = [rootNode];
  const seen = new Set();
  const ordered = [];

  while (queue.length) {
    const node = queue.shift();
    if (!node || seen.has(node.id)) continue;
    seen.add(node.id);
    ordered.push(node);
    (g.getOutgoingEdges(node) || []).forEach((edge) => {
      const child = edge.getTargetCell();
      if (child?.isNode?.() && !seen.has(child.id)) queue.push(child);
    });
  }

  return ordered;
}

function defaultChildSide(parent) {
  if (currentLayout === "logicalStructureLeft") return "left";
  if (currentLayout === "organizationStructure") return "bottom";
  return "right";
}

function addChild(side = "", targetNodeId = "") {
  const g = graph.value;
  const explicit = targetNodeId ? g?.getCellById(targetNodeId) : null;
  const parent = explicit?.isNode?.() ? explicit : selectedNodes()[0];
  if (!g || !parent?.isNode?.() || props.readOnly) return;
  const sourceSide = side || defaultChildSide(parent);
  const parentData = parent.getData() || {};
  const childLevel = (parentData.level ?? 0) + 1;
  const childSize = sizeFor(childLevel);
  const childPos = childPosition(parent, childSize, sourceSide);
  const targetSide = sourceSide === "left" ? "right" : sourceSide === "right" ? "left" : sourceSide === "top" ? "bottom" : "top";
  const childId = `n-${Math.random().toString(36).slice(2, 9)}`;

  g.startBatch("add-node");
  const childNode = g.addNode({
    id: childId,
    shape: "rect",
    x: childPos.x,
    y: childPos.y,
    width: childSize.w,
    height: childSize.h,
    ports: buildNodePorts(),
    attrs: buildNodeAttrs(childLevel, "子主题", {}, readColors(currentBackground)),
    data: { text: "子主题", level: childLevel },
  });
  g.addEdge(makeEdge(parent.id, childId, readColors(currentBackground), { edgeStyle: currentEdgeStyle, sourceSide, targetSide }));
  g.stopBatch("add-node");

  graphSelection.value?.clean();
  graphSelection.value?.select(childNode);
  currentLayout = FREE_LAYOUT_KEY;
  currentEdgeRouting = edgeRoutingForStyle(currentEdgeStyle);
  refreshEdgeGeometry();
  scheduleSave();
  requestAnimationFrame(() => showEditOverlay(childNode));
}

function removeSelected() {
  const g = graph.value;
  const nodes = selectedNodes().filter((node) => (node.getData()?.level ?? 1) !== 0);
  if (!g || !nodes.length || props.readOnly) return;
  const subtree = [];
  const seen = new Set();

  nodes.forEach((node) => {
    collectSubtreeNodes(node).forEach((child) => {
      if (seen.has(child.id)) return;
      seen.add(child.id);
      subtree.push(child);
    });
  });

  g.startBatch("remove-node");
  subtree.forEach((node) => {
    g.getConnectedEdges(node).forEach((edge) => g.removeEdge(edge));
    g.removeNode(node);
  });
  g.stopBatch("remove-node");

  cancelEdit();
  emit("active", 0);
  currentLayout = FREE_LAYOUT_KEY;
  scheduleSave();
}

function undo() {
  graphHistory.value?.undo();
}

function redo() {
  graphHistory.value?.redo();
}

function setLayout(layoutKey) {
  const g = graph.value;
  const nextLayout = normalizeLayoutKey(layoutKey);
  if (!g) return;
  if (nextLayout === FREE_LAYOUT_KEY) {
    currentLayout = FREE_LAYOUT_KEY;
    refreshEdgeGeometry();
    scheduleSave();
    return;
  }

  applyingLayout = true;
  relayout(g, directionFromLayout(nextLayout));
  applyingLayout = false;
  currentLayout = nextLayout;
  refreshEdgeGeometry();
  try {
    g.centerContent();
  } catch {
    // Ignore fit failures on empty graphs.
  }
  scheduleSave();
}

function setEdgeStyle(style) {
  const g = graph.value;
  const nextStyle = normalizeEdgeStyle(style);
  if (!g || nextStyle === currentEdgeStyle) return;
  currentEdgeStyle = nextStyle;
  currentEdgeRouting = edgeRoutingForStyle(nextStyle);
  g.startBatch("mindmap-edge-style");
  try {
    g.getEdges()
      .filter((edge) => edge.getData()?._isMindEdge)
      .forEach((edge) => {
        const data = edge.getData() || {};
        edge.setData({
          ...data,
          _isMindEdge: true,
          edgeStyle: nextStyle,
          edgeRouting: currentEdgeRouting,
        });
      });
  } finally {
    g.stopBatch("mindmap-edge-style");
  }
  refreshEdgeGeometry();
  scheduleSave();
}

function setBackground(color) {
  const g = graph.value;
  if (!g) return;
  currentBackground = color || "";
  if (currentBackground) {
    g.drawBackground({ color: currentBackground });
  } else {
    g.clearBackground();
  }
  applyColorsToGraph(g, readColors(currentBackground));
  scheduleSave();
}

function nudgeFontSize(delta) {
  const nodes = selectedNodes();
  nodes.forEach((node) => {
    const data = node.getData() || {};
    const base = data.level === 0 ? 15 : data.level === 1 ? 13 : 12;
    const current = Number(data.fontSize || node.attr("label/fontSize") || base);
    const next = Math.min(48, Math.max(10, current + delta));
    node.attr("label/fontSize", next);
    node.setData({ ...data, fontSize: next });
  });
  if (nodes.length) scheduleSave();
  return nodes.length;
}

function toggleBold() {
  const nodes = selectedNodes();
  nodes.forEach((node) => {
    const data = node.getData() || {};
    const bold = data.fontWeight === "bold" || node.attr("label/fontWeight") === "bold" || node.attr("label/fontWeight") === 600;
    const next = bold ? "normal" : "bold";
    node.attr("label/fontWeight", next);
    node.setData({ ...data, fontWeight: next });
  });
  if (nodes.length) scheduleSave();
}

function setTextColor(color) {
  const nodes = selectedNodes();
  nodes.forEach((node) => {
    node.attr("label/fill", color);
    node.setData({ ...(node.getData() || {}), color });
  });
  if (nodes.length) scheduleSave();
}

function cancelPendingSave() {
  suppressSaves = true;
  if (saveTimer) {
    clearTimeout(saveTimer);
    saveTimer = null;
  }
}

function resumeSaves() {
  suppressSaves = Boolean(props.readOnly);
}

function flushPendingSave() {
  if (!props.readOnly) flushSave();
}

function applyGraphState(payload, persist) {
  const g = graph.value;
  if (!g) return false;
  const cells = Array.isArray(payload?.cells) ? payload.cells : [];

  cancelEdit();
  suppressSaves = true;
  graphSelection.value?.clean();
  try {
    g.zoomTo(1);
    g.translate(0, 0);
  } catch {
    // Ignore transform reset errors while rehydrating.
  }
  g.clearCells();
  if (cells.length) g.fromJSON({ cells });

  currentBackground = payload?.background || "";
  currentLayout = normalizeLayoutKey(payload?.layout);
  currentEdgeStyle = normalizeEdgeStyle(payload?.edgeStyle);
  currentEdgeRouting = String(payload?.edgeRouting || edgeRoutingForStyle(currentEdgeStyle));

  if (currentBackground) g.drawBackground({ color: currentBackground });
  else g.clearBackground();
  applyColorsToGraph(g, readColors(currentBackground));
  g.getNodes().forEach(ensureNodePorts);
  refreshEdgeGeometry();
  resizeGraph();

  if (payload?.view?.tx != null || payload?.view?.ty != null) {
    g.translate(payload.view?.tx || 0, payload.view?.ty || 0);
  }
  if (payload?.view?.zoom != null) {
    g.zoomTo(payload.view.zoom);
  } else if (cells.length) {
    try {
      g.centerContent();
    } catch {
      // Ignore center failures when the graph has no content box yet.
    }
  }

  graphHistory.value?.clean?.();
  suppressSaves = Boolean(props.readOnly);
  emit("active", 0);

  if (persist) {
    savedJson = null;
    flushSave();
  } else {
    setSavedBaseline();
  }
  updateSideControls();
  return true;
}

function payloadFromStoredTree(stored) {
  if (isX6MindmapSnapshot(stored)) {
    return {
      cells: stored.cells || [],
      background: stored.background || "",
      layout: normalizeLayoutKey(stored.layout),
      edgeRouting: stored.edgeRouting || DEFAULT_EDGE_ROUTING,
      edgeStyle: stored.edgeStyle || DEFAULT_EDGE_STYLE,
      view: stored.view || null,
    };
  }

  if (stored && Array.isArray(stored.cells)) {
    return {
      cells: stored.cells,
      background: stored.background || "",
      layout: normalizeLayoutKey(stored.layout),
      edgeRouting: stored.edgeRouting || DEFAULT_EDGE_ROUTING,
      edgeStyle: stored.edgeStyle || DEFAULT_EDGE_STYLE,
      view: stored.view || null,
    };
  }

  if (stored && (stored.root || stored.data)) {
    const legacyLayout = normalizeLayoutKey(stored.layout || "logicalStructure");
    const background = stored?.theme?.config?.backgroundColor || "";
    const { cells } = treeToX6Cells(mindmapRootData(stored) || { data: { text: seedTitle() }, children: [] }, {
      colors: readColors(background),
      direction: directionFromLayout(legacyLayout),
      edgeStyle: DEFAULT_EDGE_STYLE,
    });
    return {
      cells,
      background,
      layout: legacyLayout,
      edgeRouting: DEFAULT_EDGE_ROUTING,
      edgeStyle: DEFAULT_EDGE_STYLE,
      view: null,
    };
  }

  const seeded = buildX6SeedSnapshot(seedTitle(), {
    colors: readColors(),
    layout: FREE_LAYOUT_KEY,
    edgeStyle: DEFAULT_EDGE_STYLE,
  });
  return {
    cells: seeded.cells,
    background: seeded.background,
    layout: normalizeLayoutKey(seeded.layout),
    edgeRouting: seeded.edgeRouting,
    edgeStyle: seeded.edgeStyle,
    view: seeded.view,
  };
}

async function importMarkdown(text) {
  const tree = markdownToTree(String(text || ""));
  if (!tree) return false;
  const { cells } = treeToX6Cells(tree, {
    colors: readColors(currentBackground),
    direction: "LR",
    edgeStyle: currentEdgeStyle,
  });
  return applyGraphState(
    {
      cells,
      background: currentBackground,
      layout: "logicalStructure",
      edgeRouting: edgeRoutingForStyle(currentEdgeStyle),
      edgeStyle: currentEdgeStyle,
      view: null,
    },
    true
  );
}

async function importSnapshot(text) {
  const parsed = JSON.parse(String(text || ""));
  const payload = payloadFromStoredTree(parsed);
  if (!payload?.cells) throw new Error("不是可识别的导图 JSON");
  return applyGraphState(payload, true);
}

async function exportFile(type, name) {
  const snapshot = buildSnapshot();
  if (!snapshot || !type) return null;
  if (type === "json") {
    downloadFile(`${name || "思维导图"}.json`, `${JSON.stringify(snapshot, null, 2)}\n`, "application/json;charset=utf-8");
    return true;
  }
  if (type === "md" || type === "markdown") {
    downloadFile(`${name || "思维导图"}.md`, x6CellsToMarkdown(snapshot.cells), "text/markdown;charset=utf-8");
    return true;
  }
  return null;
}

defineExpose({
  addChild,
  undo,
  redo,
  setLayout,
  setEdgeStyle,
  setBackground,
  nudgeFontSize,
  toggleBold,
  setTextColor,
  importMarkdown,
  importSnapshot,
  exportFile,
  cancelPendingSave,
  resumeSaves,
  flushPendingSave,
});

function onKeydown(event) {
  if (!graph.value || props.readOnly || editingNodeId) return;
  if (event.key === "Tab") {
    event.preventDefault();
    addChild();
    return;
  }
  if (event.key === "Delete" || event.key === "Backspace") {
    event.preventDefault();
    removeSelected();
    return;
  }
  if (event.key === "Escape") {
    graphSelection.value?.clean();
    cancelEdit();
  }
}

onMounted(() => {
  if (!containerRef.value) return;

  const g = new Graph({
    container: containerRef.value,
    background: { color: "transparent" },
    panning: { enabled: true },
    mousewheel: {
      enabled: true,
      modifiers: "ctrl",
      factor: 1.1,
      minScale: 0.3,
      maxScale: 3,
    },
    interacting: props.readOnly ? false : INTERACTING_OPTIONS,
    grid: false,
    autoResize: false,
    connecting: { enabled: false },
  });

  const history = new History({ stackSize: 100 });
  const selection = new Selection({
    enabled: true,
    multiple: true,
    rubberband: false,
    movable: !props.readOnly,
    showNodeSelectionBox: true,
  });

  g.use(history);
  g.use(selection);

  graph.value = g;
  graphHistory.value = history;
  graphSelection.value = selection;

  containerRef.value.tabIndex = 0;
  containerRef.value.addEventListener("keydown", onKeydown);

  applyGraphState(payloadFromStoredTree(props.tree), false);
  resizeGraph();

  g.on("node:moved", () => {
    if (!applyingLayout) currentLayout = FREE_LAYOUT_KEY;
    refreshEdgeGeometry();
    scheduleSave();
  });
  g.on("history:change", () => {
    if (syncingEdges) return;
    syncEdgeStyleFromGraph();
    refreshEdgeGeometry();
    scheduleSave();
  });
  g.on("selection:changed", ({ selected }) => {
    emit("active", (selected || []).filter((cell) => cell.isNode?.()).length);
    updateSideControls();
  });
  g.on("scale", () => {
    updateSideControls();
    scheduleSave();
  });
  g.on("translate", () => {
    updateSideControls();
    scheduleSave();
  });
  g.on("node:dblclick", ({ node }) => showEditOverlay(node));
  g.on("node:mouseenter", ({ node }) => {
    clearHoverClearTimer();
    hoveredNodeId = node?.id || "";
    updateSideControls();
  });
  g.on("node:mouseleave", ({ node }) => {
    scheduleHoverClear(node?.id || "");
  });
  g.on("blank:click", () => {
    if (editingNodeId) commitEdit();
    else {
      clearHoverClearTimer();
      hoveredNodeId = "";
      cancelEdit();
    }
  });

  if (typeof ResizeObserver !== "undefined") {
    resizeObserver = new ResizeObserver(scheduleResize);
    resizeObserver.observe(containerRef.value);
  }

  loading.value = false;
  emit("ready", { layout: currentLayout, background: currentBackground, edgeStyle: currentEdgeStyle, edgeRouting: currentEdgeRouting });
});

watch(
  () => props.readOnly,
  (readOnly) => {
    const g = graph.value;
    if (!g) return;
    suppressSaves = readOnly;
    g.options.interacting = readOnly ? false : INTERACTING_OPTIONS;
    if (readOnly) graphSelection.value?.clean();
    updateSideControls();
  }
);

onBeforeUnmount(() => {
  if (saveTimer) clearTimeout(saveTimer);
  if (resizeTimer) clearTimeout(resizeTimer);
  clearHoverClearTimer();
  resizeObserver?.disconnect();
  if (containerRef.value) containerRef.value.removeEventListener("keydown", onKeydown);
  cancelEdit();
  flushSave();
  graph.value?.dispose();
  graph.value = null;
  graphHistory.value = null;
  graphSelection.value = null;
});
</script>

<template>
  <div ref="editorRef" class="mm-editor">
    <div ref="containerRef" class="mm-canvas"></div>
    <textarea
      ref="editOverlayRef"
      class="mm-edit-overlay"
      rows="1"
      spellcheck="false"
      @keydown.enter.exact.prevent="commitEdit"
      @keydown.escape.prevent="cancelEdit"
      @blur="commitEdit"
    />
    <button
      v-for="control in sideControls"
      :key="control.key"
      type="button"
      class="mm-node-plus"
      :style="{ left: `${control.x}px`, top: `${control.y}px` }"
      :title="`从${control.side}侧新增子节点`"
      @mouseenter="clearHoverClearTimer(); hoveredNodeId = control.nodeId; updateSideControls()"
      @mouseleave="scheduleHoverClear(control.nodeId)"
      @mousedown.prevent
      @click.stop="addChild(control.side, control.nodeId)"
    >
      <TimelineLucideIcon name="plusSign" :stroke-width="1.8" />
    </button>
    <div v-if="loading" class="mm-loading">正在加载思维导图…</div>
  </div>
</template>
