<script setup>
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import EventDetailPane from "@/components/timeline-notes/EventDetailPane.vue";
import MobileTopBar from "@/components/timeline-notes/MobileTopBar.vue";
import RelatedEventPreviewPopover from "@/components/timeline-notes/RelatedEventPreviewPopover.vue";
import TimelineFeed from "@/components/timeline-notes/TimelineFeed.vue";
import TimelineLucideIcon from "@/components/timeline-notes/TimelineLucideIcon.vue";
import TopicSidebar from "@/components/timeline-notes/TopicSidebar.vue";
import { api } from "@/composables/useApi";
import { pushToast } from "@/composables/useToast";
import { useTimelineStore } from "@/composables/useTimelineStore";
import { usePaneSwapDrag } from "@/composables/usePaneSwapDrag";
import { useViewport } from "@/composables/useViewport";
import {
  buildX6SeedSnapshot,
} from "@/utils/mindmapX6.js";
import { buildCanvasSeedSnapshot } from "@/utils/canvasX6.js";
import {
  buildFavoriteFacetRows,
  buildOptionId,
  buildRecentFavoriteEvents,
  buildGlobalFavoriteEvents,
  clampSortForView,
  containerTypeViews,
  findBookshelfByName,
  compareEventsBySort,
  DEFAULT_SORT,
  filterFavoriteEventsByScope,
  groupTimelineEvents,
  matchesEventSearch,
  matchesPropertyFilter,
  mindmapRootData,
  normalizeTopicBookshelf,
  resolveCreateTopicRequest,
  normalizeSortLevels,
  normalizeTopicColumns,
  resolveDisplayStyle,
  shouldAutoLoadMoreForFilteredEvents,
  sortBookshelfTree,
  SIDEBAR_SORT_MODES,
} from "@/utils/timelineNotes";

const CommandPalette = defineAsyncComponent(() => import("@/components/timeline-notes/CommandPalette.vue"));
const MindmapSurface = defineAsyncComponent(() => import("@/components/timeline-notes/MindmapSurface.vue"));
const CanvasSurface = defineAsyncComponent(() => import("@/components/timeline-notes/CanvasSurface.vue"));
const SettingsModal = defineAsyncComponent(() => import("@/components/settings/SettingsModal.vue"));

const route = useRoute();
const router = useRouter();
const detailPaneRef = ref(null);
const feedPaneRef = ref(null);
const mindmapSurfaceRef = ref(null);
const canvasSurfaceRef = ref(null);
const mobileFeedScrollTop = ref(0);
const timelineStore = useTimelineStore();
const { isMobile, isCompactDesktop } = useViewport();

const DETAIL_MODES = new Set(["view", "edit", "create"]);
const FILTERS = new Set(["all", "today", "week", "favorite", "trash"]);
const LEFT_WIDTH_KEY = "chronicle-left-width";
const RIGHT_WIDTH_KEY = "chronicle-right-width";
const PREVIEW_KEY = "chronicle-show-preview";
const NAV_POSITION_KEY = "chronicle-nav-position";
const DETAIL_POSITION_KEY = "chronicle-detail-position";
const SIDEBAR_SORT_KEY = "chronicle-sidebar-sort";
const BOOKSHELF_COLLAPSE_KEY = "chronicle-bookshelf-collapsed";
const FAVORITE_SCOPE_KINDS = new Set(["all", "current-topic", "recent", "topic", "type", "tag"]);

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function normalizeFavoriteScope(scope = {}) {
  const kind = FAVORITE_SCOPE_KINDS.has(String(scope?.kind || "")) ? String(scope.kind) : "all";
  if (kind === "topic") return { kind, topicId: Number(scope?.topicId) || null };
  if (kind === "type" || kind === "tag") return { kind, value: String(scope?.value || "").trim(), topicId: Number(scope?.topicId) || null };
  return { kind };
}

function readStorage(key, fallback) {
  if (typeof window === "undefined") return fallback;
  const raw = window.localStorage.getItem(key);
  return raw == null ? fallback : raw;
}

function writeStorage(key, value) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(key, String(value));
}

function readObjectStorage(key, fallback = {}) {
  const raw = readStorage(key, "");
  if (!raw) return { ...fallback };
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : { ...fallback };
  } catch {
    return { ...fallback };
  }
}

function writeObjectStorage(key, value) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(key, JSON.stringify(value || {}));
}

// Sidebar edge is a two-value enum; coerce any legacy/invalid stored or server
// value to the default so a bad localStorage or app_config value cannot break the
// layout (the backend does not validate it).
function normalizeNavPosition(value) {
  return value === "right" ? "right" : "left";
}

// Same two-value coercion for the detail pane slot ("edge" = outer edge, "center" =
// swapped with the feed into the middle track) — docs/layout-swap-design.md §7.
function normalizeDetailPosition(value) {
  return value === "center" ? "center" : "edge";
}

function normalizeSidebarSort(value) {
  return SIDEBAR_SORT_MODES.includes(value) ? value : "default";
}

function parseRouteNumber(name) {
  const raw = route?.query?.[name];
  const value = Number.parseInt(Array.isArray(raw) ? raw[0] : raw, 10);
  return Number.isNaN(value) ? null : value;
}

function parseRouteString(name) {
  const raw = route?.query?.[name];
  return String(Array.isArray(raw) ? raw[0] : raw || "");
}

function parseRouteMode() {
  const raw = parseRouteString("mode") || "view";
  return DETAIL_MODES.has(raw) ? raw : "view";
}

function parseRouteFilter() {
  const raw = parseRouteString("filter") || "all";
  return FILTERS.has(raw) ? raw : "all";
}

function parseRoutePropertyFilter() {
  const key = parseRouteString("pk");
  return key ? { key, value: parseRouteString("pv") } : { key: "", value: "" };
}

const state = reactive({
  loading: true,
  eventsLoading: false,
  saving: false,
  columnSaving: false,
  error: "",
  detailLoading: false,
  detailError: "",
  config: {
    brandName: "编年",
    // Seeded from localStorage so the correct sidebar edge paints on frame 1;
    // loadWorkspace() reconciles with the cross-device app_config truth on load.
    navPosition: normalizeNavPosition(readStorage(NAV_POSITION_KEY, "left")),
    detailPosition: normalizeDetailPosition(readStorage(DETAIL_POSITION_KEY, "edge")),
    // Left-tree sort seeded the same way so the saved order paints on frame 1.
    sidebarSort: normalizeSidebarSort(readStorage(SIDEBAR_SORT_KEY, "default")),
    media: {
      compress: true,
      keepOriginal: false,
      quality: 80,
      maxEdge: 1920,
      thumbEdge: 400,
    },
  },
  topics: [],
  bookshelves: [],
  bookshelfTree: [],
  activeTopicId: null,
  activeTopicMeta: null,
  events: [],
  eventBounds: null,
  hasMore: false,
  nextCursor: null,
  loadingMore: false,
  autoLoadBlockedKey: "",
  searchQuery: "",
  selectedEventId: null,
  detailMode: "view",
  sidebarFilter: "all",
  collectionMode: "",
  favoriteScope: { kind: "all" },
  propertyFilter: { key: "", value: "" },
  activeEra: "",
  locateDate: "",
  detailDirty: false,
  confirmUnsaved: false,
  pendingAction: null,
  afterSaveAction: null,
  restoreRouteOnCancel: false,
  routeRestoreSnapshot: null,
  menuEvent: null,
  settingsOpen: false,
  confirmDeleteBookshelf: null,
  confirmDeleteTopics: null,
  confirmPurgeIds: null,
  rightOpen: false,
  // The mindmap note (note_type=mindmap) whose canvas is open in the center column
  // (D-2: 中栏内嵌). Null → the feed list shows. mindmapSaving drives the bar status.
  mindmapOpenId: null,
  mindmapSaving: false,
  mobileSidebarOpen: false,
  mobileSearchOpen: false,
  leftWidth: Number.parseInt(readStorage(LEFT_WIDTH_KEY, "268"), 10) || 268,
  rightWidth: Number.parseInt(readStorage(RIGHT_WIDTH_KEY, "412"), 10) || 412,
  bookshelfCollapsed: readObjectStorage(BOOKSHELF_COLLAPSE_KEY),
  focusedBookshelfName: "",
  showPreview: readStorage(PREVIEW_KEY, "on") !== "off",
  searchRequestKey: 0,
  commandOpen: false,
  commandQuery: "",
  commandResults: [],
  commandLoading: false,
  commandError: "",
  relatedPreviewOpen: false,
  relatedPreviewEventId: null,
  relatedPreviewLoading: false,
  relatedPreviewError: "",
  relatedPreviewPinned: false,
  relatedPreviewPlacement: "left",
  relatedPreviewStyle: {},
  topicCreateRequestKey: 0,
  editPreview: null,
  // Center-column sort (ordered { field, dir } levels) + timeline grouping
  // dimension; reloaded from the backend per notebook (Topic meta) or, for the
  // cross-notebook favorites view, from app config (docs/center-sort-design.md §12).
  sort: normalizeSortLevels(DEFAULT_SORT),
  groupBy: "era",
});

let resizeCleanup = null;
let detailRequestSeq = 0;
let topicEventsRequestSeq = 0;
let workspaceSelectionRequestSeq = 0;
let commandSearchTimer = null;
let commandRequestSeq = 0;
let relatedPreviewRequestSeq = 0;
let detailAbortController = null;
let detailPrefetchHandle = null;
let columnSaveChain = Promise.resolve();
const latestColumnSaveRevisionByTopic = new Map();
let columnSaveInFlight = 0;
// Serializes PUT /api/config for the cross-notebook favorites sort so rapid
// reorders can't land out of order (docs/center-sort-design.md §12).
let configSaveChain = Promise.resolve();

function normalizeMediaConfig(media = {}) {
  const source = media && typeof media === "object" ? media : {};
  return {
    compress: source.compress !== false,
    keepOriginal: source.keepOriginal === true,
    quality: Math.min(100, Math.max(1, Number.parseInt(source.quality, 10) || 80)),
    maxEdge: Math.min(8192, Math.max(320, Number.parseInt(source.maxEdge, 10) || 1920)),
    thumbEdge: Math.min(2048, Math.max(96, Number.parseInt(source.thumbEdge, 10) || 400)),
  };
}

const workspaceStyle = computed(() => ({
  "--left-w": `${isCompactDesktop.value ? clamp(state.leftWidth, 220, 240) : state.leftWidth}px`,
  "--right-w": `${isCompactDesktop.value ? clamp(state.rightWidth, 360, 380) : state.rightWidth}px`,
}));

// Painted column widths (workspaceStyle clamps them on compact desktops); the drag
// geometry must use the same values the grid actually renders at.
function paintedLeftWidth() {
  return isCompactDesktop.value ? clamp(state.leftWidth, 220, 240) : state.leftWidth;
}
function paintedRightWidth() {
  return isCompactDesktop.value ? clamp(state.rightWidth, 360, 380) : state.rightWidth;
}

// Drag-to-swap the feed and detail panes from either toolbar's empty area — the
// third entry point for detailPosition (docs/pane-swap-drag-design.md). Commits
// through the same updateDetailPosition() as the settings control and ⋮ menu.
const paneDragGhostEl = ref(null);
const PANE_GHOST = {
  sidebar: { icon: "panelLeft", label: "功能栏" },
  feed: { icon: "list", label: "笔记列表" },
  detail: { icon: "note", label: "笔记详情" },
};
const paneSwap = usePaneSwapDrag({
  // The sidebar swap (navPosition) works whether or not the detail is open; the
  // feed↔detail swap needs an open detail pane to trade places with.
  isEnabled: (pane) => !isMobile.value && (pane === "sidebar" || state.rightOpen),
  getLayout: () => ({
    W: typeof window === "undefined" ? 1920 : window.innerWidth,
    L: paintedLeftWidth(),
    R: paintedRightWidth(),
    navRight: state.config.navPosition === "right",
    detailCenter: state.config.detailPosition === "center",
    rightOpen: state.rightOpen,
  }),
  getGhostEl: () => paneDragGhostEl.value,
  onCommit: (pane) => {
    if (pane === "sidebar") {
      updateNavPosition(state.config.navPosition === "right" ? "left" : "right");
    } else {
      updateDetailPosition(state.config.detailPosition === "center" ? "edge" : "center");
    }
  },
});
const paneDragGhostIcon = computed(() => PANE_GHOST[paneSwap.draggedPane.value]?.icon || "note");
const paneDragGhostLabel = computed(() => PANE_GHOST[paneSwap.draggedPane.value]?.label || "");

const bookshelfTree = computed(() => state.bookshelfTree);
// Presentational re-order of the sidebar tree (shelves + notebooks) by the saved
// global sort; lookup/logic paths keep using the unsorted bookshelfTree above.
const sortedBookshelfTree = computed(() => sortBookshelfTree(state.bookshelfTree, state.config.sidebarSort));

const activeBookshelfName = computed(() => state.focusedBookshelfName || (state.activeTopicMeta ? normalizeTopicBookshelf(state.activeTopicMeta).name : ""));

function flattenBookshelves(tree = []) {
  return (Array.isArray(tree) ? tree : []).map(({ topics, ...bookshelf }) => ({ ...bookshelf }));
}

function flattenTopicsFromTree(tree = []) {
  return (Array.isArray(tree) ? tree : []).flatMap((bookshelf) => (bookshelf?.topics || []).map((entry) => entry?.topic).filter(Boolean));
}

async function refreshBookshelfTree({ syncTopics = false } = {}) {
  const tree = await api.listBookshelfTree();
  state.bookshelfTree = Array.isArray(tree) ? tree : [];
  state.bookshelves = flattenBookshelves(state.bookshelfTree);
  if (syncTopics) timelineStore.setTopics(flattenTopicsFromTree(state.bookshelfTree));
}

async function refreshSidebarData({ reloadTopics = false } = {}) {
  await refreshBookshelfTree({ syncTopics: reloadTopics });
}

function persistBookshelfCollapsed(nextState) {
  state.bookshelfCollapsed = { ...nextState };
  writeObjectStorage(BOOKSHELF_COLLAPSE_KEY, state.bookshelfCollapsed);
}

function ensureBookshelfExpandedForTopic(topicId = state.activeTopicId) {
  const topic = state.topics.find((item) => item.id === Number(topicId));
  if (!topic) return;
  const { name } = normalizeTopicBookshelf(topic);
  if (name) state.focusedBookshelfName = name;
  if (!name || state.bookshelfCollapsed[name] !== true) return;
  persistBookshelfCollapsed({ ...state.bookshelfCollapsed, [name]: false });
}

function toggleBookshelf(name) {
  if (!name) return;
  state.focusedBookshelfName = name;
  persistBookshelfCollapsed({
    ...state.bookshelfCollapsed,
    [name]: state.bookshelfCollapsed[name] !== true,
  });
}

function setAllBookshelvesCollapsed(collapsed) {
  const nextState = { ...state.bookshelfCollapsed };
  for (const bookshelf of bookshelfTree.value) {
    nextState[bookshelf.name] = Boolean(collapsed);
  }
  persistBookshelfCollapsed(nextState);
}

