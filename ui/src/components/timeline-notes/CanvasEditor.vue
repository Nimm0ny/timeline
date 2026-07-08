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
  buildEmbedCardNode,
  CARD_DEFAULT_HEIGHT,
  CARD_DEFAULT_WIDTH,
  computeEmbedTier,
  EMBED_DEFAULT_HEIGHT,
  EMBED_DEFAULT_WIDTH,
  EMBED_TIER,
  embedNoteIdsFromSnapshot,
  isEmbedCard,
  isX6CanvasSnapshot,
  makeCanvasEdge,
  X6_CANVAS_FORMAT,
} from "@/utils/canvasX6.js";
import { EmbedTeleport } from "@/utils/embedCardShape.js";
import { getEmbedEntry, resolveEmbedPreviews } from "@/utils/embedPreviewStore.js";
import { clearCardTiers, setCardTiers } from "@/utils/canvasTierStore.js";
import { clearEmbedDetails, getEmbedDetailHtml, setEmbedDetail } from "@/utils/embedDetailStore.js";
import { renderCachedMarkdownToHtml } from "@/utils/markdownPreview.js";
import { readX6View, writeX6View } from "@/utils/x6ViewStore.js";
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
  // Resolve one embedded note's full detail ({ bodyMarkdown, updatedAt, ... }) for the T2 tier.
  // Threaded from TimelinePage = (id) => notesStore.ensureNoteDetail(id) so canvas full-text
  // rides the app's shared LRU-40 detail cache (§7.4/§7.8). Absent → T2 stays at preview.
  resolveDetail: { type: Function, default: null },
});
const emit = defineEmits(["update", "ready", "active", "open-embed"]);

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
let viewSaveTimer = null;
let tierTimer = null;
let savedJson = null;
let suppressSaves = false;

// T2 full-markdown concurrency budget (§7.3 backstop): at most this many embed cards render the
// note's full markdown at once; extra on-screen-large cards stay at preview until they pan nearer
// the viewport center. The 360px full threshold means few cards qualify at once, so it rarely bites.
const EMBED_FULL_BUDGET = 24;
// note ids already attempted for T2 detail this board (in-flight or done) — each is fetched at
// most once per canvas session, so a re-settle never re-fetches and a failure isn't retry-stormed.
const fullTried = new Set();

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
  scheduleTierRecompute();
}

function scheduleResize() {
  if (resizeTimer) clearTimeout(resizeTimer);
  resizeTimer = setTimeout(resizeGraph, 80);
}

// ---- W5b viewport culling: classify each embed card by its on-screen geometry (§7.3) ----
// Only readable, on-screen cards render the full preview; off-screen cards go "hidden"
// (display:none, but stay mounted — no unmount thrash) and too-small ones drop to a bare
// shell. Tiers ride the reactive canvasTierStore, NOT node.data, so this never schedules a
// save or bumps updated_at (§5.5 / §7.8). Text cards are ignored (SVG, always cheap).
function recomputeTiers() {
  const g = graph.value;
  const host = containerRef.value;
  // Skip while the host is unmeasured (0-size, e.g. a not-yet-laid-out parent): every card would
  // fail open to "preview" and we'd write a throwaway all-preview batch. Cards default to "preview"
  // until the ResizeObserver fires the real classify once layout lands.
  if (!g || !host || !host.clientWidth || !host.clientHeight) return;
  // X6's zoom getter is zoom() (no getZoom()) — reading the wrong name silently pins zoom to 1,
  // so the shell tier never triggers and off-screen detection is wrong at any non-1 zoom.
  const zoom = g.zoom?.() ?? 1;
  const { tx = 0, ty = 0 } = g.translate?.() || {};
  const hostWidth = host.clientWidth;
  const hostHeight = host.clientHeight;
  const tiers = new Map();
  const fullCandidates = [];
  for (const node of g.getNodes()) {
    if (!isEmbedCard(node)) continue;
    const bbox = node.getBBox();
    const tier = computeEmbedTier({ bbox, tx, ty, zoom, hostWidth, hostHeight });
    tiers.set(node.id, tier);
    if (tier === EMBED_TIER.FULL) {
      // card-center → viewport-center distance (screen px) to rank T2 candidates for the budget.
      const dx = (bbox.x + bbox.width / 2) * zoom + tx - hostWidth / 2;
      const dy = (bbox.y + bbox.height / 2) * zoom + ty - hostHeight / 2;
      fullCandidates.push({ node, dist: dx * dx + dy * dy });
    }
  }
  const fullNodes = capFullBudget(tiers, fullCandidates);
  setCardTiers(tiers);
  for (const node of fullNodes) resolveFullDetail(node);
}

