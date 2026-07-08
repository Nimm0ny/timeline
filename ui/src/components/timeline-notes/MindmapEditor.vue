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
  extractText,
  isX6MindmapSnapshot,
  makeEdge,
  markdownToTree,
  NODE_SIZES,
  normalizeEdgeStyle,
  normalizeNodeIcon,
  normalizeTags,
  relayout,
  resolveReparentTarget,
  sanitizeHyperlink,
  treeToX6Cells,
  X6_MINDMAP_FORMAT,
  x6CellsToMarkdown,
} from "@/utils/mindmapX6.js";
import { mindmapRootData } from "@/utils/timelineNotes.js";
import { readX6View, writeX6View } from "@/utils/x6ViewStore.js";
import { useThemeStore } from "@/composables/useTheme.js";

const props = defineProps({
  noteId: { type: [Number, String], default: null },
  tree: { type: [Object, Array, null], default: null },
  title: { type: String, default: "" },
  readOnly: { type: Boolean, default: false },
});

const emit = defineEmits(["update", "ready", "active", "search", "edit-meta", "meta"]);

const themeStore = useThemeStore();

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
let viewSaveTimer = null;
let savedJson = null;
let suppressSaves = false;
const sideControls = ref([]);
const collapseToggles = ref([]);
const searchHighlights = ref([]);
const nodeBadges = ref([]);

const NOTE_TIP_LIMIT = 140;

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
  updateCollapseToggles();
  updateSearchHighlights();
  updateNodeBadges();
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
  // On a side that already branches to children, push the add-child control clear
  // of the collapse toggle that straddles that border.
  const childSides = new Set(
    (g.getOutgoingEdges(node) || [])
      .filter((edge) => edge.getData()?._isMindEdge)
      .map((edge) => edge.getData()?.sourceSide || edge.getData()?.preferredSourceSide)
      .filter(Boolean)
  );
  const insetFor = (side) => (childSides.has(side) ? 34 : 12);
  sideControls.value = controlSides(node).map((side) => {
    const inset = insetFor(side);
    if (side === "top") return { key: `${node.id}:top`, nodeId: node.id, side, x: cx, y: rect.y - hostRect.top - inset };
    if (side === "bottom") return { key: `${node.id}:bottom`, nodeId: node.id, side, x: cx, y: rect.y - hostRect.top + rect.height + inset };
    if (side === "left") return { key: `${node.id}:left`, nodeId: node.id, side, x: rect.x - hostRect.left - inset, y: cy };
    return { key: `${node.id}:right`, nodeId: node.id, side, x: rect.x - hostRect.left + rect.width + inset, y: cy };
  });
}

// Persistent collapse/expand knob at each parent node's branch origin (the dominant
// child side). Shows a "−" when expanded; the hidden-child count when collapsed, so
// a folded branch is never invisible. Independent of hover (unlike the add controls).
function dominantChildSide(childEdges) {
  const tally = {};
  childEdges.forEach((edge) => {
    const side = edge.getData()?.sourceSide || edge.getData()?.preferredSourceSide;
    if (side) tally[side] = (tally[side] || 0) + 1;
  });
  let best = "";
  let bestCount = 0;
  for (const [side, count] of Object.entries(tally)) {
    if (count > bestCount) {
      best = side;
      bestCount = count;
    }
  }
  return best;
}

function updateCollapseToggles() {
  const g = graph.value;
  const host = editorRef.value;
  if (!g || !host || props.readOnly || editingNodeId) {
    collapseToggles.value = [];
    return;
  }
  const hostRect = host.getBoundingClientRect();
  const out = 11;
  const toggles = [];
  g.getNodes().forEach((node) => {
    if (!node.isNode?.() || !node.isVisible?.()) return;
    const childEdges = (g.getOutgoingEdges(node) || []).filter((edge) => edge.getData()?._isMindEdge);
    if (!childEdges.length) return;
    const data = node.getData() || {};
    const side = dominantChildSide(childEdges) || defaultChildSide(node);
    const position = node.getPosition();
    const size = node.getSize();
    const rect = g.localToPage({ x: position.x, y: position.y, width: size.width, height: size.height });
    const left = rect.x - hostRect.left;
    const top = rect.y - hostRect.top;
    let x = left + rect.width / 2;
    let y = top + rect.height / 2;
    if (side === "left") x = left - out;
    else if (side === "top") y = top - out;
    else if (side === "bottom") y = top + rect.height + out;
    else x = left + rect.width + out;
    toggles.push({ key: `c:${node.id}`, nodeId: node.id, x, y, collapsed: data.collapsed === true, count: childEdges.length });
  });
  collapseToggles.value = toggles;
}

