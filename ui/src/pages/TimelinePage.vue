<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import CommandPalette from "@/components/timeline-notes/CommandPalette.vue";
import EventDetailPane from "@/components/timeline-notes/EventDetailPane.vue";
import MindmapSurface from "@/components/timeline-notes/MindmapSurface.vue";
import MobileTopBar from "@/components/timeline-notes/MobileTopBar.vue";
import RelatedEventPreviewPopover from "@/components/timeline-notes/RelatedEventPreviewPopover.vue";
import SettingsModal from "@/components/settings/SettingsModal.vue";
import TimelineFeed from "@/components/timeline-notes/TimelineFeed.vue";
import TimelineLucideIcon from "@/components/timeline-notes/TimelineLucideIcon.vue";
import TopicSidebar from "@/components/timeline-notes/TopicSidebar.vue";
import { api } from "@/composables/useApi";
import { pushToast } from "@/composables/useToast";
import { useTimelineStore } from "@/composables/useTimelineStore";
import { useViewport } from "@/composables/useViewport";
import {
  buildX6SeedSnapshot,
} from "@/utils/mindmapX6.js";
import {
  buildOptionId,
  compareTimelineEvents,
  buildGlobalFavoriteEvents,
  groupTimelineEvents,
  matchesEventSearch,
  matchesPropertyFilter,
  mindmapRootData,
  normalizeTopicColumns,
} from "@/utils/timelineNotes";

const route = useRoute();
const router = useRouter();
const detailPaneRef = ref(null);
const mindmapSurfaceRef = ref(null);
const timelineStore = useTimelineStore();
const { isMobile, isCompactDesktop } = useViewport();

const DETAIL_MODES = new Set(["view", "edit", "create"]);
const FILTERS = new Set(["all", "today", "week", "favorite", "trash"]);
const LEFT_WIDTH_KEY = "chronicle-left-width";
const RIGHT_WIDTH_KEY = "chronicle-right-width";
const PREVIEW_KEY = "chronicle-show-preview";

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
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
  saving: false,
  columnSaving: false,
  error: "",
  detailLoading: false,
  detailError: "",
  config: {
    brandName: "编年",
    media: {
      compress: true,
      keepOriginal: false,
      quality: 80,
      maxEdge: 1920,
      thumbEdge: 400,
    },
  },
  topics: [],
  activeTopicId: null,
  activeTopicMeta: null,
  events: [],
  eventBounds: null,
  hasMore: false,
  nextCursor: null,
  searchQuery: "",
  selectedEventId: null,
  detailMode: "view",
  sidebarFilter: "all",
  collectionMode: "",
  propertyFilter: { key: "", value: "" },
  activeEra: "",
  locateDate: "",
  detailDirty: false,
  confirmUnsaved: false,
  pendingAction: null,
  afterSaveAction: null,
  menuEvent: null,
  settingsOpen: false,
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
});

let resizeCleanup = null;
let detailRequestSeq = 0;
let commandSearchTimer = null;
let commandRequestSeq = 0;
let relatedPreviewRequestSeq = 0;
let columnSaveChain = Promise.resolve();
const latestColumnSaveRevisionByTopic = new Map();
let columnSaveInFlight = 0;

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

const activeTopicTitle = computed(
  () => state.activeTopicMeta?.title || state.topics.find((topic) => topic.id === state.activeTopicId)?.title || "编年"
);