// §7.3 render budget: keep only the EMBED_FULL_BUDGET cards nearest the viewport center at the
// "full" tier and demote the rest to "preview" (mutating `tiers`), so a zoomed-in board never
// renders dozens of full-markdown cards at once. Returns the nodes that stay full.
function capFullBudget(tiers, fullCandidates) {
  if (fullCandidates.length <= EMBED_FULL_BUDGET) return fullCandidates.map((c) => c.node);
  fullCandidates.sort((a, b) => a.dist - b.dist);
  const kept = fullCandidates.slice(0, EMBED_FULL_BUDGET);
  const keptIds = new Set(kept.map((c) => c.node.id));
  for (const c of fullCandidates) {
    if (!keptIds.has(c.node.id)) tiers.set(c.node.id, EMBED_TIER.PREVIEW);
  }
  // eslint-disable-next-line no-console
  console.debug(`[canvas] T2 over budget: ${fullCandidates.length} candidates → ${EMBED_FULL_BUDGET}`);
  return kept.map((c) => c.node);
}

// Fetch + render one T2 card's full markdown, once per canvas session (§7.4). Rides the shared
// detail cache via the resolveDetail prop (= ensureEventDetail) and the read-mode cached renderer;
// the HTML lands in embedDetailStore, which EmbedCardNode reads. Fail-open: any miss leaves the
// card at its preview, never blank.
async function resolveFullDetail(node) {
  const resolve = props.resolveDetail;
  if (typeof resolve !== "function") return;
  const noteId = node.getData?.()?.noteId;
  if (noteId == null || noteId === "") return;
  // Known-deleted target (tombstone) → don't fetch; it'd 404 and retry on every settle.
  if (getEmbedEntry(noteId)?.status === "missing") return;
  const key = String(noteId);
  // Attempt each id at most once per board: a stored entry means resolved, fullTried membership
  // means already attempted/in-flight. A transient failure thus leaves the card at preview until
  // the canvas is reopened, rather than re-fetching on every settle.
  if (getEmbedDetailHtml(noteId) || fullTried.has(key)) return;
  fullTried.add(key);
  try {
    const detail = await resolve(Number(noteId));
    // The editor may have unmounted while the fetch was in flight — don't repopulate a store the
    // unmount just cleared (onBeforeUnmount nulls graph.value after clearEmbedDetails).
    if (!graph.value) return;
    if (detail && detail.bodyMarkdown != null) {
      setEmbedDetail(
        noteId,
        renderCachedMarkdownToHtml({ eventId: noteId, updatedAt: detail.updatedAt, bodyMarkdown: detail.bodyMarkdown })
      );
    }
  } catch {
    // Fetch failed → leave the card at preview (fail-open); not retried this session (see fullTried).
  }
}

// Recompute only after the gesture settles (§7.3 "手势中不动档"): pan/zoom/model-change events
// fire continuously, so debounce; the margin ring inside computeEmbedTier absorbs small pans
// without churning cards in and out at the edge.
function scheduleTierRecompute() {
  if (tierTimer) clearTimeout(tierTimer);
  tierTimer = setTimeout(() => {
    tierTimer = null;
    recomputeTiers();
  }, 120);
}

function ensureCardPorts(node) {
  if (node?.getPorts && node.getPorts().length === 0) node.prop("ports", buildCardPorts());
}

// Content-only snapshot (cells + background). The viewport is deliberately NOT here —
// it rides localStorage (see currentView / x6ViewStore) so pan/zoom never bumps
// updated_at or fires a save. See docs/notes-app-pivot-design.md §5.5.
function buildSnapshot() {
  const g = graph.value;
  if (!g) return null;
  return {
    _fmt: X6_CANVAS_FORMAT,
    cells: g.toJSON().cells || [],
    background: currentBackground,
  };
}

function currentView() {
  const g = graph.value;
  if (!g) return null;
  const { tx = 0, ty = 0 } = g.translate?.() || {};
  // X6's zoom getter is zoom(), not getZoom() (which doesn't exist on the Graph) — reading the
  // wrong name silently persisted zoom as 1, so a reload reset the zoom. Same fix as recomputeTiers.
  return { tx, ty, zoom: g.zoom?.() ?? 1 };
}

