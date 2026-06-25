<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import EventDetailPane from "@/components/timeline-notes/EventDetailPane.vue";
import TimelineFeed from "@/components/timeline-notes/TimelineFeed.vue";
import TopicSidebar from "@/components/timeline-notes/TopicSidebar.vue";
import { api } from "@/composables/useApi";
import { pushToast } from "@/composables/useToast";
import {
  compareTimelineEvents,
  groupTimelineEvents,
  matchesEventSearch,
  matchesPropertyFilter,
  normalizeTopicColumns,
} from "@/utils/timelineNotes";

const route = useRoute();
const router = useRouter();
const detailPaneRef = ref(null);

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
  rightOpen: false,
  leftWidth: Number.parseInt(readStorage(LEFT_WIDTH_KEY, "268"), 10) || 268,
  rightWidth: Number.parseInt(readStorage(RIGHT_WIDTH_KEY, "412"), 10) || 412,
  showPreview: readStorage(PREVIEW_KEY, "on") !== "off",
  searchRequestKey: 0,
  editPreview: null,
});

let resizeCleanup = null;

const workspaceStyle = computed(() => ({
  "--left-w": `${state.leftWidth}px`,
  "--right-w": `${state.rightWidth}px`,
}));

const activeTopicTitle = computed(
  () => state.activeTopicMeta?.title || state.topics.find((topic) => topic.id === state.activeTopicId)?.title || "编年"
);

const topicColumns = computed(() => normalizeTopicColumns(state.activeTopicMeta?.columns));
const selectedEvent = computed(() => state.events.find((event) => event.id === state.selectedEventId) || null);

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

function previewedEvents() {
  const preview = state.editPreview;
  if (!preview || !preview.id) return state.events;
  return state.events.map((event) => (event.id === preview.id ? applyPreviewOverlay(event, preview) : event));
}