const isGlobalFavoritesMode = computed(() => state.collectionMode === "favorites");
const globalFavoriteEvents = computed(() => buildGlobalFavoriteEvents(timelineStore.state.eventsIndex));
const feedTitle = computed(() => (isGlobalFavoritesMode.value ? "收藏（跨本）" : activeTopicTitle.value));
const topicColumns = computed(() => normalizeTopicColumns(state.activeTopicMeta?.columns));
const feedColumns = computed(() => (isGlobalFavoritesMode.value ? [] : topicColumns.value));
// Display-style view (axis 1): start from the persisted style, then derive the live
// capability set from the local notebook snapshot so note creates/deletes (including
// undated mindmaps) update the switcher immediately, before a fresh /meta round-trip.
const feedDisplayStyle = computed(() => state.activeTopicMeta?.displayStyle || "timeline");
const feedCapabilities = computed(() => {
  if (isGlobalFavoritesMode.value) return [];
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
const mindmapNote = computed(() => {
  if (!state.mindmapOpenId) return null;
  const note = timelineStore.detailById(state.mindmapOpenId);
  if (!note || note.topicId !== state.activeTopicId || state.selectedEventId !== state.mindmapOpenId) return null;
  return note;
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
  return withPreviewOverlay(isGlobalFavoritesMode.value ? globalFavoriteEvents.value : state.events);
}

function filterEvents({ filter = state.sidebarFilter, propertyFilter = state.propertyFilter, era = state.activeEra, search = state.searchQuery } = {}) {
  if (isGlobalFavoritesMode.value) {
    return [...previewedEvents()]
      .filter((event) => matchesEventSearch(event, search, []))
      .sort(compareTimelineEvents);
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
    .sort(compareTimelineEvents);
}

const visibleEvents = computed(() => filterEvents());
const groupedEvents = computed(() => groupTimelineEvents(visibleEvents.value, "era", ""));

const feedEmptyReason = computed(() => {
  if (state.error) return "";
  if (isGlobalFavoritesMode.value && state.searchQuery.trim()) return "跨笔记本收藏中没有找到记录。";
  if (isGlobalFavoritesMode.value) return "暂无跨笔记本收藏。";
  if (!state.activeTopicId) return "先创建或选择一个笔记本。";
  if (state.sidebarFilter === "trash" && visibleEvents.value.length === 0) return "回收站为空。";
  if (state.searchQuery.trim()) return "当前搜索条件下没有找到记录。";
  if (state.activeEra) return "当前分期下没有记录。";
  if (state.propertyFilter?.key) return "当前属性筛选下没有记录。";
  return "当前筛选下没有记录。";
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

function syncActiveTopicFromStore() {
  state.topics = [...timelineStore.state.topics];
  state.activeTopicMeta = state.activeTopicId ? timelineStore.topicById(state.activeTopicId) : null;
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
  state.hasMore = false;
  state.nextCursor = null;
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
    const [config] = await Promise.all([api.getConfig(), timelineStore.loadIndex()]);
    state.config = {
      ...state.config,
      ...config,
      brandName: "编年",
      media: normalizeMediaConfig(config?.media),
    };
    applyWorkspaceSelection(options);
  } catch (error) {
    state.error = error.message || "加载失败";
    pushToast(`加载失败：${error.message}`, "error");
  } finally {
    state.loading = false;
  }
}

function runOrConfirm(action) {
  if ((state.detailMode === "edit" || state.detailMode === "create") && state.detailDirty) {
    closeRelatedPreview();
    state.pendingAction = action;
    state.confirmUnsaved = true;
    return;
  }
  action();
}

function exitGlobalFavoritesMode({ reselect = true } = {}) {
  if (!isGlobalFavoritesMode.value) return;
  state.collectionMode = "";
  if (reselect) setDefaultSelection();
}

function handleSidebarRibbon(ribbon) {
  if (ribbon !== "star") exitGlobalFavoritesMode();
}

function openGlobalFavorites() {
  runOrConfirm(async () => {
    state.collectionMode = "favorites";
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
  state.confirmUnsaved = false;
  state.pendingAction = null;
}

function openMobileSidebar() {
  if (isMobile.value) state.mobileSidebarOpen = true;
}

function closeMobileSidebar() {
  state.mobileSidebarOpen = false;
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
  const isMindmap = timelineStore.state.eventsIndex.find((item) => item.id === eventId)?.noteType === "mindmap";
  runOrConfirm(async () => {
    closeCommandPalette();
    state.collectionMode = "";
    state.sidebarFilter = "all";
    state.propertyFilter = { key: "", value: "" };
    state.activeEra = "";
    state.locateDate = "";
    state.searchQuery = "";
    applyWorkspaceSelection({
      preferredTopicId: topicId,
      preferredEventId: eventId,
      preferredMode: "view",
      openDetail: !isMindmap,
    });
    closeMobileSidebar();
    // A mindmap opens its own center canvas, never the markdown detail pane.
    if (isMindmap) {
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
    applyWorkspaceSelection({
      preferredTopicId: topicId,
      preferredEventId: null,
      preferredMode: "view",
      openDetail: false,
    });
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
}

async function applyEventSelection(eventId) {
  const id = Number(eventId);
  const event = timelineStore.state.eventsIndex.find((item) => item.id === id);
  // A mindmap opens its own center canvas (D-2), never the markdown detail pane.
  // Bring its notebook to the front first if it lives in another one.
  if (event?.noteType === "mindmap") {
    if (event.topicId && (isGlobalFavoritesMode.value || event.topicId !== state.activeTopicId)) {
      exitGlobalFavoritesMode({ reselect: false });
      state.sidebarFilter = "all";
      state.propertyFilter = { key: "", value: "" };
      state.activeEra = "";
      state.locateDate = "";
      state.searchQuery = "";
      applyWorkspaceSelection({ preferredTopicId: event.topicId, preferredEventId: id, preferredMode: "view", openDetail: false });
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
    applyWorkspaceSelection({
      preferredTopicId: event.topicId,
      preferredEventId: event.id,
      preferredMode: "view",
      openDetail: true,
    });
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

// Open a mindmap note's canvas in the center column (no markdown detail pane).
// Context (notebook switch) is handled by the caller; here we just load the full
// detail (for bodyJson) and flip the center surface.
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
      applyWorkspaceSelection({
        preferredTopicId: targetTopicId,
        preferredEventId: null,
        preferredMode: "view",
        openDetail: false,
      });
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

function relatedPreviewPosition(anchor) {
  if (typeof window === "undefined") {
    return { placement: "left", style: {} };
  }
  const width = 360;
  const estimatedHeight = 230;
  const gap = 14;
  const margin = 12;
  const viewportWidth = window.innerWidth || 1920;
  const viewportHeight = window.innerHeight || 1080;
  const target = anchor || {
    top: viewportHeight * 0.35,
    bottom: viewportHeight * 0.35 + 40,
    left: viewportWidth - state.rightWidth,
    right: viewportWidth - margin,
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
      applyWorkspaceSelection({
        preferredTopicId: topicId,
        preferredEventId: null,
        preferredMode: "view",
        openDetail: false,
      });
    }
    closeMobileSidebar();
    state.mobileSearchOpen = false;
    state.detailMode = "create";
    state.rightOpen = true;
    await syncRouteState({ topicId, eventId: state.selectedEventId, mode: "create" });
  });
}

function startEditSelectedEvent() {
  if (!selectedEvent.value || selectedEvent.value.deletedAt) return;
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
    applyWorkspaceSelection({
      preferredTopicId: topicId,
      preferredEventId: null,
      preferredMode: "view",
      openDetail: false,
    });
    state.rightOpen = false;
    closeMobileSidebar();
    await syncRouteState({ topicId, eventId: null, propertyFilter: { key: "", value: "" }, era: "", mode: "view" });
  });
}

async function createTopic(name) {
  try {
    const created = await api.createTopic(name);
    timelineStore.upsertTopic({ ...created, eventCount: 0, minDateKey: null, maxDateKey: null, minDate: null, maxDate: null });
    applyWorkspaceSelection({
      preferredTopicId: created.id,
      preferredEventId: null,
      preferredMode: "view",
      openDetail: false,
    });
    pushToast(`已创建笔记本：${name}`);
    state.rightOpen = false;
    closeMobileSidebar();
    await syncRouteState({ topicId: created.id, eventId: null });
  } catch (error) {
    pushToast(`创建笔记本失败：${error.message}`, "error");
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

function updateActiveEra(era) {
  runOrConfirm(async () => {
    exitGlobalFavoritesMode();
    applyFilterState({ era });
    closeMobileSidebar();
    await syncRouteState({ era, eventId: state.rightOpen ? state.selectedEventId : null });
  });
}

function updateSearchQuery(value) {
  state.searchQuery = value;
  setDefaultSelection();
  if (!visibleEvents.value.length) {
    state.rightOpen = false;
  }
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

async function trashMindmapNote(event) {
  mindmapSurfaceRef.value?.flushAutosave?.();
  mindmapSurfaceRef.value?.pauseAutosave?.();
  await mindmapSaveChain.catch(() => null);
  const ok = await moveEventToTrash(event);
  if (ok && Number(event?.id) === Number(state.mindmapOpenId)) {
    closeMindmap();
    setDefaultSelection();
  }
  if (!ok && Number(event?.id) === Number(state.mindmapOpenId)) {
    mindmapSurfaceRef.value?.resumeAutosave?.();
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
  mindmapSurfaceRef.value?.flushAutosave?.();
  mindmapSurfaceRef.value?.pauseAutosave?.();
  await mindmapSaveChain.catch(() => null);
  const ok = await permanentlyDeleteEvent(event);
  if (ok && Number(event?.id) === Number(state.mindmapOpenId)) {
    closeMindmap();
    setDefaultSelection();
  }
  if (!ok && Number(event?.id) === Number(state.mindmapOpenId)) {
    mindmapSurfaceRef.value?.resumeAutosave?.();
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
    syncActiveTopicFromStore();
    pushToast(topics.length > 1 ? `已删除 ${topics.length} 个笔记本` : `已删除笔记本：${topics[0].title || topics[0].name}`);
  } catch (error) {
    pushToast(deleted ? `已删除 ${deleted} 个，其余失败：${error.message}` : `删除失败：${error.message}`, "error");
  } finally {
    // Reconcile the UI to server truth whether all / some / none succeeded, so a
    // mid-loop failure never leaves the card open over already-deleted notebooks.
    state.confirmDeleteTopics = null;
    if (deleted) {
      applyWorkspaceSelection({ preferredTopicId: state.topics[0]?.id ?? null, preferredEventId: null, preferredMode: "view", openDetail: false });
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
      // A column-save snapshot may carry a stale displayStyle if a view switch is
      // in flight — keep the store's current view rather than reverting it.
      const currentStyle = timelineStore.topicById(topicId)?.displayStyle;
      timelineStore.upsertTopic(currentStyle ? { ...meta, displayStyle: currentStyle } : meta);
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

function startResize(side, event) {
  const onMove = (moveEvent) => {
    if (side === "left") {
      state.leftWidth = clamp(moveEvent.clientX, 220, 360);
      writeStorage(LEFT_WIDTH_KEY, state.leftWidth);
    } else {
      state.rightWidth = clamp(window.innerWidth - moveEvent.clientX, 360, 560);
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

async function loadSelectedEventDetail(eventId) {
  const id = Number(eventId);
  if (!id || timelineStore.detailById(id)) {
    state.detailLoading = false;
    return;
  }
  const seq = ++detailRequestSeq;
  state.detailLoading = true;
  state.detailError = "";
  try {
    await timelineStore.ensureEventDetail(id);
    if (seq === detailRequestSeq) {
      syncActiveTopicFromStore();
    }
  } catch (error) {
    if (seq === detailRequestSeq) {
      state.detailError = error.message || "详情加载失败";
      pushToast(`详情加载失败：${error.message}`, "error");
    }
  } finally {
    if (seq === detailRequestSeq) {
      state.detailLoading = false;
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
    if (!rightOpen || !eventId || mode === "create") return;
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
  () => {
    state.sidebarFilter = parseRouteFilter();
    state.propertyFilter = parseRoutePropertyFilter();
    state.activeEra = parseRouteString("era");
    state.locateDate = parseRouteString("date");
  }
);
</script>

<template>
  <div
    class="app timeline-workspace"
    :class="{
      'right-closed': !state.rightOpen,
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
      @update:searchQuery="updateSearchQuery"
      @update:search-open="state.mobileSearchOpen = $event"
    />

    <div v-if="isMobile && state.mobileSidebarOpen" class="mobile-drawer-scrim" @click="closeMobileSidebar"></div>

    <TopicSidebar
      :brand="state.config.brandName"
      :topics="state.topics"
      :events="state.events"
      :all-events="timelineStore.state.eventsIndex"
      :active-topic-id="state.activeTopicId"
      :active-filter="state.sidebarFilter"
      :global-favorite-count="globalFavoriteEvents.length"
      :global-favorites-active="isGlobalFavoritesMode"
      :columns="topicColumns"
      :property-filter="state.propertyFilter"
      :active-era="state.activeEra"
      :loading="state.loading"
      :error="state.error"
      :column-saving="state.columnSaving"
      :create-topic-request-key="state.topicCreateRequestKey"
      @create-event="startCreateEvent"
      @create-event-in-topic="createEventInTopic"
      @create-mindmap-in-topic="createMindmapNote"
      @create-topic="createTopic"
      @rename-topic="renameTopic"
      @delete-topic="requestDeleteTopic"
      @batch-delete-topics="requestBatchDeleteTopics"
      @save-topic-columns="saveTopicColumns"
      @focus-search="focusFeedSearch"
      @open-settings="openSettings"
      @open-global-favorites="openGlobalFavorites"
      @select-era="updateActiveEra"
      @select-ribbon="handleSidebarRibbon"
      @select-topic="selectTopic"
      @update:filter="updateSidebarFilter"
      @update:property-filter="updatePropertyFilter"
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

    <TimelineFeed
      v-else
      :loading="state.loading"
      :error="state.error"
      :has-topic="Boolean(state.activeTopicId) || isGlobalFavoritesMode"
      :topic-title="feedTitle"
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
      :show-view-switcher="showViewSwitcher"
      :search-placeholder="isGlobalFavoritesMode ? '搜索跨本收藏' : '搜索当前时间线'"
      :search-request-key="state.searchRequestKey"
      :command-search="!isMobile"
      :trash-view="!isGlobalFavoritesMode && state.sidebarFilter === 'trash'"
      :mobile="isMobile"
      @create-event="startCreateEvent"
      @locate-date="locateDate"
      @save-columns="saveTopicColumns"
      @change-view="changeDisplayStyle"
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
      @create-mindmap="createMindmapNote"
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

    <div v-if="state.menuEvent" class="timeline-menu-backdrop" @click="closeEventMenu">
      <div class="popover timeline-action-menu" @click.stop>
        <template v-if="state.menuEvent.deletedAt">
          <button type="button" class="pop-item" @click="restoreEvent(state.menuEvent)">
            <TimelineLucideIcon name="restore" :stroke-width="1.8" class="pop-item-ic" />
            <span class="lbl">恢复</span>
          </button>
          <span class="pop-divider"></span>
          <button type="button" class="pop-item danger" @click="permanentlyDeleteEvent(state.menuEvent)">
            <TimelineLucideIcon name="trash" :stroke-width="1.8" class="pop-item-ic" />
            <span class="lbl">永久删除</span>
          </button>
        </template>
        <template v-else>
          <button type="button" class="pop-item" @click="moveEventToTrash(state.menuEvent)">
            <TimelineLucideIcon name="trash" :stroke-width="1.8" class="pop-item-ic" />
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
      :open="state.settingsOpen"
      :brand-name="state.config.brandName"
      :media-config="state.config.media"
      :active-topic-title="activeTopicTitle"
      :has-topic="Boolean(state.activeTopicId)"
      @close="state.settingsOpen = false"
      @export-data="exportCurrentTopic"
      @update-media="updateMediaConfig"
    />

    <CommandPalette
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
