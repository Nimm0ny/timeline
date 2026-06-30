<script setup>
import { onBeforeUnmount, onMounted, ref, shallowRef } from "vue";
import { countMindmapNodes, mindmapRootData } from "@/utils/timelineNotes.js";

// Thin Vue wrapper around simple-mind-map (the authorized mindmap dependency; see
// AGENTS.md §9). The library is framework-agnostic and DOM-driven, so we own only
// its lifecycle and a small imperative controller (exposed for the toolbar): init
// into a sized container on mount, persist the FULL snapshot on change (debounced)
// and on unmount, and tear it down. The heavy full-feature bundle is dynamically
// imported so it only loads when a mindmap note is actually opened.
const props = defineProps({
  // Id of the note this canvas is bound to. The parent keys the editor per note, so
  // this is stable for the instance's life; it rides the save event so a flush during
  // a note switch (or after close) writes to the right note, never the new one.
  noteId: { type: [Number, String], default: null },
  // Stored body_json: either a full snapshot ({ root, layout, theme, view }) or, for
  // notes seeded before the toolbar, the bare tree ({ data, children }). null → seed.
  tree: { type: [Object, Array, null], default: null },
  // Seeds the root node's text when there is no stored tree yet.
  title: { type: String, default: "" },
});

const emit = defineEmits(["update", "ready", "active"]);

const canvasRef = ref(null);
const mindMap = shallowRef(null);
const loading = ref(true);
let saveTimer = null;
let resizeObserver = null;
let resizeTimer = null;
let currentBackground = ""; // the one user-adjustable theme value; node colours come from tokens
// JSON of the last-persisted snapshot. Saves that don't change it (the programmatic
// data_change on init, a layout toggle that's then undone) are skipped — this keeps
// open-without-edit from writing and collapses redundant autosaves.
let savedJson = null;

function seedRoot() {
  return { data: { text: props.title?.trim() || "中心主题" }, children: [] };
}

function readVar(name, fallback) {
  if (typeof window === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

// Luminance test (hex or rgb/rgba) so node text + line colours adapt to the chosen
// canvas background — on a dark background, fixed dark text would be invisible.
function isDarkColor(color) {
  const s = String(color || "").trim();
  let r;
  let g;
  let b;
  const hex = s.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (hex) {
    let h = hex[1];
    if (h.length === 3) h = h.split("").map((ch) => ch + ch).join("");
    r = parseInt(h.slice(0, 2), 16);
    g = parseInt(h.slice(2, 4), 16);
    b = parseInt(h.slice(4, 6), 16);
  } else {
    const m = s.match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i);
    if (!m) return false;
    r = +m[1];
    g = +m[2];
    b = +m[3];
  }
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255 < 0.5;
}

// Map app CSS tokens onto a simple-mind-map theme so a map looks native (accent root,
// soft second level, plain leaves, app font) instead of the library's default green.
// Text/line/second-fill colours adapt to the effective background so any chosen
// background — including a dark one — keeps every node legible. Read live so it tracks
// the active token values.
function buildTokenTheme(background) {
  const accent = readVar("--accent", "#7b68d9");
  const accentSoft = readVar("--accent-soft", "rgba(123,104,217,0.12)");
  const appBg = readVar("--bg-surface", "#faf8f4");
  // No explicit pick → a transparent canvas so the map follows the app's light/dark
  // theme (the .mm-editor host paints --bg-surface). An explicit swatch pins that
  // colour. Either way, contrast is judged against what's actually visible.
  const explicit = background && background !== "transparent";
  const canvasBg = explicit ? background : "transparent";
  const effectiveBg = explicit ? background : appBg;
  const dark = isDarkColor(effectiveBg);
  const ink = dark ? "#ece9e3" : readVar("--text", "#3a3733");
  const inkStrong = dark ? "#ffffff" : readVar("--text-strong", "#2a2722");
  const line = dark ? "rgba(255,255,255,0.26)" : readVar("--border-strong", "#d8d4cc");
  const secondFill = dark ? "rgba(255,255,255,0.10)" : accentSoft;
  const fontFamily =
    (typeof document !== "undefined" && getComputedStyle(document.body).fontFamily) || "inherit";
  const font = { fontFamily };
  return {
    backgroundColor: canvasBg,
    lineColor: line,
    lineWidth: 2,
    root: { fillColor: accent, color: "#ffffff", borderColor: accent, borderWidth: 0, fontSize: 18, ...font },
    second: { fillColor: secondFill, color: inkStrong, borderColor: "transparent", fontSize: 15, ...font },
    node: { fillColor: "transparent", color: ink, borderColor: "transparent", fontSize: 14, ...font },
    generalization: { fillColor: secondFill, color: inkStrong, ...font },
  };
}

// Apply the token look for the given (or token-default) background in ONE
// setThemeConfig call — a separate { backgroundColor }-only call would drop the
// node-level token colours and revert nodes to the library default.
function applyTheme(background) {
  if (!mindMap.value) return;
  mindMap.value.setThemeConfig(buildTokenTheme(background));
}

function activeNodes() {
  return mindMap.value?.renderer?.activeNodeList || [];
}

function flushSave() {
  if (saveTimer) {
    clearTimeout(saveTimer);
    saveTimer = null;
  }
  const mm = mindMap.value;
  if (!mm) return;
  let snapshot;
  try {
    snapshot = mm.getData(true);
  } catch {
    return; // instance already destroyed — nothing to persist
  }
  const json = JSON.stringify(snapshot);
  if (json === savedJson) return; // unchanged since last persist — skip
  savedJson = json;
  emit("update", { id: props.noteId, tree: snapshot });
}

function scheduleSave() {
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = setTimeout(flushSave, 600);
}

function scheduleResize() {
  if (resizeTimer) clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => mindMap.value?.resize(), 80);
}