const activeTopicTitle = computed(
  () => state.activeTopicMeta?.title || state.topics.find((topic) => topic.id === state.activeTopicId)?.title || "编年"
);
const autoLoadContextKey = computed(() =>
  JSON.stringify([
    state.activeTopicId || null,
    state.sidebarFilter,
    state.propertyFilter?.key || "",
    state.propertyFilter?.value || "",
    state.activeEra,
    state.searchQuery.trim(),
    state.collectionMode,
  ])
);

const isGlobalFavoritesMode = computed(() => state.collectionMode === "favorites");
const globalFavoriteEvents = computed(() => buildGlobalFavoriteEvents(timelineStore.state.eventsIndex));
const favoriteScope = computed(() => normalizeFavoriteScope(state.favoriteScope));
const favoritesScopedEvents = computed(() =>
  filterFavoriteEventsByScope(globalFavoriteEvents.value, favoriteScope.value, state.topics, state.activeTopicId)
);
const favoritesRecentEvents = computed(() => buildRecentFavoriteEvents(favoritesScopedEvents.value, 5));
const favoriteTypeRows = computed(() => buildFavoriteFacetRows(favoritesScopedEvents.value, state.topics, "type"));
const favoriteTagRows = computed(() => buildFavoriteFacetRows(favoritesScopedEvents.value, state.topics, "tags"));
const favoriteTopicRows = computed(() => {
  const counts = new Map();
  for (const event of favoritesScopedEvents.value) {
    const topicId = Number(event?.topicId);
    if (!topicId) continue;
    const topic = timelineStore.topicById(topicId) || state.topics.find((item) => item.id === topicId);
    if (!topic) continue;
    const existing = counts.get(topicId) || {
      topicId,
      label: topic.title || topic.name || `笔记本 ${topicId}`,
      count: 0,
    };
    existing.count += 1;
    counts.set(topicId, existing);
  }
  return [...counts.values()].sort((left, right) => right.count - left.count || left.label.localeCompare(right.label, "zh-CN"));
});
const favoriteScopeLabel = computed(() => {
  const scope = favoriteScope.value;
  if (scope.kind === "current-topic") return `当前笔记本收藏 · ${activeTopicTitle.value}`;
  if (scope.kind === "recent") return "最近加星";
  if (scope.kind === "topic") {
    const topic = timelineStore.topicById(scope.topicId) || state.topics.find((item) => item.id === scope.topicId);
    return `来源笔记本 · ${topic?.title || topic?.name || "未命名笔记本"}`;
  }
  if (scope.kind === "type") {
    const match = favoriteTypeRows.value.find((item) => item.value === scope.value && Number(item.topicId) === Number(scope.topicId));
    return `类型 · ${match?.displayLabel || scope.value || "未命名类型"}`;
  }
  if (scope.kind === "tag") {
    const match = favoriteTagRows.value.find((item) => item.value === scope.value && Number(item.topicId) === Number(scope.topicId));
    return `标签 · ${match?.displayLabel || scope.value || "未命名标签"}`;
  }
  return "全部收藏";
});
const favoritesPanel = computed(() => {
  const recentAll = buildRecentFavoriteEvents(globalFavoriteEvents.value, 5);
  const currentTopicCount = filterFavoriteEventsByScope(globalFavoriteEvents.value, { kind: "current-topic" }, state.topics, state.activeTopicId).length;
  const scope = favoriteScope.value;
  return {
    overview: [
      { id: "all", label: "全部收藏", count: globalFavoriteEvents.value.length, scope: { kind: "all" }, active: scope.kind === "all" },
      {
        id: "current-topic",
        label: "当前笔记本收藏",
        count: currentTopicCount,
        scope: { kind: "current-topic" },
        active: scope.kind === "current-topic",
      },
      { id: "recent", label: "最近加星", count: recentAll.length, scope: { kind: "recent" }, active: scope.kind === "recent" },
    ],
    sources: favoriteTopicRows.value.map((row) => ({
      ...row,
      active: scope.kind === "topic" && Number(scope.topicId) === Number(row.topicId),
      scope: { kind: "topic", topicId: row.topicId },
    })),
    types: favoriteTypeRows.value.map((row) => ({
      ...row,
      active: scope.kind === "type" && scope.value === row.value && Number(scope.topicId) === Number(row.topicId),
      scope: { kind: "type", value: row.value, topicId: row.topicId },
    })),
    tags: favoriteTagRows.value.map((row) => ({
      ...row,
      active: scope.kind === "tag" && scope.value === row.value && Number(scope.topicId) === Number(row.topicId),
      scope: { kind: "tag", value: row.value, topicId: row.topicId },
    })),
    recent: favoritesRecentEvents.value,
    emptyAll: globalFavoriteEvents.value.length === 0,
    emptyScope: globalFavoriteEvents.value.length > 0 && favoritesScopedEvents.value.length === 0,
    contextLabel: favoriteScopeLabel.value,
    clearable: scope.kind !== "all",
  };
});
const feedTitle = computed(() => (isGlobalFavoritesMode.value ? "收藏（跨本）" : activeTopicTitle.value));
const topicColumns = computed(() => normalizeTopicColumns(state.activeTopicMeta?.columns));
const feedColumns = computed(() => (isGlobalFavoritesMode.value ? [] : topicColumns.value));
// Display-style view (axis 1): start from the persisted style, then derive the live
// capability set from the local notebook snapshot so note creates/deletes (including
// undated mindmaps) update the switcher immediately, before a fresh /meta round-trip.
const feedDisplayStyle = computed(() => state.activeTopicMeta?.displayStyle || "timeline");
const feedCapabilities = computed(() => {
  if (isGlobalFavoritesMode.value) return [];
  // Container type (数字图书馆) presets the offered view set. Fall back to the legacy
  // data-derived gate only for meta predating container types (no `views`).
  const views = state.activeTopicMeta?.views;
  if (Array.isArray(views) && views.length) return [...views];
  const enabled = new Set(["list", "table", feedDisplayStyle.value]);
  const columns = normalizeTopicColumns(state.activeTopicMeta?.columns);
  const events = state.events || [];
  if (events.some((event) => event.hasDate !== false && event.dateKey != null)) enabled.add("timeline");
  if (events.length) enabled.add("outline");
  if (columns.some((column) => ["select", "multiselect"].includes(column.type))) enabled.add("board");
  if (events.some((event) => event.image || event.imageUrl || event.thumbUrl)) enabled.add("gallery");
  return [...enabled];
});
const showViewSwitcher = computed(
  () => !isMobile.value && !isGlobalFavoritesMode.value && Boolean(state.activeTopicId)
);
// Sort (docs/center-sort-design.md): direction is universal, fields are clamped to
// what the effective view can sort. Cross-notebook favorites renders as a flat list
// (own owner key + 收藏时间 field); otherwise the effective view mirrors the feed's
// effectiveView() (resolveDisplayStyle + mobile→timeline) so both agree on the clamp.
const effectiveDisplayStyle = computed(() => {
  if (isMobile.value) return "timeline";
  if (isGlobalFavoritesMode.value) return "list";
  return resolveDisplayStyle(feedDisplayStyle.value, feedCapabilities.value);
});
// Clamp/compare against the SAME columns the feed renders (feedColumns is [] in
// favorites) so the page and feed never disagree on which fields are sortable. The
// favorites-sort context only applies when favorites actually renders flat — on
// mobile it stays the era-grouped timeline (§9), so it keeps time-only sorting
// rather than ordering a grouped list by 收藏时间.
const favoritesSortContext = computed(() => isGlobalFavoritesMode.value && !isMobile.value);
const activeSort = computed(() =>
  clampSortForView(state.sort, effectiveDisplayStyle.value, feedColumns.value, favoritesSortContext.value)
);
const activeComparator = computed(() => compareEventsBySort(activeSort.value, feedColumns.value));

// The direction the backend feed must page in. Only the primary *time* sort is
// pushed down for W1 (timeline/outline clamp their primary to time); non-time
// primaries keep today's client-side sort over the loaded page, so they page
// ascending (dir 1). Descending here makes cursor pagination fetch newest-first,
// so a large notebook's "倒序" shows the true newest, not a reversed oldest page.
const feedFetchDir = computed(() => {
  const primary = activeSort.value?.[0];
  return primary && primary.field === "time" && primary.dir < 0 ? -1 : 1;
});

// Sort/grouping persist to the backend for cross-device sync: per-notebook
// sort + groupBy ride the Topic meta (loaded with the index), the cross-notebook
// favorites sort rides app config (it has no owning notebook). Reload from those
// sources whenever the owner changes (and on mount).
function topicSortLevels(topicId) {
  return normalizeSortLevels(timelineStore.topicById(topicId)?.sort);
}

function favoritesSortLevels() {
  const stored = state.config?.favoritesSort;
  return Array.isArray(stored) && stored.length
    ? normalizeSortLevels(stored)
    : [{ field: "favorited", dir: -1 }];
}

function loadGroupBy(topicId) {
  const raw = timelineStore.topicById(topicId)?.groupBy;
  return ["era", "year", "month"].includes(raw) ? raw : "era";
}

watch(
  () => [isGlobalFavoritesMode.value, state.activeTopicId],
  () => {
    state.sort = isGlobalFavoritesMode.value ? favoritesSortLevels() : topicSortLevels(state.activeTopicId);
    state.groupBy = loadGroupBy(state.activeTopicId);
  },
  // flush:"sync" so state.sort (hence feedFetchDir) is current the instant
  // activeTopicId changes — the topic-switch fetch reads feedFetchDir synchronously
  // in the same tick, so a 'pre'-flushed watcher would let it page the previous
  // topic's direction (opening a descending notebook would load its oldest page).
  { immediate: true, flush: "sync" }
);

function changeSort(sort) {
  const prevFetchDir = feedFetchDir.value;
  const next = normalizeSortLevels(sort);
  state.sort = next;
  if (isGlobalFavoritesMode.value) {
    persistFavoritesSort(next);
  } else if (state.activeTopicId) {
    persistTopicMetaField(state.activeTopicId, { sort: next });
    // The backend feed pages by time direction, so flipping 正序/倒序 changes which
    // events the first page holds — re-fetch from page 1. (Favorites is fully
    // in-memory and re-sorts client-side, so it needs no re-fetch.)
    if (feedFetchDir.value !== prevFetchDir) {
      void ensureTopicEventsReady(state.activeTopicId, { force: true });
    }
  }
}

function changeGroupBy(groupBy) {
  const next = ["era", "year", "month"].includes(groupBy) ? groupBy : "era";
  state.groupBy = next;
  if (state.activeTopicId) {
    persistTopicMetaField(state.activeTopicId, { groupBy: next });
  }
}

// Persist a per-notebook sort/groupBy change through the shared meta-save chain
// (like changeDisplayStyle) so a concurrent column-save PUT can't land out of
// order and revert it. `patch` carries the camelCase field(s) to store + PUT.
function persistTopicMetaField(topicId, patch) {
  const topicMeta = timelineStore.topicById(topicId) || state.activeTopicMeta;
  if (!topicMeta) return;
  timelineStore.upsertTopic({ ...topicMeta, ...patch });
  if (state.activeTopicId === topicId) syncActiveTopicFromStore();
  const task = async () => {
    try {
      const meta = await api.updateTopicMeta(topicId, patch);
      timelineStore.upsertTopic({ ...meta, ...patch });
      if (state.activeTopicId === topicId) syncActiveTopicFromStore();
    } catch (error) {
      try {
        timelineStore.upsertTopic(await api.getTopicMeta(topicId));
        if (state.activeTopicId === topicId) syncActiveTopicFromStore();
      } catch {
        // Best-effort rollback to server truth; keep the error toast.
      }
      pushToast(`排序保存失败：${error.message}`, "error");
    }
  };
  columnSaveChain = columnSaveChain.then(task, task);
  return columnSaveChain;
}

// The cross-notebook favorites sort has no owning notebook, so it lives in app
// config (cross-device). Optimistic local update + a serialized PUT /api/config
// so rapid reorders can't land out of order; on failure, roll back to server
// truth (parity with persistTopicMetaField).
function persistFavoritesSort(sort) {
  state.config.favoritesSort = sort;
  const task = async () => {
    try {
      await api.updateConfig({ favoritesSort: sort });
    } catch (error) {
      try {
        const config = await api.getConfig();
        state.config.favoritesSort = config?.favoritesSort ?? [{ field: "favorited", dir: -1 }];
        if (isGlobalFavoritesMode.value) state.sort = favoritesSortLevels();
      } catch {
        // Best-effort rollback to server truth; keep the error toast.
      }
      pushToast(`收藏排序保存失败：${error.message}`, "error");
    }
  };
  configSaveChain = configSaveChain.then(task, task);
  return configSaveChain;
}
// Visible now means visible: once a user turns a property column on, the center
// feed renders it even if every current row would show "—". This keeps the eye
// toggle's behavior direct and predictable.
const feedEmptyColumnKeys = computed(() => []);
const selectedEventDetail = computed(() => timelineStore.detailById(state.selectedEventId));
const selectedEventIndex = computed(
  () =>
    state.events.find((event) => event.id === state.selectedEventId) ||
    timelineStore.state.eventsIndex.find((event) => event.id === state.selectedEventId) ||
    null
);
const selectedEvent = computed(() => selectedEventDetail.value || selectedEventIndex.value);
const relatedPreviewDetail = computed(() => timelineStore.detailById(state.relatedPreviewEventId));
const relatedPreviewIndex = computed(
  () => timelineStore.state.eventsIndex.find((event) => event.id === Number(state.relatedPreviewEventId)) || null
);
const relatedPreviewEvent = computed(() => relatedPreviewDetail.value || relatedPreviewIndex.value);
const relatedPreviewTopicTitle = computed(() => {
  const topicId = relatedPreviewEvent.value?.topicId;
  return (topicId && timelineStore.topicById(topicId)?.title) || activeTopicTitle.value;
});
const detailRequiresFullEvent = computed(() => Boolean(state.rightOpen && state.selectedEventId && state.detailMode !== "create"));
const detailPaneEvent = computed(() => {
  if (state.detailMode === "create") return null;
  if (detailRequiresFullEvent.value && !selectedEventDetail.value) return null;
  return selectedEvent.value;
});
const detailPaneLoading = computed(() => Boolean(!state.detailError && (state.detailLoading || (detailRequiresFullEvent.value && !selectedEventDetail.value))));
// The mindmap note whose canvas occupies the center column. Reads the full detail
// (with bodyJson) from the cache; openMindmap ensures it is loaded first. The
// topic+selection guard auto-hides a stale canvas after any context change (switch
// notebook / filter / select another note) so the center can't get stuck showing an
// old mindmap over the new feed — no per-navigation closeMindmap() needed.
// mindmapOpenId is the single "structured note open in the center column" id — it
// drives BOTH the mindmap and the canvas surface (they only differ in how the snapshot
// renders). The two computeds discriminate by note_type so the right surface mounts.
const mindmapNote = computed(() => {
  if (!state.mindmapOpenId) return null;
  const note = timelineStore.detailById(state.mindmapOpenId);
  if (!note || note.topicId !== state.activeTopicId || state.selectedEventId !== state.mindmapOpenId) return null;
  return note.noteType === "mindmap" ? note : null;
});
const canvasNote = computed(() => {
  if (!state.mindmapOpenId) return null;
  const note = timelineStore.detailById(state.mindmapOpenId);
  if (!note || note.topicId !== state.activeTopicId || state.selectedEventId !== state.mindmapOpenId) return null;
  return note.noteType === "canvas" ? note : null;
});