function filterEvents({ filter = state.sidebarFilter, propertyFilter = state.propertyFilter, era = state.activeEra, search = state.searchQuery } = {}) {
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

async function loadWorkspace(options = {}) {
  const {
    preferredTopicId = null,
    preferredEventId = parseRouteNumber("event"),
    preferredMode = parseRouteMode(),
    openDetail = preferredMode !== "view" || preferredEventId !== null,
  } = options;

  state.loading = true;
  state.error = "";
  state.detailError = "";
  state.sidebarFilter = parseRouteFilter();
  state.propertyFilter = parseRoutePropertyFilter();
  state.activeEra = parseRouteString("era");
  state.locateDate = parseRouteString("date");

  try {
    const [config, topics] = await Promise.all([api.getConfig(), api.listTopics()]);
    state.config.brandName = "编年";
    state.topics = topics;

    const resolvedTopicId =
      preferredTopicId && topics.some((topic) => topic.id === preferredTopicId)
        ? preferredTopicId
        : parseRouteNumber("topic") && topics.some((topic) => topic.id === parseRouteNumber("topic"))
          ? parseRouteNumber("topic")
          : topics[0]?.id ?? null;

    state.activeTopicId = resolvedTopicId;
    if (!resolvedTopicId) {
      state.activeTopicMeta = null;
      state.events = [];
      state.selectedEventId = null;
      state.rightOpen = false;
      return;
    }

    const [meta, response] = await Promise.all([api.getTopicMeta(resolvedTopicId), api.getTimelineEvents(resolvedTopicId)]);
    state.activeTopicMeta = meta;
    state.eventBounds = response.bounds || null;
    state.hasMore = Boolean(response.hasMore);
    state.nextCursor = response.nextCursor || null;
    state.events = [...(response.items || [])].sort(compareTimelineEvents);

    setDefaultSelection(preferredEventId);
    state.detailMode =
      preferredMode === "create"
        ? "create"
        : preferredMode === "edit" && state.selectedEventId
          ? "edit"
          : "view";
    state.rightOpen = Boolean(openDetail && (state.selectedEventId || state.detailMode === "create"));
    document.title = `${state.config.brandName} Chronicle`;
  } catch (error) {
    state.error = error.message || "加载失败";
    pushToast(`加载失败：${error.message}`, "error");
  } finally {
    state.loading = false;
  }
}

function runOrConfirm(action) {
  if ((state.detailMode === "edit" || state.detailMode === "create") && state.detailDirty) {
    state.pendingAction = action;
    state.confirmUnsaved = true;
    return;
  }
  action();
}

function closeUnsavedDialog() {
  state.confirmUnsaved = false;
  state.pendingAction = null;
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

function selectEvent(eventId) {
  runOrConfirm(async () => {
    state.selectedEventId = eventId;
    state.detailMode = "view";
    state.detailError = "";
    state.rightOpen = true;
    await syncRouteState({ eventId, mode: "view" });
  });
}

function openRelatedEvent(eventId) {
  if (!state.events.some((event) => event.id === eventId)) return;
  selectEvent(eventId);
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
    state.detailMode = "create";
    state.rightOpen = true;
    await syncRouteState({ eventId: state.selectedEventId, mode: "create" });
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
    await loadWorkspace({
      preferredTopicId: state.activeTopicId,
      preferredEventId: result.id,
      preferredMode: "view",
      openDetail: true,
    });
    state.selectedEventId = result.id;
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
  if (topicId === state.activeTopicId) return;
  runOrConfirm(async () => {
    state.propertyFilter = { key: "", value: "" };
    state.activeEra = "";
    state.searchQuery = "";
    await loadWorkspace({
      preferredTopicId: topicId,
      preferredEventId: null,
      preferredMode: "view",
      openDetail: false,
    });
    state.rightOpen = false;
    await syncRouteState({ topicId, eventId: null, propertyFilter: { key: "", value: "" }, era: "", mode: "view" });
  });
}

async function createTopic(name) {
  try {
    const created = await api.createTopic(name);
    pushToast(`已创建笔记本：${name}`);
    await loadWorkspace({
      preferredTopicId: created.id,
      preferredEventId: null,
      preferredMode: "view",
      openDetail: false,
    });
    state.rightOpen = false;
    await syncRouteState({ topicId: created.id, eventId: null });
  } catch (error) {
    pushToast(`创建笔记本失败：${error.message}`, "error");
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
    applyFilterState({ filter });
    await syncRouteState({ filter, eventId: state.rightOpen ? state.selectedEventId : null });
  });
}

function updatePropertyFilter(propertyFilter) {
  runOrConfirm(async () => {
    applyFilterState({ propertyFilter });
    await syncRouteState({ propertyFilter, eventId: state.rightOpen ? state.selectedEventId : null });
  });
}

function updateActiveEra(era) {
  runOrConfirm(async () => {
    applyFilterState({ era });
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
    const result = await api.updateEventFavorite(event.id, !event.favorite);
    const target = state.events.find((item) => item.id === event.id);
    if (target) {
      target.favorite = result.favorite;
      target.updatedAt = result.updatedAt;
    }
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
  if (!event?.id) return;
  try {
    const result = await api.softDeleteEvent(event.id);
    const target = state.events.find((item) => item.id === event.id);
    if (target) target.deletedAt = result.deletedAt || new Date().toISOString();
    closeEventMenu();
    applyFilterState();
    await syncRouteState({ eventId: state.rightOpen ? state.selectedEventId : null });
    pushToast("已移入回收站");
  } catch (error) {
    pushToast(`删除失败：${error.message}`, "error");
  }
}

async function restoreEvent(event) {
  if (!event?.id) return;
  try {
    const result = await api.restoreEvent(event.id);
    const target = state.events.find((item) => item.id === event.id);
    if (target) {
      target.deletedAt = result.deletedAt;
      target.updatedAt = result.updatedAt;
    }
    closeEventMenu();
    applyFilterState();
    await syncRouteState({ eventId: state.rightOpen ? state.selectedEventId : null });
    pushToast("已恢复");
  } catch (error) {
    pushToast(`恢复失败：${error.message}`, "error");
  }
}

async function permanentlyDeleteEvent(event) {
  if (!event?.id) return;
  try {
    await api.permanentlyDeleteEvent(event.id);
    state.events = state.events.filter((item) => item.id !== event.id);
    closeEventMenu();
    applyFilterState();
    await syncRouteState({ eventId: state.rightOpen ? state.selectedEventId : null });
    pushToast("已永久删除");
  } catch (error) {
    pushToast(`永久删除失败：${error.message}`, "error");
  }
}

function togglePreview() {
  state.showPreview = !state.showPreview;
  writeStorage(PREVIEW_KEY, state.showPreview ? "on" : "off");
}

function focusFeedSearch() {
  state.searchRequestKey += 1;
}

// A brand-new option created in the picker is folded into its property and
// persisted to the topic immediately (optimistic local update first).
async function addPropertyOption({ key, option }) {
  if (!state.activeTopicId || !key || !option?.id) return;
  const columns = normalizeTopicColumns(state.activeTopicMeta?.columns).map((column) => {
    if (column.key !== key) return column;
    if ((column.options || []).some((existing) => existing.id === option.id)) return column;
    return { ...column, options: [...(column.options || []), option] };
  });
  state.activeTopicMeta = { ...state.activeTopicMeta, columns };
  try {
    const meta = await api.updateTopicMeta(state.activeTopicId, {
      title: state.activeTopicMeta?.title || "",
      subtitle: state.activeTopicMeta?.subtitle || "",
      columns,
    });
    state.activeTopicMeta = meta;
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
      deleted += 1;
    }
    pushToast(topics.length > 1 ? `已删除 ${topics.length} 个笔记本` : `已删除笔记本：${topics[0].title || topics[0].name}`);
  } catch (error) {
    pushToast(deleted ? `已删除 ${deleted} 个，其余失败：${error.message}` : `删除失败：${error.message}`, "error");
  } finally {
    // Reconcile the UI to server truth whether all / some / none succeeded, so a
    // mid-loop failure never leaves the card open over already-deleted notebooks.
    state.confirmDeleteTopics = null;
    if (deleted) {
      await loadWorkspace({ preferredTopicId: null, preferredEventId: null, preferredMode: "view", openDetail: false });
      state.rightOpen = false;
      await syncRouteState({ topicId: state.activeTopicId, eventId: null });
    }
  }
}

async function saveTopicColumns(columns) {
  if (!state.activeTopicId) return;
  const normalized = normalizeTopicColumns(columns);
  state.columnSaving = true;
  try {
    const meta = await api.updateTopicMeta(state.activeTopicId, {
      title: state.activeTopicMeta?.title || "",
      subtitle: state.activeTopicMeta?.subtitle || "",
      columns: normalized,
    });
    state.activeTopicMeta = meta;
    pushToast("列定义已保存");
  } catch (error) {
    pushToast(`列定义保存失败：${error.message}`, "error");
  } finally {
    state.columnSaving = false;
  }
}

function exportCurrentTopic() {
  if (!state.activeTopicId) return;
  api.exportCurrentDataRange(state.activeTopicId);
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

onMounted(() => {
  loadWorkspace();
});

onBeforeUnmount(() => {
  resizeCleanup?.();
});

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
  <div class="app timeline-workspace" :class="{ 'right-closed': !state.rightOpen }" :style="workspaceStyle">
    <TopicSidebar
      :brand="state.config.brandName"
      :topics="state.topics"
      :events="state.events"
      :active-topic-id="state.activeTopicId"
      :active-filter="state.sidebarFilter"
      :columns="topicColumns"
      :property-filter="state.propertyFilter"
      :active-era="state.activeEra"
      :loading="state.loading"
      :error="state.error"
      @create-event="startCreateEvent"
      @create-topic="createTopic"
      @delete-topic="requestDeleteTopic"
      @batch-delete-topics="requestBatchDeleteTopics"
      @focus-search="focusFeedSearch"
      @open-settings="state.settingsOpen = true"
      @select-era="updateActiveEra"
      @select-topic="selectTopic"
      @update:filter="updateSidebarFilter"
      @update:property-filter="updatePropertyFilter"
    />

    <TimelineFeed
      :loading="state.loading"
      :error="state.error"
      :has-topic="Boolean(state.activeTopicId)"
      :topic-title="activeTopicTitle"
      :event-count="visibleEvents.length"
      :empty-reason="feedEmptyReason"
      :search-query="state.searchQuery"
      :groups="groupedEvents"
      :selected-event-id="state.selectedEventId"
      :locate-date="state.locateDate"
      :columns="topicColumns"
      :column-saving="state.columnSaving"
      :show-preview="state.showPreview"
      :search-request-key="state.searchRequestKey"
      @create-event="startCreateEvent"
      @locate-date="locateDate"
      @save-columns="saveTopicColumns"
      @select-event="selectEvent"
      @toggle-favorite="toggleFavorite"
      @toggle-preview="togglePreview"
      @update:searchQuery="updateSearchQuery"
    />

    <EventDetailPane
      ref="detailPaneRef"
      :event="selectedEvent"
      :candidate-events="state.events"
      :topic-title="activeTopicTitle"
      :topic-columns="topicColumns"
      :loading="state.detailLoading"
      :error="state.detailError"
      :mode="state.detailMode"
      :saving="state.saving"
      @cancel="cancelDetailEdit"
      @close="closeDetailPane"
      @edit="startEditSelectedEvent"
      @open-menu="openEventMenu"
      @open-related="openRelatedEvent"
      @save="saveEvent"
      @toggle-favorite="toggleFavorite"
      @create-option="addPropertyOption"
      @dirty-change="state.detailDirty = $event"
      @preview-change="state.editPreview = $event"
    />

    <div id="rzLeft" class="resizer" @mousedown="startResize('left', $event)"></div>
    <div v-if="state.rightOpen" id="rzRight" class="resizer" @mousedown="startResize('right', $event)"></div>

    <div v-if="state.menuEvent" class="timeline-menu-backdrop" @click="closeEventMenu">
      <div class="timeline-action-menu" @click.stop>
        <template v-if="state.menuEvent.deletedAt">
          <button type="button" @click="restoreEvent(state.menuEvent)">恢复</button>
          <span class="pop-divider"></span>
          <button type="button" class="danger" @click="permanentlyDeleteEvent(state.menuEvent)">永久删除</button>
        </template>
        <template v-else>
          <button type="button" @click="moveEventToTrash(state.menuEvent)">移入回收站</button>
        </template>
      </div>
    </div>

    <div v-if="state.confirmUnsaved" class="timeline-modal-backdrop">
      <section class="timeline-confirm-card" role="dialog" aria-modal="true" aria-label="未保存修改">
        <h3>有未保存的修改</h3>
        <p>切换视图或事件前，请选择保存、放弃或继续编辑。</p>
        <div class="timeline-confirm-actions">
          <button type="button" class="timeline-primary-btn" @click="saveAndContinue">保存</button>
          <button type="button" class="timeline-secondary-btn" @click="discardAndContinue">放弃</button>
          <button type="button" class="timeline-secondary-btn" @click="closeUnsavedDialog">取消</button>
        </div>
      </section>
    </div>

    <div v-if="state.confirmDeleteTopics" class="timeline-modal-backdrop">
      <section class="timeline-confirm-card" role="dialog" aria-modal="true" aria-label="删除笔记本">
        <h3>{{ state.confirmDeleteTopics.length > 1 ? `删除 ${state.confirmDeleteTopics.length} 个笔记本` : "删除笔记本" }}</h3>
        <p v-if="state.confirmDeleteTopics.length > 1">将永久删除所选 {{ state.confirmDeleteTopics.length }} 个笔记本及其全部时间点，此操作不可恢复。</p>
        <p v-else>将永久删除「{{ state.confirmDeleteTopics[0].title || state.confirmDeleteTopics[0].name }}」及其全部时间点，此操作不可恢复。</p>
        <div class="timeline-confirm-actions">
          <button type="button" class="timeline-primary-btn danger" @click="confirmDeleteTopicNow">删除</button>
          <button type="button" class="timeline-secondary-btn" @click="closeDeleteTopic">取消</button>
        </div>
      </section>
    </div>

    <div v-if="state.settingsOpen" class="timeline-modal-backdrop">
      <section class="timeline-settings-card" role="dialog" aria-modal="true" aria-label="设置">
        <div class="timeline-settings-head">
          <h3>设置</h3>
          <button type="button" class="timeline-icon-btn" aria-label="关闭设置" @click="state.settingsOpen = false">×</button>
        </div>
        <div class="timeline-settings-body">
          <button type="button" class="timeline-settings-action" @click="exportCurrentTopic">导出当前笔记本</button>
          <div class="timeline-settings-meta">
            <span>品牌</span>
            <strong>{{ state.config.brandName }}</strong>
          </div>
          <div class="timeline-settings-meta">
            <span>当前专题</span>
            <strong>{{ activeTopicTitle }}</strong>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>
