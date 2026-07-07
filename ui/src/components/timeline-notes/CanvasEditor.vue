<script setup>
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from "vue";
import { Graph } from "@antv/x6";
import { History } from "@antv/x6-plugin-history";
import { Selection } from "@antv/x6-plugin-selection";
import {
  applyCanvasColors,
  buildCanvasSeedSnapshot,
  buildCardNode,
  buildCardPorts,
  CARD_DEFAULT_HEIGHT,
  CARD_DEFAULT_WIDTH,
  isX6CanvasSnapshot,
  makeCanvasEdge,
  X6_CANVAS_FORMAT,
} from "@/utils/canvasX6.js";
import { useThemeStore } from "@/composables/useTheme.js";

// A free-form board (Obsidian-canvas style): the page owns persistence (@update) and
// which note is open; this component owns the X6 graph — free cards, hand-drawn
// connectors, pan/zoom. Deliberately far simpler than MindmapEditor: no tree, no
// auto-layout, no reparent. The surface drives it through the exposed controller.
const props = defineProps({
  noteId: { type: [Number, String], default: null },
  tree: { type: [Object, Array, null], default: null },
  title: { type: String, default: "" },
  readOnly: { type: Boolean, default: false },
});
const emit = defineEmits(["update", "ready", "active"]);

const themeStore = useThemeStore();

const editorRef = ref(null);
const containerRef = ref(null);
const editOverlayRef = ref(null);
const graph = shallowRef(null);
const graphHistory = shallowRef(null);
const graphSelection = shallowRef(null);
const loading = ref(true);

let currentBackground = "";
let editingNodeId = "";
let resizeObserver = null;
let resizeTimer = null;
let saveTimer = null;
let savedJson = null;
let suppressSaves = false;

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
  return false;
}

// Raw hex palette (the snapshot stores concrete colors, not CSS vars) derived from the
// live theme, so the board follows light/dark and a custom canvas background.
function readColors(background) {
  const explicit = background && background !== "transparent";
  const dark = isDarkColor(explicit ? background : readVar("--bg-surface", "#faf8f4"));
  return {
    accent: readVar("--accent", "#7b68d9"),
    text: dark ? "#ece9e3" : readVar("--text", "#3a3733"),
    line: dark ? "rgba(255,255,255,0.24)" : readVar("--border-strong", "#d8d4cc"),
    card: dark ? "#332f28" : "#ffffff",
  };
}

function selectedNodes() {
  return graphSelection.value?.getSelectedCells?.()?.filter((cell) => cell.isNode?.()) ?? [];
}

function resizeGraph() {
  const host = containerRef.value;
  const g = graph.value;
  if (!host || !g) return;
  g.resize(host.clientWidth, host.clientHeight);
}

function scheduleResize() {
  if (resizeTimer) clearTimeout(resizeTimer);
  resizeTimer = setTimeout(resizeGraph, 80);
}

function ensureCardPorts(node) {
  if (node?.getPorts && node.getPorts().length === 0) node.prop("ports", buildCardPorts());
}