function eventCreatedDate(event) {
  const raw = event?.createdAt || event?.updatedAt;
  const date = raw ? new Date(raw) : null;
  return date && !Number.isNaN(date.getTime()) ? date : null;
}

function isToday(event) {
  const date = eventCreatedDate(event);
  if (!date) return false;
  const now = new Date();
  return date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth() && date.getDate() === now.getDate();
}

function isThisWeek(event) {
  const date = eventCreatedDate(event);
  if (!date) return false;
  const now = new Date();
  const start = new Date(now);
  const day = (now.getDay() + 6) % 7;
  start.setDate(now.getDate() - day);
  start.setHours(0, 0, 0, 0);
  const end = new Date(start);
  end.setDate(start.getDate() + 7);
  return date >= start && date < end;
}

function matchesMainFilter(event, filter) {
  if (filter === "trash") return Boolean(event.deletedAt);
  if (event.deletedAt) return false;
  if (filter === "today") return isToday(event);
  if (filter === "week") return isThisWeek(event);
  if (filter === "favorite") return Boolean(event.favorite);
  return true;
}

// Seamless edit preview: while a node is being edited, overlay the live draft
// (title / date / era) onto its center-column row so the row updates and
// re-sorts/re-groups in real time. Date is applied only once fully valid so a
// mid-typing partial value never corrupts the sort order.
function applyPreviewOverlay(event, preview) {
  const year = Number.parseInt(preview.dateYear, 10);
  const month = Number.parseInt(preview.dateMonth, 10);
  const day = Number.parseInt(preview.dateDay, 10);
  const validDate =
    Number.isInteger(year) && Number.isInteger(month) && Number.isInteger(day) &&
    month >= 1 && month <= 12 && day >= 1 && day <= 31;
  const headline = String(preview.headline ?? "").trim();
  const era = String(preview.era ?? "").trim();
  return {
    ...event,
    headline: headline || event.headline,
    era: era || event.era,
    ...(validDate
      ? {
          dateParts: { year, month, day },
          dateKey: year * 10000 + month * 100 + day,
          isoDate: `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`,
          displayLabel: `${year}年${month}月${day}日`,
        }
      : {}),
  };
}

function withPreviewOverlay(events) {
  const preview = state.editPreview;
  if (!preview || !preview.id) return events;
  return events.map((event) => (event.id === preview.id ? applyPreviewOverlay(event, preview) : event));
}

function previewedEvents() {
  return withPreviewOverlay(isGlobalFavoritesMode.value ? favoritesScopedEvents.value : state.events);
}

function filterEvents({ filter = state.sidebarFilter, propertyFilter = state.propertyFilter, era = state.activeEra, search = state.searchQuery } = {}) {
  if (isGlobalFavoritesMode.value) {
    return [...previewedEvents()]
      .filter((event) => matchesEventSearch(event, search, []))
      .sort(activeComparator.value);
  }

  // The row being edited stays visible even if the live draft no longer matches
  // the active property/era/search, so it never vanishes mid-edit under a filter.
  // Never exempt it into the trash view (a live row must not appear there).
  const editingId = filter === "trash" ? null : (state.editPreview?.id ?? null);
  const columns = topicColumns.value;
  return [...previewedEvents()]
    .filter((event) => event.id === editingId || matchesMainFilter(event, filter))
    .filter((event) => event.id === editingId || !propertyFilter?.key || matchesPropertyFilter(event, propertyFilter))
    .filter((event) => event.id === editingId || !era || event.era === era)
    .filter((event) => event.id === editingId || matchesEventSearch(event, search, columns))
    .sort(activeComparator.value);
}

const visibleEvents = computed(() => filterEvents());
const groupedEvents = computed(() => groupTimelineEvents(visibleEvents.value, state.groupBy, "", feedColumns.value, activeSort.value));

const feedEmptyReason = computed(() => {
  if (state.error) return "";
  if (isGlobalFavoritesMode.value && state.searchQuery.trim()) return "跨笔记本收藏中没有找到记录。";
  if (isGlobalFavoritesMode.value && favoritesPanel.value.emptyScope) return "当前筛选下没有收藏。";
  if (isGlobalFavoritesMode.value) return "暂无跨笔记本收藏。";
  if (!state.activeTopicId) return "先创建或选择一个笔记本。";
  if (state.sidebarFilter === "trash" && visibleEvents.value.length === 0) return "回收站为空。";
  if (state.searchQuery.trim()) return "当前搜索条件下没有找到记录。";
  if (state.activeEra) return "当前分组下没有记录。";
  if (state.propertyFilter?.key) return "当前属性筛选下没有记录。";
  return "当前筛选下没有记录。";
});

watch(
  () => [
    visibleEvents.value.length,
    state.hasMore,
    state.eventsLoading,
    state.loadingMore,
    state.activeTopicId,
    isGlobalFavoritesMode.value,
  ],
  ([visibleCount, hasMore, eventsLoading, loadingMore, activeTopicId, globalFavoritesMode]) => {
    if (
      state.autoLoadBlockedKey !== autoLoadContextKey.value &&
      shouldAutoLoadMoreForFilteredEvents({
        activeTopicId,
        globalFavoritesMode,
        hasMore,
        eventsLoading,
        loadingMore,
        visibleCount,
      })
    ) {
      void loadMoreActiveTopicEvents({ auto: true });
    }
  }
);

watch(autoLoadContextKey, (next, previous) => {
  if (previous && next !== previous && state.autoLoadBlockedKey === previous) {
    state.autoLoadBlockedKey = "";
  }
});

async function syncRouteState(overrides = {}) {
  const topicId = overrides.topicId !== undefined ? overrides.topicId : state.activeTopicId;
  const eventId =
    overrides.eventId !== undefined
      ? overrides.eventId
      : state.rightOpen && state.selectedEventId
        ? state.selectedEventId
        : null;
  const mode = overrides.mode ?? state.detailMode;
  const filter = overrides.filter ?? state.sidebarFilter;
  const propertyFilter = overrides.propertyFilter ?? state.propertyFilter;
  const era = overrides.era ?? state.activeEra;
  const date = overrides.date ?? state.locateDate;
  await router.replace({
    query: {
      ...route.query,
      topic: topicId ? String(topicId) : undefined,
      event: eventId ? String(eventId) : undefined,
      mode: mode !== "view" ? mode : undefined,
      filter: filter !== "all" ? filter : undefined,
      pk: propertyFilter?.key || undefined,
      pv: propertyFilter?.key ? String(propertyFilter.value) : undefined,
      tag: undefined,
      era: era || undefined,
      date: date || undefined,
    },
  });
}

function setDefaultSelection(preferredEventId = null) {
  const items = filterEvents();
  if (preferredEventId && items.some((event) => event.id === preferredEventId)) {
    state.selectedEventId = preferredEventId;
    return;
  }
  if (items.some((event) => event.id === state.selectedEventId)) return;
  state.selectedEventId = items[0]?.id ?? null;
}

// mindmap and canvas notes both open their own center-column surface (never the
// markdown detail pane); everything else uses the detail pane.
function opensInCenterColumn(event) {
  return event?.noteType === "mindmap" || event?.noteType === "canvas";
}

function buildRouteSelectionSpec() {
  const eventId = parseRouteNumber("event");
  const routeTopicId = parseRouteNumber("topic");
  const mode = parseRouteMode();
  const event = eventId ? timelineStore.eventById(eventId) || null : null;
  const topicId = event?.topicId || routeTopicId || null;
  const openMindmap = opensInCenterColumn(event);
  return {
    event,
    eventId,
    mode,
    openDetail: openMindmap ? false : mode !== "view" || eventId !== null,
    openMindmap,
    topicId,
  };
}

function routeSelectionMatchesState(spec) {
  const expectedMode =
    spec.mode === "create"
      ? "create"
      : spec.mode === "edit" && spec.eventId
        ? "edit"
        : "view";
  const topicMatches = spec.topicId ? state.activeTopicId === spec.topicId : true;
  const eventMatches = spec.eventId ? state.selectedEventId === spec.eventId : true;

  if (spec.openMindmap) {
    return topicMatches && eventMatches && state.mindmapOpenId === spec.eventId && !state.rightOpen && state.detailMode === "view";
  }

  return (
    topicMatches &&
    eventMatches &&
    state.mindmapOpenId == null &&
    state.detailMode === expectedMode &&
    state.rightOpen === Boolean(spec.openDetail && (spec.eventId || expectedMode === "create"))
  );
}

async function ensureTopicEventsReady(topicId, { force = false, throwOnError = false } = {}) {
  const id = Number(topicId);
  if (!id) return true;
  if (timelineStore.isTopicEventsLoaded(id) && !force) {
    if (state.activeTopicId === id) syncActiveTopicFromStore();
    return true;
  }
  const seq = ++topicEventsRequestSeq;
  state.eventsLoading = true;
  try {
    await timelineStore.ensureTopicEvents(id, { force, dir: feedFetchDir.value });
    if (state.activeTopicId === id) syncActiveTopicFromStore();
    state.error = "";
    return true;
  } catch (error) {
    const message = error.message || "事件加载失败";
    if (state.activeTopicId === id) state.error = message;
    if (throwOnError) throw error;
    pushToast(`事件加载失败：${message}`, "error");
    return false;
  } finally {
    if (seq === topicEventsRequestSeq) state.eventsLoading = false;
  }
}

async function loadMoreActiveTopicEvents({ auto = false } = {}) {
  const topicId = Number(state.activeTopicId);
  if (
    !topicId ||
    state.loadingMore ||
    isGlobalFavoritesMode.value ||
    !timelineStore.topicHasMore(topicId) ||
    (auto && state.autoLoadBlockedKey === autoLoadContextKey.value)
  ) {
    return;
  }
  state.loadingMore = true;
  try {
    await timelineStore.ensureTopicEvents(topicId, { append: true, dir: feedFetchDir.value });
    if (state.autoLoadBlockedKey === autoLoadContextKey.value) state.autoLoadBlockedKey = "";
    syncActiveTopicFromStore();
  } catch (error) {
    if (auto) state.autoLoadBlockedKey = autoLoadContextKey.value;
    pushToast(`更多事件加载失败：${error.message}`, "error");
  } finally {
    state.loadingMore = false;
  }
}

async function ensureGlobalIndexReady() {
  if (timelineStore.state.indexLoaded) return true;
  const seq = ++topicEventsRequestSeq;
  state.eventsLoading = true;
  try {
    await timelineStore.loadIndex();
    syncActiveTopicFromStore();
    state.error = "";
    return true;
  } catch (error) {
    const message = error.message || "索引加载失败";
    state.error = message;
    pushToast(`索引加载失败：${message}`, "error");
    return false;
  } finally {
    if (seq === topicEventsRequestSeq) state.eventsLoading = false;
  }
}

async function applyWorkspaceSelectionWithEvents(options = {}, loadOptions = {}) {
  const seq = ++workspaceSelectionRequestSeq;
  applyWorkspaceSelection(options);
  const topicId = state.activeTopicId;
  if (!topicId) return seq === workspaceSelectionRequestSeq;
  const ok = await ensureTopicEventsReady(topicId, loadOptions);
  if (!ok || seq !== workspaceSelectionRequestSeq || state.activeTopicId !== topicId) return false;
  if (ok) applyWorkspaceSelection(options);
  return ok;
}

async function ensureRouteSelectionData() {
  const routeTopicId = parseRouteNumber("topic");
  const routeEventId = parseRouteNumber("event");
  if (routeTopicId) {
    const ready = await ensureTopicEventsReady(routeTopicId);
    if (!ready || !routeEventId || timelineStore.eventById(routeEventId)) return ready;
    try {
      await timelineStore.ensureEventDetail(routeEventId);
      return true;
    } catch (error) {
      pushToast(`详情加载失败：${error.message}`, "error");
      return false;
    }
  }
  if (!routeEventId || timelineStore.eventById(routeEventId)) return true;
  try {
    await timelineStore.ensureEventDetail(routeEventId);
    return true;
  } catch (error) {
    pushToast(`详情加载失败：${error.message}`, "error");
    return false;
  }
}

async function applyRouteSelectionFromQuery() {
  if (!timelineStore.state.topicsLoaded || !state.topics.length) return;
  const routeReady = await ensureRouteSelectionData();
  if (!routeReady) return;
  const spec = buildRouteSelectionSpec();
  if (routeSelectionMatchesState(spec)) return;

  if (spec.event?.topicId && (isGlobalFavoritesMode.value || spec.event.topicId !== state.activeTopicId)) {
    state.collectionMode = "";
    state.sidebarFilter = "all";
    state.propertyFilter = { key: "", value: "" };
    state.activeEra = "";
    state.locateDate = "";
    state.searchQuery = "";
  }

  await applyWorkspaceSelectionWithEvents({
    preferredEventId: spec.eventId,
    preferredMode: spec.mode,
    preferredTopicId: spec.topicId,
    openDetail: spec.openDetail,
  });

  if (spec.openMindmap && spec.eventId) {
    state.selectedEventId = spec.eventId;
    state.detailMode = "view";
    state.detailError = "";
    state.rightOpen = false;
    state.mindmapOpenId = spec.eventId;
    await timelineStore.ensureEventDetail(spec.eventId);
    return;
  }

  closeMindmap();
}

function syncActiveTopicFromStore() {
  state.topics = [...timelineStore.state.topics];
  state.activeTopicMeta = state.activeTopicId ? timelineStore.topicById(state.activeTopicId) : null;
  ensureBookshelfExpandedForTopic(state.activeTopicId);
  state.events = state.activeTopicId ? timelineStore.eventsForTopic(state.activeTopicId) : [];
  state.eventBounds = state.activeTopicMeta
    ? {
        eventCount: state.activeTopicMeta.eventCount,
        minDateKey: state.activeTopicMeta.minDateKey,
        maxDateKey: state.activeTopicMeta.maxDateKey,
        minDate: state.activeTopicMeta.minDate,
        maxDate: state.activeTopicMeta.maxDate,
      }
    : null;
  state.hasMore = state.activeTopicId ? timelineStore.topicHasMore(state.activeTopicId) : false;
  state.nextCursor = state.activeTopicId ? timelineStore.topicNextCursor(state.activeTopicId) : null;
}