function flushViewSave() {
  if (viewSaveTimer) {
    clearTimeout(viewSaveTimer);
    viewSaveTimer = null;
  }
  if (props.readOnly || suppressSaves) return;
  writeX6View("canvas", props.noteId, currentView());
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

// Graph-local coordinates of the viewport center — where a toolbar-inserted node lands.
function viewportCenterLocal() {
  const g = graph.value;
  const host = containerRef.value;
  if (!g || !host) return null;
  const rect = host.getBoundingClientRect();
  return g.pageToLocal(rect.left + rect.width / 2, rect.top + rect.height / 2);
}

function addCardAtCenter() {
  const local = viewportCenterLocal();
  if (local) addCard(local.x, local.y);
}

// Drop an embed card (a reference to another note) at the viewport center. The picker in
// CanvasSurface supplies { noteId, headline }; the live title/preview arrive via the batch fetch
// kicked off here, and the backend writes an `embed` link row on the next save (§7.5).
function addEmbedCard({ noteId, headline = "" } = {}) {
  const g = graph.value;
  if (!g || props.readOnly || noteId == null) return;
  const local = viewportCenterLocal();
  if (!local) return;
  const node = g.addNode(
    buildEmbedCardNode({
      x: local.x - EMBED_DEFAULT_WIDTH / 2,
      y: local.y - EMBED_DEFAULT_HEIGHT / 2,
      noteId,
      headline,
    })
  );
  graphSelection.value?.clean();
  graphSelection.value?.select(node);
  resolveEmbedPreviews([noteId]);
  scheduleSave();
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
  addEmbedCard,
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
  // One batch fetch for every embedded note's title/preview so the cards render immediately;
  // pan/zoom afterwards costs zero fetches (§7.4). Safe no-op when the board has no embeds.
  resolveEmbedPreviews(embedNoteIdsFromSnapshot(cells));
  resizeGraph();
  // Prefer the per-device localStorage viewport; fall back to a legacy snapshot view
  // (canvases saved before viewport moved to localStorage), else centerContent below.
  const stored = readX6View("canvas", props.noteId);
  const view = stored || payload?.view;
  // Migrate a legacy snapshot viewport into localStorage on first open — else the next
  // content save (buildSnapshot no longer emits `view`) silently drops it and resets the view.
  if (!stored && payload?.view) writeX6View("canvas", props.noteId, payload.view);
  // Apply zoom BEFORE translate: zoomTo() scales about the viewport center and shifts the pan,
  // so setting the absolute translation LAST restores the exact saved {tx,ty,zoom}. (Order only
  // started to matter once zoom actually persisted — see currentView.) centerContent is the
  // no-stored-pan fallback (fresh board), so it's gated on the translate being absent.
  if (view?.zoom != null) g.zoomTo(view.zoom);
  if (view?.tx != null || view?.ty != null) {
    g.translate(view.tx || 0, view.ty || 0);
  } else if (cells.length) {
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
  // Classify tiers synchronously now that the viewport is restored, so off-screen embeds
  // start "hidden" on the FIRST paint (a big board must not render every card on open, §7.4).
  recomputeTiers();
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
  // history:change fires on add / move / remove / undo / redo → a moved-or-added embed card
  // may cross the viewport or readable-size boundary, so re-classify (debounced).
  g.on("history:change", () => {
    scheduleSave();
    scheduleTierRecompute();
  });
  // Count all selected cells (nodes AND edges) so the delete button enables for a lone
  // connector too; setTextColor is a no-op on edges, so an edge-only selection is safe.
  g.on("selection:changed", ({ selected }) => {
    emit("active", (selected || []).length);
  });
  // Pan/zoom: persist the viewport (localStorage only) AND re-classify tiers — cards move in
  // and out of the viewport ring, and zoom changes each card's on-screen pixel size.
  g.on("scale", () => {
    scheduleViewSave();
    scheduleTierRecompute();
  });
  g.on("translate", () => {
    scheduleViewSave();
    scheduleTierRecompute();
  });
  g.on("node:dblclick", ({ node }) => {
    // Text card → inline edit overlay; embed card → open the referenced note (its "activate"
    // gesture). Single-click still just selects, so grabbing a card to move/delete never opens.
    if (isEmbedCard(node)) {
      const noteId = node.getData()?.noteId;
      if (noteId != null) {
        // The preview popover positions against a rect POJO (numeric top/left/right/height), so
        // pass the card's screen rect — NOT the raw DOM node, whose reads would all be NaN.
        const anchor = g.findViewByCell(node)?.container?.getBoundingClientRect?.() || null;
        emit("open-embed", { id: noteId, anchor });
      }
      return;
    }
    showEditOverlay(node);
  });
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
  if (tierTimer) clearTimeout(tierTimer);
  resizeObserver?.disconnect();
  if (containerRef.value) containerRef.value.removeEventListener("keydown", onKeydown);
  cancelEdit();
  flushViewSave();
  flushSave();
  // Drop this board's tiers + rendered T2 detail so they can't bleed into the next note
  // (CanvasSurface keys the editor by note.id → a switch remounts and re-classifies from scratch).
  clearCardTiers();
  clearEmbedDetails();
  fullTried.clear();
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
    <!-- Renders each embed card's Vue instance into its X6 foreignObject (via @antv/x6-vue-shape
         teleport); produces no layout of its own. Must stay mounted while the board is open. -->
    <EmbedTeleport />
    <div v-if="loading" class="mm-loading">正在加载画布…</div>
  </div>
</template>