// --- Imperative controller (toolbar) --------------------------------------
function undo() {
  mindMap.value?.execCommand("BACK");
}
function redo() {
  mindMap.value?.execCommand("FORWARD");
}
function setLayout(name) {
  if (!mindMap.value || !name) return;
  mindMap.value.setLayout(name);
  scheduleSave();
}
function setBackground(color) {
  if (!mindMap.value) return;
  currentBackground = color;
  applyTheme(color);
  scheduleSave();
}
function nudgeFontSize(delta) {
  const nodes = activeNodes();
  if (!nodes.length) return 0;
  nodes.forEach((node) => {
    // Baseline matches buildTokenTheme's per-level sizes (root 18 / second 15 / leaf 14)
    // so the first nudge on an untouched node steps from its actual rendered size.
    const base = node.isRoot ? 18 : node.parent && node.parent.isRoot ? 15 : 14;
    const current = Number(node.getData("fontSize")) || base;
    const next = Math.min(48, Math.max(10, current + delta));
    mindMap.value.execCommand("SET_NODE_STYLE", node, "fontSize", next);
  });
  scheduleSave();
  return nodes.length;
}
function toggleBold() {
  const nodes = activeNodes();
  if (!nodes.length) return;
  nodes.forEach((node) => {
    const bold = node.getData("fontWeight") === "bold";
    mindMap.value.execCommand("SET_NODE_STYLE", node, "fontWeight", bold ? "normal" : "bold");
  });
  scheduleSave();
}
function setTextColor(color) {
  const nodes = activeNodes();
  if (!nodes.length) return;
  nodes.forEach((node) => mindMap.value.execCommand("SET_NODE_STYLE", node, "color", color));
  scheduleSave();
}

defineExpose({ undo, redo, setLayout, setBackground, nudgeFontSize, toggleBold, setTextColor });

onMounted(async () => {
  const { default: MindMap } = await import("simple-mind-map/full.js");
  // Guard against the component unmounting before the async import resolved.
  if (!canvasRef.value) return;

  const stored = props.tree;
  const rootData = mindmapRootData(stored) || seedRoot();
  const isSnapshot = !!(stored && typeof stored === "object" && stored.root);
  // Viewport culling only earns its overhead on large maps; small maps stay simple.
  const openPerformance = countMindmapNodes(rootData) > 60;

  mindMap.value = new MindMap({
    el: canvasRef.value,
    data: rootData,
    layout: (isSnapshot && stored.layout) || "logicalStructure",
    openPerformance,
    performanceConfig: { time: 200, padding: 120, removeNodeWhenOutCanvas: true },
  });

  // Node/line colours always come from the app tokens (applied every load), so they
  // stay consistent and never drift to the library's default green/teal. The only
  // theme-level value the toolbar changes is the background; per-node font/bold/colour
  // ride the node tree (node data), and layout/view restore separately. Re-derive the
  // token look each load and fold in just the saved background (single applyTheme call).
  currentBackground = (isSnapshot && stored.theme && stored.theme.config && stored.theme.config.backgroundColor) || "";
  applyTheme(currentBackground);
  if (isSnapshot && stored.view) {
    try {
      mindMap.value.view.setTransformData(stored.view);
    } catch {
      /* ignore an unusable saved view transform */
    }
  }

  // Baseline AFTER restore/theme so an open-without-edit doesn't autosave.
  try {
    savedJson = JSON.stringify(mindMap.value.getData(true));
  } catch {
    savedJson = null;
  }

  mindMap.value.on("data_change", scheduleSave);
  mindMap.value.on("node_active", (_node, activeList) => emit("active", (activeList || []).length));

  if (typeof ResizeObserver !== "undefined") {
    resizeObserver = new ResizeObserver(scheduleResize);
    resizeObserver.observe(canvasRef.value);
  }
  loading.value = false;
  let background = "";
  try {
    background = mindMap.value.getThemeConfig("backgroundColor") || "";
  } catch {
    background = "";
  }
  emit("ready", { layout: mindMap.value.getLayout?.() || "logicalStructure", background });
});

onBeforeUnmount(() => {
  if (resizeTimer) clearTimeout(resizeTimer);
  resizeObserver?.disconnect();
  resizeObserver = null;
  // Persist a pending edit before the canvas goes away (quick edit-then-close).
  flushSave();
  if (mindMap.value) {
    mindMap.value.destroy();
    mindMap.value = null;
  }
});
</script>

<template>
  <div class="mm-editor">
    <div ref="canvasRef" class="mm-canvas"></div>
    <div v-if="loading" class="mm-loading">正在加载思维导图…</div>
  </div>
</template>