function applyWorkspaceSelection(options = {}) {
  const {
    preferredTopicId = null,
    preferredEventId = parseRouteNumber("event"),
    preferredMode = parseRouteMode(),
    openDetail = preferredMode !== "view" || preferredEventId !== null,
  } = options;
  const topics = timelineStore.state.topics;
  const routeTopicId = parseRouteNumber("topic");
  const resolvedTopicId =
    preferredTopicId && topics.some((topic) => topic.id === preferredTopicId)
      ? preferredTopicId
      : routeTopicId && topics.some((topic) => topic.id === routeTopicId)
        ? routeTopicId
        : topics[0]?.id ?? null;

  state.activeTopicId = resolvedTopicId;
  syncActiveTopicFromStore();

  if (!resolvedTopicId) {
    state.activeTopicMeta = null;
    state.events = [];
    state.selectedEventId = null;
    state.rightOpen = false;
    return;
  }

  setDefaultSelection(preferredEventId);
  state.detailMode =
    preferredMode === "create"
      ? "create"
      : preferredMode === "edit" && state.selectedEventId
        ? "edit"
        : "view";
  state.rightOpen = Boolean(openDetail && (state.selectedEventId || state.detailMode === "create"));
  document.title = `${state.config.brandName} Chronicle`;
}

async function loadWorkspace(options = {}) {
  state.loading = true;
  state.error = "";
  state.detailError = "";
  state.sidebarFilter = parseRouteFilter();
  state.propertyFilter = parseRoutePropertyFilter();
  state.activeEra = parseRouteString("era");
  state.locateDate = parseRouteString("date");

  try {
    const [config] = await Promise.all([
      api.getConfig(),
      refreshBookshelfTree({ syncTopics: true }),
    ]);
    state.config = {
      ...state.config,
      ...config,
      brandName: "编年",
      navPosition: normalizeNavPosition(config?.navPosition),
      detailPosition: normalizeDetailPosition(config?.detailPosition),
      sidebarSort: normalizeSidebarSort(config?.sidebarSort),
      media: normalizeMediaConfig(config?.media),
    };
    // Mirror the cross-device truth into localStorage so the next load paints the
    // correct sidebar edge on frame 1 instead of flashing the default and swapping.
    writeStorage(NAV_POSITION_KEY, state.config.navPosition);
    writeStorage(DETAIL_POSITION_KEY, state.config.detailPosition);
    writeStorage(SIDEBAR_SORT_KEY, state.config.sidebarSort);
    await applyWorkspaceSelectionWithEvents(options, { throwOnError: true });
    await applyRouteSelectionFromQuery();
  } catch (error) {
    state.error = error.message || "加载失败";
    pushToast(`加载失败：${error.message}`, "error");
  } finally {
    state.loading = false;
  }
}

function runOrConfirm(action, options = {}) {
  const { restoreRouteOnCancel = false, routeRestoreSnapshot = null } = options;
  if ((state.detailMode === "edit" || state.detailMode === "create") && state.detailDirty) {
    closeRelatedPreview();
    state.pendingAction = action;
    state.restoreRouteOnCancel = restoreRouteOnCancel;
    state.routeRestoreSnapshot = routeRestoreSnapshot;
    state.confirmUnsaved = true;
    return;
  }
  state.restoreRouteOnCancel = false;
  state.routeRestoreSnapshot = null;
  action();
}

function exitGlobalFavoritesMode({ reselect = true } = {}) {
  if (!isGlobalFavoritesMode.value) return;
  state.collectionMode = "";
  if (reselect) setDefaultSelection();
}

function handleSidebarRibbon(ribbon) {
  if (ribbon === "tags") void ensureGlobalIndexReady();
  if (ribbon !== "star") exitGlobalFavoritesMode();
}

function openGlobalFavorites() {
  runOrConfirm(async () => {
    const ready = await ensureGlobalIndexReady();
    if (!ready) return;
    state.collectionMode = "favorites";
    closeMindmap();
    state.favoriteScope = { kind: "all" };
    state.sidebarFilter = "all";
    state.propertyFilter = { key: "", value: "" };
    state.activeEra = "";
    state.locateDate = "";
    state.searchQuery = "";
    state.detailMode = "view";
    state.rightOpen = false;
    setDefaultSelection();
    closeMobileSidebar();
    await syncRouteState({
      eventId: null,
      mode: "view",
      filter: "all",
      propertyFilter: { key: "", value: "" },
      era: "",
      date: "",
    });
  });
}

function closeUnsavedDialog() {
  const shouldRestoreRoute = state.restoreRouteOnCancel;
  const restoreSnapshot = state.routeRestoreSnapshot;
  state.confirmUnsaved = false;
  state.pendingAction = null;
  state.restoreRouteOnCancel = false;
  state.routeRestoreSnapshot = null;
  if (shouldRestoreRoute) void syncRouteState(restoreSnapshot || {});
}

function openMobileSidebar() {
  if (isMobile.value) state.mobileSidebarOpen = true;
}

function closeMobileSidebar() {
  state.mobileSidebarOpen = false;
}

function rememberMobileFeedScroll() {
  if (!isMobile.value) return;
  mobileFeedScrollTop.value = feedPaneRef.value?.rememberScroll?.() ?? feedPaneRef.value?.currentScrollTop?.() ?? mobileFeedScrollTop.value;
}

async function restoreMobileFeedScroll() {
  if (!isMobile.value) return;
  await nextTick();
  await feedPaneRef.value?.restoreScroll?.(mobileFeedScrollTop.value);
}

function openSettings() {
  closeMobileSidebar();
  state.settingsOpen = true;
}

function clearCommandSearchTimer() {
  if (commandSearchTimer) {
    window.clearTimeout(commandSearchTimer);
    commandSearchTimer = null;
  }
}

function openCommandPalette(initialQuery = "") {
  state.commandOpen = true;
  state.commandQuery = String(initialQuery || "");
  state.commandResults = [];
  state.commandError = "";
}

function closeCommandPalette() {
  clearCommandSearchTimer();
  commandRequestSeq += 1;
  state.commandOpen = false;
  state.commandLoading = false;
}

async function performCommandSearch(query, seq) {
  const trimmed = String(query || "").trim();
  if (!trimmed) {
    state.commandResults = [];
    state.commandError = "";
    state.commandLoading = false;
    return;
  }

  state.commandLoading = true;
  state.commandError = "";
  try {
    const rows = await api.search(trimmed, { limit: 8 });
    if (seq !== commandRequestSeq) return;
    state.commandResults = Array.isArray(rows) ? rows : [];
  } catch (error) {
    if (seq !== commandRequestSeq) return;
    state.commandResults = [];
    state.commandError = error.message || "搜索失败";
  } finally {
    if (seq === commandRequestSeq) state.commandLoading = false;
  }
}