function buildSnapshot() {
  const g = graph.value;
  if (!g) return null;
  const { tx = 0, ty = 0 } = g.translate?.() || {};
  return {
    _fmt: X6_CANVAS_FORMAT,
    cells: g.toJSON().cells || [],
    background: currentBackground,
    view: { tx, ty, zoom: g.getZoom?.() ?? 1 },
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

// ---- Card text editing (overlay a textarea over the card, commit on blur/enter) ----
function cancelEdit() {
  editingNodeId = "";
  if (editOverlayRef.value) editOverlayRef.value.style.display = "none";
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
  overlay.style.left = `${rect.x - hostRect.left}px`;
  overlay.style.top = `${rect.y - hostRect.top}px`;
  overlay.style.width = `${rect.width}px`;
  overlay.style.height = `${rect.height}px`;
  overlay.style.fontSize = `${(Number(node.attr("label/fontSize")) || 13) * scale}px`;
  overlay.style.lineHeight = "1.4";
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

// ---- Controller (driven by CanvasSurface toolbar) ----
function addCard(x, y) {
  const g = graph.value;
  if (!g || props.readOnly) return;
  const node = g.addNode(
    buildCardNode({
      x: x - CARD_DEFAULT_WIDTH / 2,
      y: y - CARD_DEFAULT_HEIGHT / 2,
      text: "新卡片",
      colors: readColors(currentBackground),
    })
  );
  graphSelection.value?.clean();
  graphSelection.value?.select(node);
  scheduleSave();
  requestAnimationFrame(() => showEditOverlay(node));
}

function addCardAtCenter() {
  const g = graph.value;
  const host = containerRef.value;
  if (!g || !host) return;
  const rect = host.getBoundingClientRect();
  const local = g.pageToLocal(rect.left + rect.width / 2, rect.top + rect.height / 2);
  addCard(local.x, local.y);
}

function deleteSelected() {
  const g = graph.value;
  const cells = graphSelection.value?.getSelectedCells?.() || [];
  if (!g || !cells.length || props.readOnly) return;
  g.startBatch("cv-remove");
  cells.forEach((cell) => {
    if (cell.isNode?.()) g.getConnectedEdges(cell).forEach((edge) => g.removeEdge(edge));
    g.removeCell(cell);
  });
  g.stopBatch("cv-remove");
  cancelEdit();
  emit("active", 0);
  scheduleSave();
}

function undo() {
  if (graphHistory.value?.canUndo()) graphHistory.value.undo();
}
function redo() {
  if (graphHistory.value?.canRedo()) graphHistory.value.redo();
}

function setBackground(value) {
  const g = graph.value;
  if (!g) return;
  currentBackground = value || "";
  if (currentBackground) g.drawBackground({ color: currentBackground });
  else g.clearBackground();
  applyCanvasColors(g, readColors(currentBackground));
  scheduleSave();
}

function setTextColor(color) {
  const nodes = selectedNodes();
  if (!nodes.length || props.readOnly) return;
  nodes.forEach((node) => {
    node.attr("label/fill", color);
    node.setData({ ...(node.getData() || {}), color });
  });
  scheduleSave();
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

defineExpose({
  addCard: addCardAtCenter,
  deleteSelected,
  undo,
  redo,
  setBackground,
  setTextColor,
  cancelPendingSave,
  resumeSaves,
  flushPendingSave,
});

function payloadFromStoredCanvas(stored) {
  if (isX6CanvasSnapshot(stored) || (stored && Array.isArray(stored.cells))) {
    return { cells: stored.cells || [], background: stored.background || "", view: stored.view || null };
  }
  const seeded = buildCanvasSeedSnapshot(readColors());
  return { cells: seeded.cells, background: seeded.background, view: seeded.view };
}

function applyGraphState(payload) {
  const g = graph.value;
  if (!g) return;
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
  if (currentBackground) g.drawBackground({ color: currentBackground });
  else g.clearBackground();
  applyCanvasColors(g, readColors(currentBackground));
  g.getNodes().forEach(ensureCardPorts);
  resizeGraph();
  const view = payload?.view;
  if (view?.tx != null || view?.ty != null) g.translate(view.tx || 0, view.ty || 0);
  if (view?.zoom != null) g.zoomTo(view.zoom);
  else if (cells.length) {
    try {
      g.centerContent();
    } catch {
      // No content box yet — nothing to center.
    }
  }
  graphHistory.value?.clean?.();
  suppressSaves = Boolean(props.readOnly);
  emit("active", 0);
  setSavedBaseline();
}

function onKeydown(event) {
  if (!graph.value || props.readOnly || editingNodeId) return;
  if (event.key === "Delete" || event.key === "Backspace") {
    event.preventDefault();
    deleteSelected();
  } else if (event.key === "Escape") {
    graphSelection.value?.clean();
    cancelEdit();
  }
}

onMounted(() => {
  if (!containerRef.value) return;
  const g = new Graph({
    container: containerRef.value,
    background: { color: "transparent" },
    // Left-drag on blank pans (matching the mindmap's proven config); ctrl+wheel zooms.
    panning: { enabled: true },
    mousewheel: { enabled: true, modifiers: "ctrl", factor: 1.1, minScale: 0.3, maxScale: 3 },
    interacting: props.readOnly
      ? false
      : { nodeMovable: true, magnetConnectable: true, edgeMovable: false, edgeLabelMovable: false },
    grid: false,
    autoResize: false,
    connecting: {
      enabled: !props.readOnly,
      snap: { radius: 24 },
      allowBlank: false,
      allowLoop: false,
      allowMulti: false,
      allowNode: false,
      allowEdge: false,
      highlight: true,
      router: { name: "normal" },
      connector: { name: "rounded", args: { radius: 12 } },
      createEdge() {
        return this.createEdge(makeCanvasEdge(readColors(currentBackground)));
      },
      validateConnection({ sourceCell, targetCell }) {
        if (!sourceCell || !targetCell || sourceCell.id === targetCell.id) return false;
        const dup = this.getEdges().some((edge) => {
          const s = edge.getSourceCellId?.();
          const t = edge.getTargetCellId?.();
          return (s === sourceCell.id && t === targetCell.id) || (s === targetCell.id && t === sourceCell.id);
        });
        return !dup;
      },
    },
  });

  const history = new History({ stackSize: 100 });
  // rubberband stays OFF: it and left-drag panning both fire on a blank mousedown, so
  // enabling it would pan and box-select at the same time. Multi-select via shift-click.
  const selection = new Selection({ enabled: true, multiple: true, rubberband: false, movable: !props.readOnly, showNodeSelectionBox: true });
  g.use(history);
  g.use(selection);

  graph.value = g;
  graphHistory.value = history;
  graphSelection.value = selection;

  containerRef.value.tabIndex = 0;
  containerRef.value.addEventListener("keydown", onKeydown);

  applyGraphState(payloadFromStoredCanvas(props.tree));
  resizeGraph();

  g.on("node:moved", () => scheduleSave());
  g.on("history:change", () => scheduleSave());
  // Count all selected cells (nodes AND edges) so the delete button enables for a lone
  // connector too; setTextColor is a no-op on edges, so an edge-only selection is safe.
  g.on("selection:changed", ({ selected }) => {
    emit("active", (selected || []).length);
  });
  g.on("scale", () => scheduleSave());
  g.on("translate", () => scheduleSave());
  g.on("node:dblclick", ({ node }) => showEditOverlay(node));
  g.on("blank:dblclick", ({ x, y }) => addCard(x, y));
  g.on("blank:click", () => {
    if (editingNodeId) commitEdit();
  });
  g.on("edge:connected", ({ edge, isNew }) => {
    if (!isNew) return;
    edge.setData({ _isCanvasEdge: true });
    edge.attr("line/stroke", readColors(currentBackground).line);
    scheduleSave();
  });

  if (typeof ResizeObserver !== "undefined") {
    resizeObserver = new ResizeObserver(scheduleResize);
    resizeObserver.observe(containerRef.value);
  }

  loading.value = false;
  emit("ready", { background: currentBackground });
});

watch(
  () => props.readOnly,
  (readOnly) => {
    const g = graph.value;
    if (!g) return;
    suppressSaves = readOnly;
    g.options.interacting = readOnly ? false : { nodeMovable: true, magnetConnectable: true, edgeMovable: false, edgeLabelMovable: false };
    if (g.options.connecting) g.options.connecting.enabled = !readOnly;
    if (readOnly) graphSelection.value?.clean();
  }
);

// Live theme sync — mirror a runtime light/dark/contrast switch onto the board,
// preserving per-card overrides (see applyCanvasColors).
watch(
  () => themeStore.config,
  () => {
    const g = graph.value;
    if (g) applyCanvasColors(g, readColors(currentBackground));
  }
);

onBeforeUnmount(() => {
  if (saveTimer) clearTimeout(saveTimer);
  if (resizeTimer) clearTimeout(resizeTimer);
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
    <div ref="containerRef" class="mm-canvas cv-canvas"></div>
    <textarea
      ref="editOverlayRef"
      class="mm-edit-overlay"
      rows="1"
      spellcheck="false"
      @keydown.enter.exact.prevent="commitEdit"
      @keydown.escape.prevent="cancelEdit"
      @blur="commitEdit"
    />
    <div v-if="loading" class="mm-loading">正在加载画布…</div>
  </div>
</template>