// Per-node metadata badges (icon marker / hyperlink / note / tags) drawn as a DOM
// row under each visible node, using the same localToPage + host-relative mapping as
// the other overlays. The row container is pointer-transparent; only the link (opens
// the URL) and note (selects + edits) chips capture clicks, so gaps never block the
// canvas. Shown in read-only too, so a trashed map's links/notes stay reachable.
function updateNodeBadges() {
  const g = graph.value;
  const host = editorRef.value;
  if (!g || !host || editingNodeId) {
    if (nodeBadges.value.length) nodeBadges.value = [];
    return;
  }
  const hostRect = host.getBoundingClientRect();
  const badges = [];
  g.getNodes().forEach((node) => {
    if (!node.isNode?.() || !node.isVisible?.()) return;
    const data = node.getData() || {};
    const link = sanitizeHyperlink(data.hyperlink);
    const note = extractText(data.note || "");
    const tags = (Array.isArray(data.tag) ? data.tag : []).map((tag) => String(tag || "")).filter(Boolean);
    const icon = normalizeNodeIcon(data.icon);
    if (!link && !note && !tags.length && !icon) return;
    const position = node.getPosition();
    const size = node.getSize();
    const rect = g.localToPage({ x: position.x, y: position.y, width: size.width, height: size.height });
    badges.push({
      key: `b:${node.id}`,
      nodeId: node.id,
      x: rect.x - hostRect.left,
      y: rect.y - hostRect.top + rect.height + 4,
      icon,
      link,
      note: Boolean(note),
      noteTip: note.length > NOTE_TIP_LIMIT ? `${note.slice(0, NOTE_TIP_LIMIT)}…` : note,
      tags: tags.slice(0, 3),
      moreTags: Math.max(0, tags.length - 3),
    });
  });
  nodeBadges.value = badges;
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
        if (!edge.isVisible()) return;
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

// Content snapshot (cells + background + layout/edge styling). The viewport is
// deliberately NOT here — it rides localStorage (see currentView / x6ViewStore) so
// pan/zoom never bumps updated_at or fires a save. See notes-app-pivot-design.md §5.5.
function buildSnapshot() {
  const g = graph.value;
  if (!g) return null;
  return {
    _fmt: X6_MINDMAP_FORMAT,
    cells: g.toJSON().cells || [],
    background: currentBackground,
    layout: currentLayout,
    edgeRouting: currentEdgeRouting,
    edgeStyle: currentEdgeStyle,
  };
}

function currentView() {
  const g = graph.value;
  if (!g) return null;
  const { tx = 0, ty = 0 } = g.translate?.() || {};
  // X6's zoom getter is zoom(), not getZoom() (which doesn't exist on the Graph) — reading the
  // wrong name silently persisted zoom as 1, so a reload reset the mindmap zoom to 1.
  return { tx, ty, zoom: g.zoom?.() ?? 1 };
}

function flushViewSave() {
  if (viewSaveTimer) {
    clearTimeout(viewSaveTimer);
    viewSaveTimer = null;
  }
  if (props.readOnly || suppressSaves) return;
  writeX6View("mindmap", props.noteId, currentView());
}

// Pan/zoom → persist the viewport to localStorage only (no DB write, no updated_at).
function scheduleViewSave() {
  if (props.readOnly || suppressSaves) return;
  if (viewSaveTimer) clearTimeout(viewSaveTimer);
  viewSaveTimer = setTimeout(flushViewSave, 400);
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
  refreshSearch();
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

// Recompute node/edge visibility from the persisted `data.collapsed` flags: a node
// is hidden when ANY ancestor is collapsed (so nested folds compose correctly), and
// an edge is hidden when its child endpoint is hidden. History is suppressed so the
// visibility churn never lands on the undo stack. Idempotent — safe to call after any
// structural change or on load.
function applyCollapseVisibility() {
  const g = graph.value;
  if (!g) return;
  const nodes = g.getNodes().filter((node) => node.isNode?.());
  const edges = g.getEdges().filter((edge) => edge.getData()?._isMindEdge);
  const childrenOf = new Map();
  const hasParent = new Set();
  edges.forEach((edge) => {
    const source = edge.getSourceCell?.()?.id;
    const target = edge.getTargetCell?.()?.id;
    if (!source || !target) return;
    if (!childrenOf.has(source)) childrenOf.set(source, []);
    childrenOf.get(source).push(target);
    hasParent.add(target);
  });
  const hidden = new Set();
  const seen = new Set();
  const visit = (id, underCollapsed) => {
    if (seen.has(id)) return;
    seen.add(id);
    if (underCollapsed) hidden.add(id);
    const collapsed = g.getCellById(id)?.getData?.()?.collapsed === true;
    (childrenOf.get(id) || []).forEach((childId) => visit(childId, underCollapsed || collapsed));
  };
  nodes.filter((node) => !hasParent.has(node.id)).forEach((root) => visit(root.id, false));

  withHistorySuppressed(() => {
    g.startBatch("collapse-visibility");
    try {
      nodes.forEach((node) => {
        const hide = hidden.has(node.id);
        if (node.isVisible() === hide) node.setVisible(!hide);
      });
      edges.forEach((edge) => {
        const target = edge.getTargetCell?.()?.id;
        const hide = target ? hidden.has(target) : false;
        if (edge.isVisible() === hide) edge.setVisible(!hide);
      });
    } finally {
      g.stopBatch("collapse-visibility");
    }
  });
}

function toggleCollapse(nodeId) {
  const g = graph.value;
  if (!g || props.readOnly) return;
  const node = g.getCellById(nodeId);
  if (!node?.isNode?.()) return;
  const data = node.getData() || {};
  withHistorySuppressed(() => node.setData({ ...data, collapsed: !(data.collapsed === true) }));
  applyCollapseVisibility();
  refreshEdgeGeometry();
  scheduleSave();
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
  // Adding under a folded node auto-expands it so the new child is actually visible.
  const parentState = parent.getData() || {};
  if (parentState.collapsed) withHistorySuppressed(() => parent.setData({ ...parentState, collapsed: false }));
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
  applyCollapseVisibility();
  refreshEdgeGeometry();
  scheduleSave();
  refreshSearch();
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
  refreshSearch();
}

// Normalised snapshot of the live graph for reparent hit-testing: each node with its
// on-canvas box and its current parent (from the incoming mind edge).
function reparentNodeList() {
  const g = graph.value;
  if (!g) return [];
  const parentOf = new Map();
  g.getEdges().forEach((edge) => {
    if (!edge.getData()?._isMindEdge) return;
    const source = edge.getSourceCell?.()?.id;
    const target = edge.getTargetCell?.()?.id;
    if (source && target) parentOf.set(target, source);
  });
  return g
    .getNodes()
    .filter((node) => node.isNode?.())
    .map((node) => {
      const position = node.getPosition();
      const size = node.getSize();
      return { id: node.id, x: position.x, y: position.y, w: size.width, h: size.height, parentId: parentOf.get(node.id) || "" };
    });
}

// Rewire a dropped node under a new parent: drop its old incoming edge, add one from
// the target, re-level + re-size + recolor its whole subtree to the new depth, and
// reflow. The node keeps the position it was dropped at (free layout).
function reparentNode(movedId, targetId) {
  const g = graph.value;
  if (!g) return;
  const moved = g.getCellById(movedId);
  const target = g.getCellById(targetId);
  if (!moved?.isNode?.() || !target?.isNode?.()) return;
  const subtree = collectSubtreeNodes(moved);
  const newLevel = (target.getData()?.level ?? 0) + 1;
  const delta = newLevel - (moved.getData()?.level ?? newLevel);
  const sourceSide = defaultChildSide(target);
  const targetSide = sourceSide === "left" ? "right" : sourceSide === "right" ? "left" : sourceSide === "top" ? "bottom" : "top";

  g.startBatch("reparent");
  (g.getIncomingEdges(moved) || []).forEach((edge) => {
    if (edge.getData()?._isMindEdge) g.removeEdge(edge);
  });
  g.addEdge(makeEdge(targetId, movedId, readColors(currentBackground), { edgeStyle: currentEdgeStyle, sourceSide, targetSide }));
  subtree.forEach((node) => {
    const data = node.getData() || {};
    const level = Math.max(0, (data.level ?? 0) + delta);
    node.setData({ ...data, level });
    const size = sizeFor(level);
    node.resize(size.w, size.h);
  });
  g.stopBatch("reparent");

  applyColorsToGraph(g, readColors(currentBackground));
  currentLayout = FREE_LAYOUT_KEY;
  applyCollapseVisibility();
  refreshEdgeGeometry();
  graphSelection.value?.clean();
  graphSelection.value?.select(moved);
  scheduleSave();
  refreshSearch();
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

// ---- Node rich metadata (hyperlink / note / tags / icon) ----
// These target a SINGLE selected node (the toolbar gates the panel on exactly one
// selection). Values live in node.data and ride the snapshot on save; hyperlink/tag
// also round-trip to markdown, note/icon are JSON-snapshot-only by design.
function activeSingleNode() {
  const nodes = selectedNodes();
  return nodes.length === 1 && nodes[0]?.isNode?.() ? nodes[0] : null;
}

function getActiveNodeMeta() {
  const node = activeSingleNode();
  if (!node) return null;
  const data = node.getData() || {};
  return {
    id: node.id,
    text: extractText(data.text || ""),
    hyperlink: String(data.hyperlink || ""),
    note: String(data.note || ""),
    tags: Array.isArray(data.tag) ? data.tag.map((tag) => String(tag || "")).filter(Boolean) : [],
    icon: normalizeNodeIcon(data.icon),
  };
}

function updateActiveNodeData(patch) {
  const node = activeSingleNode();
  if (!node || props.readOnly) return false;
  node.setData({ ...(node.getData() || {}), ...patch });
  updateSideControls();
  scheduleSave();
  return true;
}

function setNodeHyperlink(url) {
  updateActiveNodeData({ hyperlink: sanitizeHyperlink(url) });
}

function setNodeNote(text) {
  updateActiveNodeData({ note: String(text || "") });
}

function setNodeTags(tags) {
  // Tags feed the search index (mindmapPlainText), so refresh an open find after a change.
  if (updateActiveNodeData({ tag: normalizeTags(tags) })) refreshSearch();
}

function setNodeIcon(icon) {
  updateActiveNodeData({ icon: normalizeNodeIcon(icon) });
}

// A node's note/link badge asks to edit: select that node, then let the surface open
// its 节点信息 panel (which reads getActiveNodeMeta of the now-selected node).
function requestEditMeta(nodeId) {
  const g = graph.value;
  const node = g?.getCellById(nodeId);
  if (!node?.isNode?.()) return;
  graphSelection.value?.clean();
  graphSelection.value?.select(node);
  if (props.readOnly) return;
  emit("edit-meta");
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
  applyCollapseVisibility();
  refreshEdgeGeometry();
  resizeGraph();

  // Prefer the per-device localStorage viewport; fall back to a legacy snapshot view
  // (maps saved before viewport moved to localStorage), else centerContent below.
  const stored = readX6View("mindmap", props.noteId);
  const view = stored || payload?.view;
  // Migrate a legacy snapshot viewport into localStorage on first open — else the next
  // content save (buildSnapshot no longer emits `view`) silently drops it and resets the view.
  if (!stored && payload?.view) writeX6View("mindmap", props.noteId, payload.view);
  if (view?.tx != null || view?.ty != null) {
    g.translate(view.tx || 0, view.ty || 0);
  }
  if (view?.zoom != null) {
    g.zoomTo(view.zoom);
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

// ---- Node search ----
// Text find across nodes: cycle matches top-to-bottom, centering + selecting each,
// auto-expanding any collapsed ancestors so a buried match becomes visible (reuses
// the collapse machinery). State is internal; the toolbar drives it and reads back
// { count, index } for its find bar.
let searchState = { query: "", matchIds: [], index: 0 };

// All-hits highlight overlay. Attr-based tinting would be clobbered by
// applyColorsToGraph (theme sync), so every match is drawn as a DOM box over the
// canvas using the same localToPage + host-relative mapping as the add/collapse
// controls. Recomputed via updateSideControls on pan/zoom/selection/drag; matches
// inside a still-collapsed branch are hidden (skipped), and the focused match gets
// `.current`. Positioned below the controls (z 8) so it never blocks interaction.
function updateSearchHighlights() {
  const g = graph.value;
  const host = editorRef.value;
  if (!g || !host || !searchState.matchIds.length) {
    if (searchHighlights.value.length) searchHighlights.value = [];
    return;
  }
  const hostRect = host.getBoundingClientRect();
  const boxes = [];
  searchState.matchIds.forEach((id, order) => {
    const node = g.getCellById(id);
    if (!node?.isNode?.() || !node.isVisible?.()) return;
    const position = node.getPosition();
    const size = node.getSize();
    const rect = g.localToPage({ x: position.x, y: position.y, width: size.width, height: size.height });
    boxes.push({
      key: `hl:${id}`,
      x: rect.x - hostRect.left,
      y: rect.y - hostRect.top,
      w: rect.width,
      h: rect.height,
      current: order === searchState.index,
    });
  });
  searchHighlights.value = boxes;
}

function expandAncestors(nodeId) {
  const g = graph.value;
  if (!g) return false;
  const parentOf = new Map();
  g.getEdges().forEach((edge) => {
    if (!edge.getData()?._isMindEdge) return;
    const source = edge.getSourceCell?.()?.id;
    const target = edge.getTargetCell?.()?.id;
    if (source && target) parentOf.set(target, source);
  });
  let changed = false;
  const seen = new Set();
  let cursor = parentOf.get(nodeId);
  while (cursor && !seen.has(cursor)) {
    seen.add(cursor);
    const node = g.getCellById(cursor);
    const data = node?.getData?.() || {};
    if (data.collapsed) {
      withHistorySuppressed(() => node.setData({ ...data, collapsed: false }));
      changed = true;
    }
    cursor = parentOf.get(cursor);
  }
  return changed;
}

function focusSearchMatch() {
  const g = graph.value;
  if (!g || !searchState.matchIds.length) return;
  const node = g.getCellById(searchState.matchIds[searchState.index]);
  if (!node?.isNode?.()) return;
  if (expandAncestors(node.id)) {
    applyCollapseVisibility();
    refreshEdgeGeometry();
    scheduleSave();
  }
  graphSelection.value?.clean();
  graphSelection.value?.select(node);
  try {
    g.centerCell(node);
  } catch {
    // Ignore centering failures (e.g. empty transform state).
  }
}

function computeSearchMatchIds() {
  const g = graph.value;
  if (!g || !searchState.query) return [];
  return g
    .getNodes()
    .filter((node) => node.isNode?.() && String(node.getData()?.text || "").toLowerCase().includes(searchState.query))
    .sort((a, b) => {
      const pa = a.getPosition();
      const pb = b.getPosition();
      return pa.y - pb.y || pa.x - pb.x;
    })
    .map((node) => node.id);
}

function searchNodes(query) {
  const q = String(query || "").trim().toLowerCase();
  searchState = { query: q, matchIds: [], index: 0 };
  if (q) {
    searchState.matchIds = computeSearchMatchIds();
    if (searchState.matchIds.length) focusSearchMatch();
  }
  updateSearchHighlights();
  return { count: searchState.matchIds.length, index: searchState.matchIds.length ? 1 : 0 };
}

// A text/structure edit can change what the active query matches. Recompute the
// match set (clamping the current index) and refresh the overlay + report the new
// count to the toolbar, WITHOUT re-centering — re-centering mid-edit would yank the
// canvas. No-op when no search is active.
function refreshSearch() {
  if (!searchState.query) return;
  searchState.matchIds = computeSearchMatchIds();
  if (searchState.index >= searchState.matchIds.length) {
    searchState.index = Math.max(0, searchState.matchIds.length - 1);
  }
  updateSearchHighlights();
  emit("search", { count: searchState.matchIds.length, index: searchState.matchIds.length ? searchState.index + 1 : 0 });
}

function stepMatch(direction) {
  const count = searchState.matchIds.length;
  if (!count) return { count: 0, index: 0 };
  searchState.index = (searchState.index + (direction < 0 ? -1 : 1) + count) % count;
  focusSearchMatch();
  updateSearchHighlights();
  return { count, index: searchState.index + 1 };
}

function clearSearch() {
  searchState = { query: "", matchIds: [], index: 0 };
  searchHighlights.value = [];
}

defineExpose({
  searchNodes,
  stepMatch,
  clearSearch,
  addChild,
  undo,
  redo,
  setLayout,
  setEdgeStyle,
  setBackground,
  nudgeFontSize,
  toggleBold,
  setTextColor,
  getActiveNodeMeta,
  setNodeHyperlink,
  setNodeNote,
  setNodeTags,
  setNodeIcon,
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

  g.on("node:moved", ({ node }) => {
    if (!applyingLayout) currentLayout = FREE_LAYOUT_KEY;
    // Dropped a node onto another? Rewire it as that node's child (guards in
    // resolveReparentTarget block root/self/descendant/current-parent).
    if (!applyingLayout && !props.readOnly && node?.isNode?.()) {
      const targetId = resolveReparentTarget(node.id, reparentNodeList());
      if (targetId) {
        reparentNode(node.id, targetId);
        return;
      }
    }
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
    // Report the single-node metadata target (or null) so the surface can keep its
    // node info panel bound to the node it opened for.
    emit("meta", getActiveNodeMeta());
    updateSideControls();
  });
  g.on("scale", () => {
    updateSideControls();
    scheduleViewSave();
  });
  g.on("translate", () => {
    updateSideControls();
    scheduleViewSave();
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

// Live theme sync: the app re-derives its token set (light/dark, accent, contrast)
// by reassigning the theme config; mirror that onto the canvas so node/edge colors
// follow a runtime theme switch instead of staying stale until the next reload.
// readColors() re-reads the fresh CSS vars; applyColorsToGraph preserves per-node
// custom colors (data.color) and only re-derives the theme-driven defaults.
watch(
  () => themeStore.config,
  () => {
    const g = graph.value;
    if (!g) return;
    applyColorsToGraph(g, readColors(currentBackground));
  }
);

onBeforeUnmount(() => {
  if (saveTimer) clearTimeout(saveTimer);
  if (resizeTimer) clearTimeout(resizeTimer);
  clearHoverClearTimer();
  resizeObserver?.disconnect();
  if (containerRef.value) containerRef.value.removeEventListener("keydown", onKeydown);
  cancelEdit();
  flushViewSave();
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
    <div
      v-for="hl in searchHighlights"
      :key="hl.key"
      class="mm-search-hl"
      :class="{ current: hl.current }"
      :style="{ left: `${hl.x}px`, top: `${hl.y}px`, width: `${hl.w}px`, height: `${hl.h}px` }"
      aria-hidden="true"
    ></div>
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
      <TimelineLucideIcon name="plusSign" :stroke-width="1.5" />
    </button>
    <button
      v-for="toggle in collapseToggles"
      :key="toggle.key"
      type="button"
      class="mm-node-collapse"
      :class="{ collapsed: toggle.collapsed }"
      :style="{ left: `${toggle.x}px`, top: `${toggle.y}px` }"
      :title="toggle.collapsed ? `展开分支（${toggle.count}）` : '折叠分支'"
      @mousedown.prevent
      @click.stop="toggleCollapse(toggle.nodeId)"
    >
      <span v-if="toggle.collapsed" class="mm-collapse-count">{{ toggle.count }}</span>
      <span v-else class="mm-collapse-glyph">−</span>
    </button>
    <div
      v-for="badge in nodeBadges"
      :key="badge.key"
      class="mm-node-badges"
      :style="{ left: `${badge.x}px`, top: `${badge.y}px` }"
    >
      <span v-if="badge.icon" class="mm-badge is-icon">
        <TimelineLucideIcon :name="badge.icon" :stroke-width="1.5" />
      </span>
      <a
        v-if="badge.link"
        class="mm-badge is-link"
        :href="badge.link"
        target="_blank"
        rel="noopener noreferrer"
        :title="badge.link"
        @mousedown.stop
        @click.stop
      >
        <TimelineLucideIcon name="link" :stroke-width="1.5" />
      </a>
      <button
        v-if="badge.note"
        type="button"
        class="mm-badge is-note"
        :title="badge.noteTip"
        @mousedown.stop
        @click.stop="requestEditMeta(badge.nodeId)"
      >
        <TimelineLucideIcon name="note" :stroke-width="1.5" />
      </button>
      <span v-for="(tag, index) in badge.tags" :key="`tag-${index}`" class="mm-badge-tag">#{{ tag }}</span>
      <span v-if="badge.moreTags" class="mm-badge-more">+{{ badge.moreTags }}</span>
    </div>
    <div v-if="loading" class="mm-loading">正在加载思维导图…</div>
  </div>
</template>