function handleGlobalKeydown(event) {
  if (!((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k")) return;
  event.preventDefault();
  openCommandPalette();
}

function selectCommandEvent(result) {
  const topicId = Number(result?.topicId);
  const eventId = Number(result?.id);
  if (!topicId || !eventId) return;
  runOrConfirm(async () => {
    closeCommandPalette();
    state.collectionMode = "";
    state.sidebarFilter = "all";
    state.propertyFilter = { key: "", value: "" };
    state.activeEra = "";
    state.locateDate = "";
    state.searchQuery = "";
    const ready = await applyWorkspaceSelectionWithEvents({
      preferredTopicId: topicId,
      preferredEventId: eventId,
      preferredMode: "view",
      openDetail: false,
    });
    if (!ready) return;
    const event = timelineStore.eventById(eventId);
    if (!event) {
      pushToast("未找到目标笔记", "error");
      return;
    }
    closeMobileSidebar();
    // A mindmap or canvas opens its own center surface, never the markdown detail pane.
    if (opensInCenterColumn(event)) {
      await openMindmap(eventId);
      return;
    }
    closeMindmap();
    state.detailError = "";
    state.rightOpen = true;
    await syncRouteState({
      topicId,
      eventId,
      filter: "all",
      propertyFilter: { key: "", value: "" },
      era: "",
      date: "",
      mode: "view",
    });
  });
}

function selectCommandTopic(topic) {
  const topicId = Number(topic?.id);
  if (!topicId) return;
  runOrConfirm(async () => {
    closeCommandPalette();
    exitGlobalFavoritesMode({ reselect: false });
    state.propertyFilter = { key: "", value: "" };
    state.activeEra = "";
    state.searchQuery = "";
    const ready = await applyWorkspaceSelectionWithEvents({
      preferredTopicId: topicId,
      preferredEventId: null,
      preferredMode: "view",
      openDetail: false,
    });
    if (!ready) return;
    state.rightOpen = false;
    closeMobileSidebar();
    await syncRouteState({ topicId, eventId: null, propertyFilter: { key: "", value: "" }, era: "", mode: "view" });
  });
}

function handleCommandPaletteCommand(command) {
  closeCommandPalette();
  if (command === "new-event") {
    startCreateEvent();
    return;
  }
  if (command === "new-topic") {
    exitGlobalFavoritesMode({ reselect: false });
    closeMobileSidebar();
    state.topicCreateRequestKey += 1;
    return;
  }
  if (command === "settings") {
    openSettings();
    return;
  }
  if (command === "export") exportCurrentTopic();
}

function discardAndContinue() {
  const action = state.pendingAction;
  state.detailDirty = false;
  state.confirmUnsaved = false;
  state.pendingAction = null;
  state.restoreRouteOnCancel = false;
  state.routeRestoreSnapshot = null;
  detailPaneRef.value?.discardDraft?.();
  if (action) action();
}

function saveAndContinue() {
  const action = state.pendingAction;
  const didSubmit = detailPaneRef.value?.submit?.();
  if (!didSubmit) {
    state.afterSaveAction = null;
    return;
  }
  state.afterSaveAction = action;
  state.confirmUnsaved = false;
  state.pendingAction = null;
  state.restoreRouteOnCancel = false;
  state.routeRestoreSnapshot = null;
}

async function applyEventSelection(eventId) {
  const id = Number(eventId);
  rememberMobileFeedScroll();
  let event = timelineStore.eventById(id);
  if (!event) {
    try {
      event = await timelineStore.ensureEventDetail(id);
    } catch (error) {
      pushToast(`详情加载失败：${error.message}`, "error");
      return;
    }
  }
  // A mindmap or canvas opens its own center surface (D-2), never the markdown detail
  // pane. Bring its notebook to the front first if it lives in another one.
  if (opensInCenterColumn(event)) {
    if (event.topicId && (isGlobalFavoritesMode.value || event.topicId !== state.activeTopicId)) {
      exitGlobalFavoritesMode({ reselect: false });
      state.sidebarFilter = "all";
      state.propertyFilter = { key: "", value: "" };
      state.activeEra = "";
      state.locateDate = "";
      state.searchQuery = "";
      const ready = await applyWorkspaceSelectionWithEvents({
        preferredTopicId: event.topicId,
        preferredEventId: id,
        preferredMode: "view",
        openDetail: false,
      });
      if (!ready) return;
    }
    await openMindmap(id);
    return;
  }
  if (event?.topicId && (isGlobalFavoritesMode.value || event.topicId !== state.activeTopicId)) {
    state.collectionMode = "";
    state.sidebarFilter = "all";
    state.propertyFilter = { key: "", value: "" };
    state.activeEra = "";
    state.locateDate = "";
    state.searchQuery = "";
    const ready = await applyWorkspaceSelectionWithEvents({
      preferredTopicId: event.topicId,
      preferredEventId: event.id,
      preferredMode: "view",
      openDetail: true,
    });
    if (!ready) return;
    state.detailError = "";
    state.rightOpen = true;
    closeMobileSidebar();
    await syncRouteState({
      topicId: event.topicId,
      eventId: event.id,
      filter: "all",
      propertyFilter: { key: "", value: "" },
      era: "",
      date: "",
      mode: "view",
    });
    return;
  }

  state.selectedEventId = id;
  state.detailMode = "view";
  state.detailError = "";
  state.rightOpen = true;
  await syncRouteState({ eventId: id, mode: "view" });
}

function selectEvent(eventId) {
  runOrConfirm(() => applyEventSelection(eventId));
}

// Open a structured note's surface in the center column (no markdown detail pane).
// Type-agnostic: drives both mindmap and canvas (mindmapNote/canvasNote discriminate
// which surface mounts). Context (notebook switch) is handled by the caller; here we
// just load the full detail (for bodyJson) and flip the center surface.
async function openMindmap(eventId) {
  const id = Number(eventId);
  state.selectedEventId = id;
  state.detailMode = "view";
  state.detailError = "";
  state.rightOpen = false;
  state.mindmapOpenId = id;
  await timelineStore.ensureEventDetail(id);
  await syncRouteState({ eventId: id, mode: "view" });
}

function closeMindmap() {
  state.mindmapOpenId = null;
}

// Create a mindmap note seeded with one X6 root snapshot, then open its canvas.
// Mindmaps are undated by default so they can live as free-form canvases; dated
// legacy maps still round-trip because persistMindmapTree forwards an existing date.
function createMindmapNote(topicId = state.activeTopicId) {
  const targetTopicId = Number(topicId || state.activeTopicId);
  if (!targetTopicId) {
    pushToast("请先选择一个笔记本", "error");
    return;
  }
  runOrConfirm(async () => {
    exitGlobalFavoritesMode({ reselect: false });
    if (targetTopicId !== state.activeTopicId) {
      state.propertyFilter = { key: "", value: "" };
      state.activeEra = "";
      state.searchQuery = "";
      const ready = await applyWorkspaceSelectionWithEvents({
        preferredTopicId: targetTopicId,
        preferredEventId: null,
        preferredMode: "view",
        openDetail: false,
      });
      if (!ready) return;
    }
    closeMobileSidebar();
    try {
      const result = await api.createTopicEvent(targetTopicId, {
        headline: "未命名导图",
        noteType: "mindmap",
        bodyJson: buildX6SeedSnapshot("中心主题"),
      });
      timelineStore.upsertEvent(result);
      syncActiveTopicFromStore();
      await openMindmap(result.id);
      pushToast("已创建思维导图");
    } catch (error) {
      pushToast(`创建失败：${error.message}`, "error");
    }
  });
}

// Create a canvas note seeded with one starter card, then open its board. Canvases are
// undated free-form boards; persistCanvasSnapshot autosaves the X6 snapshot.
function createCanvasNote(topicId = state.activeTopicId) {
  const targetTopicId = Number(topicId || state.activeTopicId);
  if (!targetTopicId) {
    pushToast("请先选择一个笔记本", "error");
    return;
  }
  runOrConfirm(async () => {
    exitGlobalFavoritesMode({ reselect: false });
    if (targetTopicId !== state.activeTopicId) {
      state.propertyFilter = { key: "", value: "" };
      state.activeEra = "";
      state.searchQuery = "";
      const ready = await applyWorkspaceSelectionWithEvents({
        preferredTopicId: targetTopicId,
        preferredEventId: null,
        preferredMode: "view",
        openDetail: false,
      });
      if (!ready) return;
    }
    closeMobileSidebar();
    try {
      const result = await api.createTopicEvent(targetTopicId, {
        headline: "未命名画布",
        noteType: "canvas",
        bodyJson: buildCanvasSeedSnapshot(),
      });
      timelineStore.upsertEvent(result);
      syncActiveTopicFromStore();
      await openMindmap(result.id);
      pushToast("已创建画布");
    } catch (error) {
      pushToast(`创建失败：${error.message}`, "error");
    }
  });
}

// Legacy snapshots may store rich-text HTML in node text; the note headline stays
// plain text, so decode tags + entities before tracking the root label.
function htmlToPlainText(html) {
  const raw = String(html || "");
  if (typeof document === "undefined") return raw.replace(/<[^>]*>/g, "").replace(/\s+/g, " ").trim();
  const tmp = document.createElement("div");
  tmp.innerHTML = raw;
  return (tmp.textContent || "").replace(/\s+/g, " ").trim();
}

// Saves are serialized through a chain so the editor's debounced data_change bursts
// can't land out of order. The save carries the bound note id (the editor is keyed
// per note) so a flush during a note switch — or after the canvas closed — writes to
// the right note, never the newly-opened one. The headline tracks the root node text.
let mindmapSaveChain = Promise.resolve();
function saveMindmapTree(payload) {
  mindmapSaveChain = mindmapSaveChain.then(() => persistMindmapTree(payload));
  return mindmapSaveChain;
}

async function persistMindmapTree({ id, tree } = {}) {
  const note = id ? timelineStore.detailById(id) : null;
  if (!note || note.deletedAt) return;
  state.mindmapSaving = true;
  try {
    // tree may be a legacy tree/snapshot or the new X6 snapshot; mindmapRootData
    // normalizes all supported shapes so headline sync stays stable through migration.
    const rootText = htmlToPlainText(mindmapRootData(tree)?.data?.text) || note.headline || "未命名导图";
    const payload = {
      headline: rootText,
      era: note.era || "",
      noteType: "mindmap",
      bodyJson: tree,
      extra: note.extra || {},
      // updateEvent is a full replace — forward the note's existing attachments and
      // related links so a tree autosave can't blank them.
      attachments: note.attachments || [],
      relatedEventIds: note.relatedEventIds || [],
    };
    if (note.hasDate && note.dateParts?.year != null) {
      payload.dateYear = note.dateParts.year;
      payload.dateMonth = note.dateParts.month;
      payload.dateDay = note.dateParts.day;
    }
    const result = await api.updateEvent(id, payload);
    timelineStore.upsertEvent(result);
    syncActiveTopicFromStore();
  } catch (error) {
    pushToast(`保存失败：${error.message}`, "error");
  } finally {
    state.mindmapSaving = false;
  }
}

// Canvas autosave, mirroring the mindmap save chain (serialized so debounced snapshot
// bursts can't land out of order; the bound note id keeps a late flush on the right
// note). The headline tracks the first card so the note's title reflects its board.
let canvasSaveChain = Promise.resolve();
function saveCanvasSnapshot(payload) {
  canvasSaveChain = canvasSaveChain.then(() => persistCanvasSnapshot(payload));
  return canvasSaveChain;
}

async function persistCanvasSnapshot({ id, tree } = {}) {
  const note = id ? timelineStore.detailById(id) : null;
  if (!note || note.deletedAt) return;
  state.mindmapSaving = true;
  try {
    const firstCard = (tree?.cells || []).find((cell) => cell && cell.shape !== "edge");
    const headline = htmlToPlainText(firstCard?.data?.text) || note.headline || "未命名画布";
    const payload = {
      headline,
      era: note.era || "",
      noteType: "canvas",
      bodyJson: tree,
      extra: note.extra || {},
      // updateEvent is a full replace — forward existing attachments/links so a board
      // autosave can't blank them.
      attachments: note.attachments || [],
      relatedEventIds: note.relatedEventIds || [],
    };
    if (note.hasDate && note.dateParts?.year != null) {
      payload.dateYear = note.dateParts.year;
      payload.dateMonth = note.dateParts.month;
      payload.dateDay = note.dateParts.day;
    }
    const result = await api.updateEvent(id, payload);
    timelineStore.upsertEvent(result);
    syncActiveTopicFromStore();
  } catch (error) {
    pushToast(`保存失败：${error.message}`, "error");
  } finally {
    state.mindmapSaving = false;
  }
}

function relatedPreviewPosition(anchor) {
  if (typeof window === "undefined") {
    return { placement: "left", style: {} };
  }
  const width = 360;
  const estimatedHeight = 268;
  const gap = 14;
  const margin = 12;
  const viewportWidth = window.innerWidth || 1920;
  const viewportHeight = window.innerHeight || 1080;
  // Fallback anchor = the detail pane's horizontal span, which depends on which of
  // the four nav/detail layout combos is active (docs/layout-swap-design.md §7).
  const navRight = state.config.navPosition === "right";
  const detailCenter = state.config.detailPosition === "center";
  const paintedLeft = isCompactDesktop.value ? clamp(state.leftWidth, 220, 240) : state.leftWidth;
  let detailLeft;
  if (detailCenter) {
    detailLeft = navRight ? viewportWidth - paintedLeft - state.rightWidth : paintedLeft;
  } else {
    detailLeft = navRight ? 0 : viewportWidth - state.rightWidth;
  }
  const target = anchor || {
    top: viewportHeight * 0.35,
    bottom: viewportHeight * 0.35 + 40,
    left: detailLeft,
    right: detailLeft + state.rightWidth - margin,
    height: 40,
  };
  const canPlaceLeft = target.left - width - gap >= margin;
  const placement = canPlaceLeft ? "left" : "right";
  const rawLeft = placement === "left" ? target.left - width - gap : target.right + gap;
  const left = clamp(rawLeft, margin, Math.max(margin, viewportWidth - width - margin));
  const top = clamp(target.top - 8, margin, Math.max(margin, viewportHeight - estimatedHeight - margin));
  const anchorY = clamp(target.top + target.height / 2 - top, 22, estimatedHeight - 22);
  return {
    placement,
    style: {
      left: `${Math.round(left)}px`,
      top: `${Math.round(top)}px`,
      "--related-anchor-y": `${Math.round(anchorY)}px`,
    },
  };
}

async function openRelatedPreview(payload, { pinned = false } = {}) {
  if (state.relatedPreviewPinned && !pinned) return;
  const id = Number(payload?.id ?? payload);
  if (!id) return;
  const seq = ++relatedPreviewRequestSeq;
  const position = relatedPreviewPosition(payload?.anchor);
  state.relatedPreviewEventId = id;
  state.relatedPreviewOpen = true;
  state.relatedPreviewPinned = Boolean(pinned);
  state.relatedPreviewPlacement = position.placement;
  state.relatedPreviewStyle = position.style;
  state.relatedPreviewError = "";

  if (timelineStore.detailById(id)) {
    state.relatedPreviewLoading = false;
    return;
  }

  state.relatedPreviewLoading = true;
  try {
    await timelineStore.ensureEventDetail(id);
    if (seq === relatedPreviewRequestSeq) syncActiveTopicFromStore();
  } catch (error) {
    if (seq === relatedPreviewRequestSeq) {
      state.relatedPreviewError = error.message || "关联事件加载失败";
    }
  } finally {
    if (seq === relatedPreviewRequestSeq) state.relatedPreviewLoading = false;
  }
}

function previewRelatedEvent(payload) {
  openRelatedPreview(payload, { pinned: false });
}

function pinRelatedEvent(payload) {
  openRelatedPreview(payload, { pinned: true });
}

function hideRelatedPreview(eventId) {
  if (state.relatedPreviewPinned) return;
  if (eventId && Number(eventId) !== Number(state.relatedPreviewEventId)) return;
  closeRelatedPreview();
}

function closeRelatedPreview() {
  relatedPreviewRequestSeq += 1;
  state.relatedPreviewOpen = false;
  state.relatedPreviewEventId = null;
  state.relatedPreviewLoading = false;
  state.relatedPreviewError = "";
  state.relatedPreviewPinned = false;
  state.relatedPreviewStyle = {};
}

function openRelatedPreviewFull() {
  const id = Number(state.relatedPreviewEventId);
  if (!id) return;
  closeRelatedPreview();
  runOrConfirm(() => applyEventSelection(id));
}

function closeDetailPane() {
  runOrConfirm(async () => {
    state.rightOpen = false;
    state.detailMode = "view";
    await syncRouteState({ eventId: null, mode: "view" });
  });
}

function startCreateEvent() {
  runOrConfirm(async () => {
    if (!state.activeTopicId) {
      pushToast("请先选择一个笔记本", "error");
      return;
    }
    exitGlobalFavoritesMode();
    closeMobileSidebar();
    state.mobileSearchOpen = false;
    rememberMobileFeedScroll();
    state.detailMode = "create";
    state.rightOpen = true;
    await syncRouteState({ eventId: state.selectedEventId, mode: "create" });
  });
}

// Row "⊕" affordance: create a note inside a specific notebook, switching to it
// first if it isn't already active (mirrors selectTopic + startCreateEvent).
function createEventInTopic(topicId) {
  if (!topicId) return;
  runOrConfirm(async () => {
    exitGlobalFavoritesMode({ reselect: false });
    if (topicId !== state.activeTopicId) {
      state.propertyFilter = { key: "", value: "" };
      state.activeEra = "";
      state.searchQuery = "";
      const ready = await applyWorkspaceSelectionWithEvents({
        preferredTopicId: topicId,
        preferredEventId: null,
        preferredMode: "view",
        openDetail: false,
      });
      if (!ready) return;
    }
    closeMobileSidebar();
    state.mobileSearchOpen = false;
    rememberMobileFeedScroll();
    state.detailMode = "create";
    state.rightOpen = true;
    await syncRouteState({ topicId, eventId: state.selectedEventId, mode: "create" });
  });
}

function startEditSelectedEvent() {
  if (!selectedEvent.value || selectedEvent.value.deletedAt) return;
  rememberMobileFeedScroll();
  state.detailMode = "edit";
  state.rightOpen = true;
  syncRouteState({ eventId: state.selectedEventId, mode: "edit" });
}

function cancelDetailEdit() {
  runOrConfirm(async () => {
    state.detailMode = "view";
    state.rightOpen = Boolean(state.selectedEventId);
    await syncRouteState({ eventId: state.rightOpen ? state.selectedEventId : null, mode: "view" });
  });
}

async function cleanupDeletedImages(imageOps, currentImage) {
  const pending = [...new Set((imageOps?.deleteImages || []).filter((filename) => filename && filename !== currentImage))];
  if (!pending.length) return;
  await Promise.allSettled(pending.map((filename) => api.deleteImage(filename)));
}

async function saveEvent(payload) {
  if (!state.activeTopicId) return;
  state.saving = true;
  try {
    const result = payload.id
      ? await api.updateEvent(payload.id, payload.data)
      : await api.createTopicEvent(state.activeTopicId, payload.data);

    await cleanupDeletedImages(payload.imageOps, payload.data.image);
    detailPaneRef.value?.markSaved?.();
    state.detailDirty = false;
    timelineStore.upsertEvent(result);
    await refreshSidebarData({ reloadTopics: true });
    syncActiveTopicFromStore();
    state.selectedEventId = result.id;
    state.detailMode = "view";
    state.rightOpen = true;
    await syncRouteState({ eventId: result.id, mode: "view" });
    pushToast(payload.id ? "事件已更新" : "事件已创建");

    const nextAction = state.afterSaveAction;
    state.afterSaveAction = null;
    if (nextAction) {
      await nextTick();
      nextAction();
    }
  } catch (error) {
    state.afterSaveAction = null;
    pushToast(`保存失败：${error.message}`, "error");
  } finally {
    state.saving = false;
  }
}

async function selectTopic(topicId) {
  if (topicId === state.activeTopicId && !isGlobalFavoritesMode.value) return;
  runOrConfirm(async () => {
    closeMindmap();
    exitGlobalFavoritesMode({ reselect: false });
    state.propertyFilter = { key: "", value: "" };
    state.activeEra = "";
    state.searchQuery = "";
    const ready = await applyWorkspaceSelectionWithEvents({
      preferredTopicId: topicId,
      preferredEventId: null,
      preferredMode: "view",
      openDetail: false,
    });
    if (!ready) return;
    state.rightOpen = false;
    closeMobileSidebar();
    await syncRouteState({ topicId, eventId: null, propertyFilter: { key: "", value: "" }, era: "", mode: "view" });
  });
}

function bookshelfByName(name) {
  return findBookshelfByName(state.bookshelves, name, bookshelfTree.value);
}

async function createTopic(input) {
  const request = resolveCreateTopicRequest(input, activeBookshelfName.value, state.bookshelves, bookshelfTree.value);
  const topicName = request.topicName;
  if (!topicName) return;
  try {
    const created = await api.createTopic(topicName, request.bookshelfId);
    timelineStore.upsertTopic({ ...created, eventCount: 0, minDateKey: null, maxDateKey: null, minDate: null, maxDate: null });
    await refreshSidebarData({ reloadTopics: true });
    if (created?.bookshelfName) state.focusedBookshelfName = created.bookshelfName;
    const ready = await applyWorkspaceSelectionWithEvents({
      preferredTopicId: created.id,
      preferredEventId: null,
      preferredMode: "view",
      openDetail: false,
    });
    if (!ready) return;
    pushToast(`已创建笔记本：${topicName}`);
    state.rightOpen = false;
    closeMobileSidebar();
    await syncRouteState({ topicId: created.id, eventId: null });
  } catch (error) {
    pushToast(`创建笔记本失败：${error.message}`, "error");
  }
}

async function createBookshelf(name) {
  try {
    const created = await api.createBookshelf(name);
    await refreshBookshelfTree();
    state.focusedBookshelfName = created.name || "";
    persistBookshelfCollapsed({
      ...state.bookshelfCollapsed,
      [created.name]: false,
    });
    pushToast(`已创建书架：${created.title || name}`);
    closeMobileSidebar();
  } catch (error) {
    pushToast(`创建书架失败：${error.message}`, "error");
  }
}

async function renameBookshelf({ name, title } = {}) {
  const bookshelf = bookshelfByName(name);
  const nextTitle = String(title || "").trim();
  if (!bookshelf?.id || !nextTitle) return;
  try {
    const updated = await api.updateBookshelf(bookshelf.id, { title: nextTitle });
    await refreshBookshelfTree();
    if (state.focusedBookshelfName === bookshelf.name) state.focusedBookshelfName = updated.name || bookshelf.name;
    pushToast(`已重命名书架：${updated.title || nextTitle}`);
  } catch (error) {
    pushToast(`重命名书架失败：${error.message}`, "error");
  }
}

// Inline rename from the row "⋯" menu. Sends only the title (meta fields are
// independently optional server-side, so columns/subtitle are untouched) and
// patches the local list in place — no event reload, order is by id asc.
async function renameTopic({ id, title } = {}) {
  const name = (title || "").trim();
  if (!id || !name) return;
  try {
    const meta = await api.updateTopicMeta(id, { title: name });
    timelineStore.upsertTopic(meta);
    await refreshSidebarData({ reloadTopics: true });
    syncActiveTopicFromStore();
    pushToast(`已重命名为：${meta.title}`);
  } catch (error) {
    pushToast(`重命名失败：${error.message}`, "error");
  }
}

function applyFilterState({ filter = state.sidebarFilter, propertyFilter = state.propertyFilter, era = state.activeEra, date = state.locateDate } = {}) {
  state.sidebarFilter = filter;
  state.propertyFilter = propertyFilter;
  state.activeEra = era;
  state.locateDate = date;
  setDefaultSelection();
  if (!visibleEvents.value.length) {
    state.rightOpen = false;
    state.detailMode = "view";
  } else if (state.rightOpen && !visibleEvents.value.some((event) => event.id === state.selectedEventId)) {
    state.selectedEventId = visibleEvents.value[0].id;
  }
}

function applyFavoriteScope(scope = state.favoriteScope) {
  state.favoriteScope = normalizeFavoriteScope(scope);
  setDefaultSelection();
  if (!visibleEvents.value.length) {
    state.rightOpen = false;
    state.detailMode = "view";
  } else if (state.rightOpen && !visibleEvents.value.some((event) => event.id === state.selectedEventId)) {
    state.selectedEventId = visibleEvents.value[0].id;
  }
}

function updateSidebarFilter(filter) {
  runOrConfirm(async () => {
    exitGlobalFavoritesMode();
    applyFilterState({ filter });
    closeMobileSidebar();
    await syncRouteState({ filter, eventId: state.rightOpen ? state.selectedEventId : null });
  });
}

function updatePropertyFilter(propertyFilter) {
  runOrConfirm(async () => {
    exitGlobalFavoritesMode();
    applyFilterState({ propertyFilter });
    closeMobileSidebar();
    await syncRouteState({ propertyFilter, eventId: state.rightOpen ? state.selectedEventId : null });
  });
}

function updateSearchQuery(value) {
  state.searchQuery = value;
  setDefaultSelection();
  if (!visibleEvents.value.length) {
    state.rightOpen = false;
  }
}

function updateFavoriteScope(scope) {
  runOrConfirm(() => {
    if (!isGlobalFavoritesMode.value) state.collectionMode = "favorites";
    applyFavoriteScope(scope);
    closeMobileSidebar();
  });
}

function clearFavoriteScope() {
  if (favoriteScope.value.kind === "all") return;
  updateFavoriteScope({ kind: "all" });
}

function locateDate(value) {
  state.locateDate = value;
  syncRouteState({ date: value });
}

async function toggleFavorite(event) {
  if (!event || event.deletedAt) return;
  try {
    const wasGlobalFavorites = isGlobalFavoritesMode.value;
    const result = await api.updateEventFavorite(event.id, !event.favorite);
    timelineStore.upsertEvent(result);
    syncActiveTopicFromStore();
    if (wasGlobalFavorites) setDefaultSelection();
  } catch (error) {
    pushToast(`收藏更新失败：${error.message}`, "error");
  }
}

function openEventMenu(event) {
  if (!event?.id) return;
  state.menuEvent = event;
}

function closeEventMenu() {
  state.menuEvent = null;
}

async function moveEventToTrash(event) {
  if (!event?.id) return false;
  try {
    const result = await api.softDeleteEvent(event.id);
    timelineStore.patchEvent(event.id, { deletedAt: result.deletedAt || new Date().toISOString() });
    await refreshSidebarData({ reloadTopics: true });
    syncActiveTopicFromStore();
    closeEventMenu();
    applyFilterState();
    await syncRouteState({ eventId: state.rightOpen ? state.selectedEventId : null });
    pushToast("已移入回收站");
    return true;
  } catch (error) {
    pushToast(`删除失败：${error.message}`, "error");
    return false;
  }
}

async function restoreEvent(event) {
  if (!event?.id) return false;
  try {
    const result = await api.restoreEvent(event.id);
    timelineStore.upsertEvent(result);
    await refreshSidebarData({ reloadTopics: true });
    syncActiveTopicFromStore();
    closeEventMenu();
    applyFilterState();
    await syncRouteState({ eventId: state.rightOpen ? state.selectedEventId : null });
    pushToast("已恢复");
    return true;
  } catch (error) {
    pushToast(`恢复失败：${error.message}`, "error");
    return false;
  }
}

async function permanentlyDeleteEvent(event) {
  if (!event?.id) return false;
  try {
    await api.permanentlyDeleteEvent(event.id);
    timelineStore.removeEvent(event.id);
    await refreshSidebarData({ reloadTopics: true });
    syncActiveTopicFromStore();
    closeEventMenu();
    applyFilterState();
    await syncRouteState({ eventId: state.rightOpen ? state.selectedEventId : null });
    pushToast("已永久删除");
    return true;
  } catch (error) {
    pushToast(`永久删除失败：${error.message}`, "error");
    return false;
  }
}

// The center surface open right now (mindmap or canvas — never both). Its trash/restore
// flow is identical, so both surfaces share these handlers.
function activeCenterSurface() {
  return mindmapSurfaceRef.value || canvasSurfaceRef.value || null;
}
async function settleCenterSaves() {
  await mindmapSaveChain.catch(() => null);
  await canvasSaveChain.catch(() => null);
}

async function trashMindmapNote(event) {
  activeCenterSurface()?.flushAutosave?.();
  activeCenterSurface()?.pauseAutosave?.();
  await settleCenterSaves();
  const ok = await moveEventToTrash(event);
  if (ok && Number(event?.id) === Number(state.mindmapOpenId)) {
    closeMindmap();
    setDefaultSelection();
  }
  if (!ok && Number(event?.id) === Number(state.mindmapOpenId)) {
    activeCenterSurface()?.resumeAutosave?.();
  }
}

async function restoreMindmapNote(event) {
  await restoreEvent(event);
  if (Number(event?.id) === Number(state.mindmapOpenId)) {
    closeMindmap();
    setDefaultSelection();
  }
}

async function permanentlyDeleteMindmapNote(event) {
  activeCenterSurface()?.flushAutosave?.();
  activeCenterSurface()?.pauseAutosave?.();
  await settleCenterSaves();
  const ok = await permanentlyDeleteEvent(event);
  if (ok && Number(event?.id) === Number(state.mindmapOpenId)) {
    closeMindmap();
    setDefaultSelection();
  }
  if (!ok && Number(event?.id) === Number(state.mindmapOpenId)) {
    activeCenterSurface()?.resumeAutosave?.();
  }
}

function togglePreview() {
  state.showPreview = !state.showPreview;
  writeStorage(PREVIEW_KEY, state.showPreview ? "on" : "off");
}

// Note-level batch ops: run the existing per-event state patches over the
// selected ids, then reconcile the view. Each is resilient to partial failure.
async function runBatch(ids, perEvent, doneLabel) {
  const sourceEvents = isGlobalFavoritesMode.value ? globalFavoriteEvents.value : state.events;
  const targets = sourceEvents.filter((event) => ids.includes(event.id));
  if (!targets.length) return;
  let done = 0;
  try {
    for (const event of targets) {
      // perEvent returns false for a no-op skip (e.g. already in target state),
      // so the toast counts only events actually changed.
      const ran = await perEvent(event);
      if (ran !== false) {
        if (ran?.permanentDeletedId) {
          timelineStore.removeEvent(ran.permanentDeletedId);
        } else if (ran?.id) {
          timelineStore.upsertEvent(ran);
        } else if ("deletedAt" in (ran || {})) {
          timelineStore.patchEvent(event.id, { deletedAt: ran.deletedAt || new Date().toISOString() });
        }
        done += 1;
      }
    }
    pushToast(`${doneLabel} ${done} 条`);
  } catch (error) {
    pushToast(done ? `已处理 ${done} 条，其余失败：${error.message}` : `操作失败：${error.message}`, "error");
  } finally {
    await refreshSidebarData({ reloadTopics: true });
    syncActiveTopicFromStore();
    applyFilterState();
    state.rightOpen = false;
    await syncRouteState({ eventId: null });
  }
}

function batchFavoriteEvents(ids) {
  return runBatch(ids, (event) => (event.favorite ? false : api.updateEventFavorite(event.id, true)), "已收藏");
}

function batchTrashEvents(ids) {
  return runBatch(ids, (event) => (event.deletedAt ? false : api.softDeleteEvent(event.id)), "已移入回收站");
}

function batchRestoreEvents(ids) {
  return runBatch(ids, (event) => (event.deletedAt ? api.restoreEvent(event.id) : false), "已恢复");
}

// Permanent batch delete is irreversible — gate it behind an in-app confirm.
function requestBatchPurge(ids) {
  const targets = (ids || []).filter((id) => state.events.some((event) => event.id === id));
  if (targets.length) state.confirmPurgeIds = targets;
}

function closeBatchPurge() {
  state.confirmPurgeIds = null;
}

async function confirmBatchPurgeNow() {
  const ids = state.confirmPurgeIds;
  state.confirmPurgeIds = null;
  if (ids?.length) {
    await runBatch(
      ids,
      async (event) => {
        await api.permanentlyDeleteEvent(event.id);
        return { permanentDeletedId: event.id };
      },
      "已永久删除"
    );
  }
}

function focusFeedSearch() {
  if (isMobile.value) {
    state.mobileSearchOpen = true;
    closeMobileSidebar();
    return;
  }
  openCommandPalette();
}

// A brand-new option created in the picker is folded into its property and
// persisted to the topic immediately (optimistic local update first).
async function addPropertyOption({ key, option }) {
  if (!state.activeTopicId || !key || !option?.id) return;
  const topicEvents = timelineStore.eventsForTopic(state.activeTopicId);
  const orphanIds = new Set();
  for (const event of topicEvents) {
    const raw = event?.extra?.[key];
    const list = Array.isArray(raw) ? raw : raw ? [raw] : [];
    for (const value of list) {
      const normalized = String(value || "").trim();
      if (normalized) orphanIds.add(normalized);
    }
  }
  const existingIds = new Set(
    normalizeTopicColumns(state.activeTopicMeta?.columns)
      .find((column) => column.key === key)
      ?.options?.map((item) => item.id) || []
  );
  const nextOptionId = existingIds.has(option.id) || orphanIds.has(option.id)
    ? buildOptionId(option.label || option.id, [...existingIds, ...orphanIds])
    : option.id;
  const columns = normalizeTopicColumns(state.activeTopicMeta?.columns).map((column) => {
    if (column.key !== key) return column;
    if ((column.options || []).some((existing) => existing.id === nextOptionId)) return column;
    return { ...column, options: [...(column.options || []), { ...option, id: nextOptionId }] };
  });
  try {
    const meta = await api.updateTopicMeta(state.activeTopicId, {
      title: state.activeTopicMeta?.title || "",
      subtitle: state.activeTopicMeta?.subtitle || "",
      columns,
    });
    timelineStore.upsertTopic(meta);
    syncActiveTopicFromStore();
  } catch (error) {
    pushToast(`选项保存失败：${error.message}`, "error");
  }
}

function topicsByIds(ids) {
  const wanted = new Set(ids);
  return state.topics.filter((topic) => wanted.has(topic.id));
}

function requestDeleteBookshelf(bookshelfName) {
  const bookshelf = bookshelfByName(bookshelfName);
  if (bookshelf) state.confirmDeleteBookshelf = bookshelf;
}

function closeDeleteBookshelf() {
  state.confirmDeleteBookshelf = null;
}

async function confirmDeleteBookshelfNow() {
  const bookshelf = state.confirmDeleteBookshelf;
  if (!bookshelf?.id) return;
  try {
    await api.deleteBookshelf(bookshelf.id);
    await refreshBookshelfTree();
    if (state.focusedBookshelfName === bookshelf.name) {
      state.focusedBookshelfName = normalizeTopicBookshelf(state.activeTopicMeta || {}).name;
    }
    pushToast(`已删除书架：${bookshelf.title || bookshelf.name}`);
  } catch (error) {
    pushToast(`删除书架失败：${error.message}`, "error");
  } finally {
    state.confirmDeleteBookshelf = null;
  }
}

function requestDeleteTopic(topicId) {
  const topics = topicsByIds([topicId]);
  if (topics.length) state.confirmDeleteTopics = topics;
}

function requestBatchDeleteTopics(ids) {
  const topics = topicsByIds(ids || []);
  if (topics.length) state.confirmDeleteTopics = topics;
}

function closeDeleteTopic() {
  state.confirmDeleteTopics = null;
}

async function confirmDeleteTopicNow() {
  const topics = state.confirmDeleteTopics;
  if (!topics?.length) return;
  let deleted = 0;
  try {
    for (const topic of topics) {
      await api.deleteTopic(topic.id);
      timelineStore.removeTopic(topic.id);
      deleted += 1;
    }
    await refreshSidebarData({ reloadTopics: true });
    syncActiveTopicFromStore();
    pushToast(topics.length > 1 ? `已删除 ${topics.length} 个笔记本` : `已删除笔记本：${topics[0].title || topics[0].name}`);
  } catch (error) {
    pushToast(deleted ? `已删除 ${deleted} 个，其余失败：${error.message}` : `删除失败：${error.message}`, "error");
  } finally {
    // Reconcile the UI to server truth whether all / some / none succeeded, so a
    // mid-loop failure never leaves the card open over already-deleted notebooks.
    state.confirmDeleteTopics = null;
    if (deleted) {
      await applyWorkspaceSelectionWithEvents({
        preferredTopicId: state.topics[0]?.id ?? null,
        preferredEventId: null,
        preferredMode: "view",
        openDetail: false,
      });
      state.rightOpen = false;
      await syncRouteState({ topicId: state.activeTopicId, eventId: null });
    }
  }
}

async function persistTopicColumns(topicId, columns, { silentSuccess = false } = {}) {
  if (!topicId) return;
  const normalized = normalizeTopicColumns(columns);
  const topicMeta = timelineStore.topicById(topicId) || (state.activeTopicId === topicId ? state.activeTopicMeta : null);
  const title = topicMeta?.title || "";
  const subtitle = topicMeta?.subtitle || "";
  const revision = (latestColumnSaveRevisionByTopic.get(topicId) || 0) + 1;
  latestColumnSaveRevisionByTopic.set(topicId, revision);
  if (topicMeta) {
    timelineStore.upsertTopic({
      ...topicMeta,
      columns: normalized,
    });
    if (state.activeTopicId === topicId) syncActiveTopicFromStore();
  }
  const task = async () => {
    columnSaveInFlight += 1;
    state.columnSaving = true;
    try {
      const meta = await api.updateTopicMeta(topicId, {
        title,
        subtitle,
        columns: normalized,
      });
      if (revision !== latestColumnSaveRevisionByTopic.get(topicId)) return meta;
      // A column-save snapshot may carry a stale displayStyle / sort / groupBy if a
      // view switch or sort change is in flight — keep the store's current values
      // rather than reverting them.
      const current = timelineStore.topicById(topicId);
      const preserved = {};
      if (current?.displayStyle) preserved.displayStyle = current.displayStyle;
      if (current?.sort) preserved.sort = current.sort;
      if (current?.groupBy) preserved.groupBy = current.groupBy;
      timelineStore.upsertTopic({ ...meta, ...preserved });
      if (state.activeTopicId === topicId) syncActiveTopicFromStore();
      if (!silentSuccess) pushToast("列定义已保存");
      return meta;
    } catch (error) {
      if (revision !== latestColumnSaveRevisionByTopic.get(topicId)) return null;
      try {
        const freshMeta = await api.getTopicMeta(topicId);
        timelineStore.upsertTopic(freshMeta);
        if (state.activeTopicId === topicId) syncActiveTopicFromStore();
      } catch {
        // Best-effort rollback to server truth; keep the original error toast.
      }
      pushToast(`列定义保存失败：${error.message}`, "error");
      return null;
    } finally {
      columnSaveInFlight = Math.max(0, columnSaveInFlight - 1);
      state.columnSaving = columnSaveInFlight > 0;
    }
  };
  columnSaveChain = columnSaveChain.then(task, task);
  return columnSaveChain;
}

async function saveTopicColumns(payload) {
  const topicId = Number(payload?.topicId || state.activeTopicId);
  const columns = payload?.columns || [];
  if (!topicId) return;
  await persistTopicColumns(topicId, columns, { silentSuccess: true });
}

async function changeDisplayStyle(style) {
  const topicId = state.activeTopicId;
  if (!topicId || !style) return;
  const topicMeta = timelineStore.topicById(topicId) || state.activeTopicMeta;
  if (!topicMeta || topicMeta.displayStyle === style) return;
  // Optimistic: reflect the new view immediately.
  timelineStore.upsertTopic({ ...topicMeta, displayStyle: style });
  if (state.activeTopicId === topicId) syncActiveTopicFromStore();
  // Serialize through the shared meta-save chain so a concurrent column-save PUT
  // (or a rapid second view switch) can't land out of order and revert the view.
  const task = async () => {
    try {
      const meta = await api.updateTopicMeta(topicId, { displayStyle: style });
      timelineStore.upsertTopic({ ...meta, displayStyle: style });
      if (state.activeTopicId === topicId) syncActiveTopicFromStore();
    } catch (error) {
      try {
        timelineStore.upsertTopic(await api.getTopicMeta(topicId));
        if (state.activeTopicId === topicId) syncActiveTopicFromStore();
      } catch {
        // Best-effort rollback to server truth; keep the error toast.
      }
      pushToast(`视图切换失败：${error.message}`, "error");
    }
  };
  columnSaveChain = columnSaveChain.then(task, task);
  return columnSaveChain;
}

// Switch a container's type (数字图书馆). The backend re-gates the view set and clamps
// displayStyle into it; mirror that optimistically so the switcher + feed don't flash,
// then reconcile with the server truth through the shared meta-save chain.
async function changeContainerType({ id, containerType } = {}) {
  const topicId = Number(id);
  if (!topicId || !containerType) return;
  const topicMeta =
    timelineStore.topicById(topicId) || (topicId === state.activeTopicId ? state.activeTopicMeta : null);
  if (!topicMeta || topicMeta.containerType === containerType) return;
  const views = containerTypeViews(containerType);
  const nextDisplay = views.includes(topicMeta.displayStyle) ? topicMeta.displayStyle : views[0];
  timelineStore.upsertTopic({
    ...topicMeta,
    containerType,
    views,
    defaultView: views[0],
    displayStyle: nextDisplay,
  });
  if (state.activeTopicId === topicId) syncActiveTopicFromStore();
  const task = async () => {
    try {
      const meta = await api.updateTopicMeta(topicId, { containerType });
      timelineStore.upsertTopic(meta);
      if (state.activeTopicId === topicId) syncActiveTopicFromStore();
    } catch (error) {
      try {
        timelineStore.upsertTopic(await api.getTopicMeta(topicId));
        if (state.activeTopicId === topicId) syncActiveTopicFromStore();
      } catch {
        // Best-effort rollback to server truth; keep the error toast.
      }
      pushToast(`容器类型切换失败：${error.message}`, "error");
    }
  };
  columnSaveChain = columnSaveChain.then(task, task);
  return columnSaveChain;
}

async function resizeTopicColumn(payload) {
  const key = String(payload?.key || "").trim();
  if (!state.activeTopicId || !key) return;
  const width = Number(payload?.width || 96);
  const columns = normalizeTopicColumns(state.activeTopicMeta?.columns).map((column) =>
    column.key === key ? { ...column, width } : column
  );
  await persistTopicColumns(state.activeTopicId, columns, { silentSuccess: true });
}

function exportCurrentTopic() {
  if (!state.activeTopicId) return;
  api.exportCurrentDataRange(state.activeTopicId);
}

async function updateMediaConfig(media) {
  const nextMedia = normalizeMediaConfig(media);
  const previousMedia = state.config.media;
  state.config.media = nextMedia;
  try {
    const updated = await api.updateConfig({ media: nextMedia });
    state.config.media = normalizeMediaConfig(updated?.media);
    pushToast("媒体设置已保存");
  } catch (error) {
    state.config.media = previousMedia;
    pushToast(`媒体设置保存失败：${error.message}`, "error");
  }
}

// Which outer edge the function sidebar sits on (desktop only). Global app-config
// preference (cross-device), same optimistic + rollback path as media config; also
// mirrored to localStorage so the next load paints the right side on frame 1.
async function updateNavPosition(position) {
  const next = normalizeNavPosition(position);
  const previous = normalizeNavPosition(state.config.navPosition);
  if (next === previous) return;
  state.config.navPosition = next;
  writeStorage(NAV_POSITION_KEY, next);
  try {
    const updated = await api.updateConfig({ navPosition: next });
    state.config.navPosition = normalizeNavPosition(updated?.navPosition);
    writeStorage(NAV_POSITION_KEY, state.config.navPosition);
  } catch (error) {
    state.config.navPosition = previous;
    writeStorage(NAV_POSITION_KEY, previous);
    pushToast(`布局设置保存失败：${error.message}`, "error");
  }
}

// Which grid track the detail pane occupies ("edge" | "center"), i.e. the 中栏/右栏
// swap (docs/layout-swap-design.md §7). Same optimistic + rollback + localStorage
// first-frame mirror path as navPosition.
async function updateDetailPosition(position) {
  const next = normalizeDetailPosition(position);
  const previous = normalizeDetailPosition(state.config.detailPosition);
  if (next === previous) return;
  state.config.detailPosition = next;
  writeStorage(DETAIL_POSITION_KEY, next);
  try {
    const updated = await api.updateConfig({ detailPosition: next });
    state.config.detailPosition = normalizeDetailPosition(updated?.detailPosition);
    writeStorage(DETAIL_POSITION_KEY, state.config.detailPosition);
  } catch (error) {
    state.config.detailPosition = previous;
    writeStorage(DETAIL_POSITION_KEY, previous);
    pushToast(`布局设置保存失败：${error.message}`, "error");
  }
}

// Global left-tree sort (bookshelves + notebooks). Same optimistic + rollback +
// localStorage-mirror path as navPosition; the reorder itself is a pure computed.
async function updateSidebarSort(mode) {
  const next = normalizeSidebarSort(mode);
  const previous = normalizeSidebarSort(state.config.sidebarSort);
  if (next === previous) return;
  state.config.sidebarSort = next;
  writeStorage(SIDEBAR_SORT_KEY, next);
  try {
    const updated = await api.updateConfig({ sidebarSort: next });
    state.config.sidebarSort = normalizeSidebarSort(updated?.sidebarSort);
    writeStorage(SIDEBAR_SORT_KEY, state.config.sidebarSort);
  } catch (error) {
    state.config.sidebarSort = previous;
    writeStorage(SIDEBAR_SORT_KEY, previous);
    pushToast(`排序设置保存失败：${error.message}`, "error");
  }
}

function startResize(side, event) {
  // When the sidebar is on the right, both handles mirror: the sidebar boundary is
  // measured from the right edge and the detail boundary from the left. With the
  // detail pane in the center track its boundary is offset by the sidebar width
  // (docs/layout-swap-design.md §7).
  const navRight = state.config.navPosition === "right";
  const detailCenter = state.config.detailPosition === "center";
  // Width the sidebar actually paints at (workspaceStyle clamps it on compact desktops).
  const paintedLeft = () => (isCompactDesktop.value ? clamp(state.leftWidth, 220, 240) : state.leftWidth);
  const onMove = (moveEvent) => {
    if (side === "left") {
      const width = navRight ? window.innerWidth - moveEvent.clientX : moveEvent.clientX;
      // On compact desktops the sidebar paints clamped to 220–240, so cap the stored
      // value there too — otherwise the resizer drags past where the column renders.
      const leftMax = isCompactDesktop.value ? 240 : 360;
      state.leftWidth = clamp(width, 220, leftMax);
      writeStorage(LEFT_WIDTH_KEY, state.leftWidth);
    } else {
      let width;
      if (detailCenter) {
        const inner = navRight ? window.innerWidth - moveEvent.clientX : moveEvent.clientX;
        width = inner - paintedLeft();
      } else {
        width = navRight ? moveEvent.clientX : window.innerWidth - moveEvent.clientX;
      }
      // On compact desktops the detail paints clamped to 360–380; match that so the
      // stored value can't exceed the painted width. On roomier desktops the cap grows
      // with the viewport (feed stays ≥480px) but never below the legacy 560.
      const maxRight = isCompactDesktop.value
        ? 380
        : Math.max(560, Math.min(960, window.innerWidth - paintedLeft() - 480));
      state.rightWidth = clamp(width, 360, maxRight);
      writeStorage(RIGHT_WIDTH_KEY, state.rightWidth);
    }
  };

  const onUp = () => {
    window.removeEventListener("mousemove", onMove);
    window.removeEventListener("mouseup", onUp);
    resizeCleanup = null;
  };

  resizeCleanup?.();
  resizeCleanup = onUp;
  window.addEventListener("mousemove", onMove);
  window.addEventListener("mouseup", onUp);
  event.preventDefault();
}

function cancelDetailRequest() {
  detailAbortController?.abort();
  detailAbortController = null;
}

function clearDetailPrefetch() {
  if (detailPrefetchHandle == null || typeof window === "undefined") return;
  if (typeof window.cancelIdleCallback === "function" && typeof detailPrefetchHandle === "number") {
    window.cancelIdleCallback(detailPrefetchHandle);
  } else {
    window.clearTimeout(detailPrefetchHandle);
  }
  detailPrefetchHandle = null;
}

function scheduleDetailPrefetch(eventId) {
  clearDetailPrefetch();
  const id = Number(eventId);
  if (!id || !state.rightOpen || state.detailMode === "create") return;
  const items = visibleEvents.value;
  const index = items.findIndex((event) => event.id === id);
  if (index < 0) return;
  const distance = isMobile.value ? 1 : 2;
  const targets = items
    .slice(Math.max(0, index - distance), Math.min(items.length, index + distance + 1))
    .filter((event) => event.id !== id)
    .map((event) => event.id);
  if (!targets.length) return;

  const run = async () => {
    detailPrefetchHandle = null;
    for (const targetId of targets) {
      if (timelineStore.detailById(targetId)) continue;
      try {
        await timelineStore.ensureEventDetail(targetId);
      } catch (error) {
        if (error?.name === "AbortError") return;
      }
    }
  };

  if (typeof window !== "undefined" && typeof window.requestIdleCallback === "function") {
    detailPrefetchHandle = window.requestIdleCallback(() => {
      void run();
    });
    return;
  }
  detailPrefetchHandle = window.setTimeout(() => {
    void run();
  }, 120);
}

async function loadSelectedEventDetail(eventId) {
  const id = Number(eventId);
  const seq = ++detailRequestSeq;
  timelineStore.setProtectedDetailId(id || null);
  if (!id || timelineStore.detailById(id)) {
    cancelDetailRequest();
    state.detailLoading = false;
    state.detailError = "";
    scheduleDetailPrefetch(id);
    return;
  }
  cancelDetailRequest();
  const controller = new AbortController();
  detailAbortController = controller;
  state.detailLoading = true;
  state.detailError = "";
  try {
    await timelineStore.ensureEventDetail(id, { signal: controller.signal });
    if (seq === detailRequestSeq) {
      syncActiveTopicFromStore();
    }
  } catch (error) {
    if (error?.name === "AbortError") return;
    if (seq === detailRequestSeq) {
      state.detailError = error.message || "详情加载失败";
      pushToast(`详情加载失败：${error.message}`, "error");
    }
  } finally {
    if (detailAbortController === controller) detailAbortController = null;
    if (seq === detailRequestSeq) {
      state.detailLoading = false;
      scheduleDetailPrefetch(id);
    }
  }
}

onMounted(() => {
  window.addEventListener("keydown", handleGlobalKeydown);
  loadWorkspace();
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleGlobalKeydown);
  resizeCleanup?.();
  clearCommandSearchTimer();
  cancelDetailRequest();
  clearDetailPrefetch();
});

watch(
  isMobile,
  (mobile) => {
    if (!mobile) {
      state.mobileSidebarOpen = false;
      state.mobileSearchOpen = false;
    }
  }
);

watch(
  () => [state.selectedEventId, state.rightOpen, state.detailMode],
  ([eventId, rightOpen, mode]) => {
    timelineStore.setProtectedDetailId(rightOpen ? eventId : null);
    if (!rightOpen) {
      cancelDetailRequest();
      clearDetailPrefetch();
      if (isMobile.value) void restoreMobileFeedScroll();
      return;
    }
    if (!eventId || mode === "create") {
      cancelDetailRequest();
      clearDetailPrefetch();
      state.detailLoading = false;
      state.detailError = "";
      return;
    }
    loadSelectedEventDetail(eventId);
  }
);

watch(
  () => [state.commandOpen, state.commandQuery],
  ([open, query]) => {
    clearCommandSearchTimer();
    if (!open) return;
    const seq = ++commandRequestSeq;
    commandSearchTimer = window.setTimeout(() => {
      performCommandSearch(query, seq);
    }, 120);
  }
);

watch(
  () => [route.query.topic, route.query.event, route.query.mode, route.query.filter, route.query.pk, route.query.pv, route.query.era, route.query.date],
  (next, prev = []) => {
    const applyRouteFilterState = () => {
      state.sidebarFilter = parseRouteFilter();
      state.propertyFilter = parseRoutePropertyFilter();
      state.activeEra = parseRouteString("era");
      state.locateDate = parseRouteString("date");
    };
    if (state.loading) return;
    const [nextTopic, nextEvent, nextMode] = next;
    const [prevTopic, prevEvent, prevMode] = prev;
    if (nextTopic !== prevTopic || nextEvent !== prevEvent || nextMode !== prevMode) {
      const spec = buildRouteSelectionSpec();
      if (routeSelectionMatchesState(spec)) {
        applyRouteFilterState();
        return;
      }
      const restoreSnapshot = {
        topicId: state.activeTopicId,
        eventId: state.rightOpen ? state.selectedEventId : null,
        mode: state.detailMode,
        filter: state.sidebarFilter,
        propertyFilter: { ...state.propertyFilter },
        era: state.activeEra,
        date: state.locateDate,
      };
      runOrConfirm(() => {
        applyRouteFilterState();
        void applyRouteSelectionFromQuery();
      }, { restoreRouteOnCancel: true, routeRestoreSnapshot: restoreSnapshot });
      return;
    }
    applyRouteFilterState();
  }
);
</script>

<template>
  <div
    class="app timeline-workspace"
    :class="{
      'right-closed': !state.rightOpen,
      'nav-right': !isMobile && state.config.navPosition === 'right',
      'detail-center': !isMobile && state.config.detailPosition === 'center',
      'pane-dragging': paneSwap.dragging.value,
      'is-mobile': isMobile,
      'mobile-drawer-open': state.mobileSidebarOpen,
      'mobile-detail-open': isMobile && state.rightOpen,
    }"
    :style="workspaceStyle"
  >
    <MobileTopBar
      v-if="isMobile"
      :title="feedTitle"
      :count="visibleEvents.length"
      :search-query="state.searchQuery"
      :search-open="state.mobileSearchOpen"
      @open-drawer="openMobileSidebar"
      @create-event="startCreateEvent"
      @create-mindmap="createMindmapNote"
      @create-canvas="createCanvasNote"
      @update:searchQuery="updateSearchQuery"
      @update:search-open="state.mobileSearchOpen = $event"
    />

    <div v-if="isMobile && state.mobileSidebarOpen" class="mobile-drawer-scrim" @click="closeMobileSidebar"></div>

    <TopicSidebar
      :brand="state.config.brandName"
      :topics="state.topics"
      :events="state.events"
      :all-events="timelineStore.state.eventsIndex"
      :bookshelf-tree="sortedBookshelfTree"
      :sidebar-sort="state.config.sidebarSort"
      :bookshelf-collapsed="state.bookshelfCollapsed"
      :active-bookshelf-name="activeBookshelfName"
      :active-topic-id="state.activeTopicId"
      :active-filter="state.sidebarFilter"
      :global-favorite-count="globalFavoriteEvents.length"
      :global-favorites-active="isGlobalFavoritesMode"
      :favorites-panel="favoritesPanel"
      :columns="topicColumns"
      :property-filter="state.propertyFilter"
      :property-data-ready="timelineStore.state.indexLoaded"
      :loading="state.loading"
      :error="state.error"
      :column-saving="state.columnSaving"
      :create-topic-request-key="state.topicCreateRequestKey"
      @create-bookshelf="createBookshelf"
      @create-event="startCreateEvent"
      @create-event-in-topic="createEventInTopic"
      @create-mindmap-in-topic="createMindmapNote"
      @create-canvas-in-topic="createCanvasNote"
      @create-topic="createTopic"
      @rename-bookshelf="renameBookshelf"
      @rename-topic="renameTopic"
      @change-container-type="changeContainerType"
      @delete-bookshelf="requestDeleteBookshelf"
      @delete-topic="requestDeleteTopic"
      @batch-delete-topics="requestBatchDeleteTopics"
      @save-topic-columns="saveTopicColumns"
      @focus-search="focusFeedSearch"
      @open-settings="openSettings"
      @open-global-favorites="openGlobalFavorites"
      @update:favorite-scope="updateFavoriteScope"
      @open-favorite-event="selectEvent"
      @toggle-bookshelf="toggleBookshelf"
      @set-all-bookshelves-collapsed="setAllBookshelvesCollapsed"
      @select-ribbon="handleSidebarRibbon"
      @select-topic="selectTopic"
      @update:filter="updateSidebarFilter"
      @update:property-filter="updatePropertyFilter"
      @update:sidebar-sort="updateSidebarSort"
      @pane-drag-start="paneSwap.onPaneDragStart"
    />

    <MindmapSurface
      v-if="mindmapNote"
      ref="mindmapSurfaceRef"
      :note="mindmapNote"
      :saving="state.mindmapSaving"
      @back="closeMindmap"
      @save="saveMindmapTree"
      @toggle-favorite="toggleFavorite"
      @move-to-trash="trashMindmapNote"
      @restore="restoreMindmapNote"
      @permanent-delete="permanentlyDeleteMindmapNote"
    />

    <CanvasSurface
      v-else-if="canvasNote"
      ref="canvasSurfaceRef"
      :note="canvasNote"
      :saving="state.mindmapSaving"
      :resolve-detail="timelineStore.ensureEventDetail"
      @back="closeMindmap"
      @save="saveCanvasSnapshot"
      @toggle-favorite="toggleFavorite"
      @move-to-trash="trashMindmapNote"
      @restore="restoreMindmapNote"
      @permanent-delete="permanentlyDeleteMindmapNote"
      @open-embed="pinRelatedEvent"
    />

    <TimelineFeed
      ref="feedPaneRef"
      v-else
      :loading="state.loading || state.eventsLoading"
      :error="state.error"
      :has-topic="Boolean(state.activeTopicId) || isGlobalFavoritesMode"
      :topic-title="feedTitle"
      :filter-context-label="isGlobalFavoritesMode ? favoritesPanel.contextLabel : ''"
      :filter-context-clearable="isGlobalFavoritesMode && favoritesPanel.clearable"
      :topic-id="state.activeTopicId"
      :topics="state.topics"
      :event-count="visibleEvents.length"
      :empty-reason="feedEmptyReason"
      :search-query="state.searchQuery"
      :groups="groupedEvents"
      :all-events="state.events"
      :selected-event-id="state.selectedEventId"
      :locate-date="state.locateDate"
      :columns="feedColumns"
      :empty-column-keys="feedEmptyColumnKeys"
      :column-saving="state.columnSaving"
      :show-preview="state.showPreview"
      :show-source="isGlobalFavoritesMode"
      :global-favorites-mode="isGlobalFavoritesMode"
      :show-column-controls="!isGlobalFavoritesMode"
      :display-style="feedDisplayStyle"
      :capabilities="feedCapabilities"
      :sort="activeSort"
      :group-by="state.groupBy"
      :show-view-switcher="showViewSwitcher"
      :search-placeholder="isGlobalFavoritesMode ? '搜索跨本收藏' : '搜索当前时间线'"
      :search-request-key="state.searchRequestKey"
      :command-search="!isMobile"
      :trash-view="!isGlobalFavoritesMode && state.sidebarFilter === 'trash'"
      :mobile="isMobile"
      :has-more="state.hasMore"
      :loading-more="state.loadingMore"
      :can-retry-load-more="
        !isGlobalFavoritesMode &&
        state.hasMore &&
        !state.eventsLoading &&
        !state.loadingMore &&
        state.autoLoadBlockedKey === autoLoadContextKey
      "
      @create-event="startCreateEvent"
      @locate-date="locateDate"
      @save-columns="saveTopicColumns"
      @change-view="changeDisplayStyle"
      @change-sort="changeSort"
      @change-group-by="changeGroupBy"
      @resize-column="resizeTopicColumn"
      @select-event="selectEvent"
      @toggle-favorite="toggleFavorite"
      @toggle-preview="togglePreview"
      @update:searchQuery="updateSearchQuery"
      @batch-favorite="batchFavoriteEvents"
      @batch-trash="batchTrashEvents"
      @batch-restore="batchRestoreEvents"
      @batch-permanent-delete="requestBatchPurge"
      @open-command-palette="openCommandPalette"
      @clear-context-filter="clearFavoriteScope"
      @create-mindmap="createMindmapNote"
      @create-canvas="createCanvasNote"
      @load-more="loadMoreActiveTopicEvents($event || { auto: false })"
      @pane-drag-start="paneSwap.onPaneDragStart"
    />

    <EventDetailPane
      v-show="!isMobile || state.rightOpen"
      ref="detailPaneRef"
      :event="detailPaneEvent"
      :candidate-events="state.events"
      :topic-title="activeTopicTitle"
      :topic-columns="topicColumns"
      :loading="detailPaneLoading"
      :error="state.detailError"
      :mode="state.detailMode"
      :saving="state.saving"
      :mobile="isMobile"
      :detail-position="state.config.detailPosition"
      @update-detail-position="updateDetailPosition"
      @pane-drag-start="paneSwap.onPaneDragStart"
      @cancel="cancelDetailEdit"
      @close="closeDetailPane"
      @edit="startEditSelectedEvent"
      @open-menu="openEventMenu"
      @move-to-trash="moveEventToTrash"
      @preview-related="previewRelatedEvent"
      @hide-related-preview="hideRelatedPreview"
      @pin-related="pinRelatedEvent"
      @save="saveEvent"
      @toggle-favorite="toggleFavorite"
      @create-option="addPropertyOption"
      @dirty-change="state.detailDirty = $event"
      @preview-change="state.editPreview = $event"
    />

    <RelatedEventPreviewPopover
      :open="state.relatedPreviewOpen"
      :event="relatedPreviewEvent"
      :topic-title="relatedPreviewTopicTitle"
      :loading="state.relatedPreviewLoading"
      :error="state.relatedPreviewError"
      :pinned="state.relatedPreviewPinned"
      :placement="state.relatedPreviewPlacement"
      :style-vars="state.relatedPreviewStyle"
      @close="closeRelatedPreview"
      @open-full="openRelatedPreviewFull"
    />

    <div v-if="!isMobile" id="rzLeft" class="resizer" @mousedown="startResize('left', $event)"></div>
    <div v-if="!isMobile && state.rightOpen" id="rzRight" class="resizer" @mousedown="startResize('right', $event)"></div>

    <!-- Pane-swap drag overlays (docs/pane-swap-drag-design.md §2). The target
         highlight marks where the dragged pane lands once past the midline; the
         ghost trails the pointer. Both are fixed, pointer-events:none leaf nodes so
         the drag stays compositor-only. The ghost stays mounted (hidden via CSS
         until .pane-dragging) so its transform can be written without a mount flash. -->
    <div
      v-if="paneSwap.dragging.value"
      class="pane-swap-target"
      :class="{ armed: paneSwap.armed.value }"
      :style="{ left: `${paneSwap.targetRect.value.left}px`, width: `${paneSwap.targetRect.value.width}px` }"
      aria-hidden="true"
    ></div>
    <div ref="paneDragGhostEl" class="pane-drag-ghost" aria-hidden="true">
      <TimelineLucideIcon :name="paneDragGhostIcon" :stroke-width="1.5" />
      <span>{{ paneDragGhostLabel }}</span>
    </div>

    <div v-if="state.menuEvent" class="timeline-menu-backdrop" @click="closeEventMenu">
      <div class="popover timeline-action-menu" @click.stop>
        <template v-if="state.menuEvent.deletedAt">
          <button type="button" class="pop-item" @click="restoreEvent(state.menuEvent)">
            <TimelineLucideIcon name="restore" :stroke-width="1.5" class="pop-item-ic" />
            <span class="lbl">恢复</span>
          </button>
          <span class="pop-divider"></span>
          <button type="button" class="pop-item danger" @click="permanentlyDeleteEvent(state.menuEvent)">
            <TimelineLucideIcon name="trash" :stroke-width="1.5" class="pop-item-ic" />
            <span class="lbl">永久删除</span>
          </button>
        </template>
        <template v-else>
          <button type="button" class="pop-item" @click="moveEventToTrash(state.menuEvent)">
            <TimelineLucideIcon name="trash" :stroke-width="1.5" class="pop-item-ic" />
            <span class="lbl">移入回收站</span>
          </button>
        </template>
      </div>
    </div>

    <div v-if="state.confirmUnsaved" class="timeline-modal-backdrop" @click="closeUnsavedDialog">
      <section class="timeline-confirm-card" role="dialog" aria-modal="true" aria-label="未保存修改" @click.stop>
        <h3>有未保存的修改</h3>
        <p>切换视图或事件前，请选择保存、放弃或继续编辑。</p>
        <div class="timeline-confirm-actions">
          <button type="button" class="timeline-primary-btn" @click="saveAndContinue">保存</button>
          <button type="button" class="timeline-secondary-btn" @click="discardAndContinue">放弃</button>
          <button type="button" class="timeline-secondary-btn" @click="closeUnsavedDialog">取消</button>
        </div>
      </section>
    </div>

    <div v-if="state.confirmDeleteBookshelf" class="timeline-modal-backdrop" @click="closeDeleteBookshelf">
      <section class="timeline-confirm-card" role="dialog" aria-modal="true" aria-label="删除书架" @click.stop>
        <h3>删除书架</h3>
        <p>将删除「{{ state.confirmDeleteBookshelf.title || state.confirmDeleteBookshelf.name }}」。仅空书架允许删除。</p>
        <div class="timeline-confirm-actions">
          <button type="button" class="timeline-primary-btn danger" @click="confirmDeleteBookshelfNow">删除</button>
          <button type="button" class="timeline-secondary-btn" @click="closeDeleteBookshelf">取消</button>
        </div>
      </section>
    </div>

    <div v-if="state.confirmDeleteTopics" class="timeline-modal-backdrop" @click="closeDeleteTopic">
      <section class="timeline-confirm-card" role="dialog" aria-modal="true" aria-label="删除笔记本" @click.stop>
        <h3>{{ state.confirmDeleteTopics.length > 1 ? `删除 ${state.confirmDeleteTopics.length} 个笔记本` : "删除笔记本" }}</h3>
        <p v-if="state.confirmDeleteTopics.length > 1">将永久删除所选 {{ state.confirmDeleteTopics.length }} 个笔记本及其全部时间点，此操作不可恢复。</p>
        <p v-else>将永久删除「{{ state.confirmDeleteTopics[0].title || state.confirmDeleteTopics[0].name }}」及其全部时间点，此操作不可恢复。</p>
        <div class="timeline-confirm-actions">
          <button type="button" class="timeline-primary-btn danger" @click="confirmDeleteTopicNow">删除</button>
          <button type="button" class="timeline-secondary-btn" @click="closeDeleteTopic">取消</button>
        </div>
      </section>
    </div>

    <div v-if="state.confirmPurgeIds" class="timeline-modal-backdrop" @click="closeBatchPurge">
      <section class="timeline-confirm-card" role="dialog" aria-modal="true" aria-label="永久删除" @click.stop>
        <h3>永久删除 {{ state.confirmPurgeIds.length }} 条</h3>
        <p>将永久删除所选 {{ state.confirmPurgeIds.length }} 条时间点，无法恢复。</p>
        <div class="timeline-confirm-actions">
          <button type="button" class="timeline-primary-btn danger" @click="confirmBatchPurgeNow">永久删除</button>
          <button type="button" class="timeline-secondary-btn" @click="closeBatchPurge">取消</button>
        </div>
      </section>
    </div>

    <SettingsModal
      v-if="state.settingsOpen"
      :open="state.settingsOpen"
      :brand-name="state.config.brandName"
      :media-config="state.config.media"
      :nav-position="state.config.navPosition"
      :detail-position="state.config.detailPosition"
      :active-topic-title="activeTopicTitle"
      :has-topic="Boolean(state.activeTopicId)"
      @close="state.settingsOpen = false"
      @export-data="exportCurrentTopic"
      @update-media="updateMediaConfig"
      @update-nav-position="updateNavPosition"
      @update-detail-position="updateDetailPosition"
    />

    <CommandPalette
      v-if="state.commandOpen"
      :open="state.commandOpen"
      :query="state.commandQuery"
      :events="state.commandResults"
      :topics="state.topics"
      :loading="state.commandLoading"
      :error="state.commandError"
      @close="closeCommandPalette"
      @update:query="state.commandQuery = $event"
      @select-event="selectCommandEvent"
      @select-topic="selectCommandTopic"
      @command="handleCommandPaletteCommand"
    />
  </div>
</template>
