<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import TopicSidebar from "@/components/timeline-notes/TopicSidebar.vue";
import TimelineFeed from "@/components/timeline-notes/TimelineFeed.vue";
import EventDetailPane from "@/components/timeline-notes/EventDetailPane.vue";
import { api } from "@/composables/useApi";
import { pushToast } from "@/composables/useToast";
import { compareTimelineEvents, groupTimelineEvents, matchesEventSearch } from "@/utils/timelineNotes";

const route = useRoute();
const router = useRouter();
const detailPaneRef = ref(null);
const stageStyle = reactive({
  "--tn-sidebar-width": "293px",
  "--tn-detail-width": "552px",
  "--tn-detail-content-width": "508px",
  "--tn-feed-left": "32px",
  "--tn-year-label-width": "92px",
  "--tn-rail-width": "56px",
  "--tn-card-width": "531px",
  "--tn-card-text-width": "480px",
  "--tn-card-title-width": "390px",
  "--tn-composer-left": "61px",
  "--tn-composer-width": "662px",
});

const DETAIL_MODES = new Set(["view", "edit", "create"]);
const FILTERS = new Set(["all", "today", "week", "favorite", "trash"]);
const STAGE_WIDTH = 1920;

function clampNumber(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function clampToAvailable(value, min, max) {
  const safeMax = Math.max(1, max);
  if (safeMax < min) return safeMax;
  return clampNumber(value, min, safeMax);
}

const state = reactive({
  loading: true,
  saving: false,
  error: "",
  detailLoading: true,
  detailError: "",
  config: {
    brandName: "时间线笔记",
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
  activeTag: "",
  locateDate: "",
  detailDirty: false,
  confirmUnsaved: false,
  pendingAction: null,
  afterSaveAction: null,
  menuEvent: null,
  settingsOpen: false,
});

function parseRouteNumber(name) {
  const raw = route?.query?.[name];
  const value = Number.parseInt(Array.isArray(raw) ? raw[0] : raw, 10);
  return Number.isNaN(value) ? null : value;
}

function updateStageScale() {
  if (typeof window === "undefined") return;
  const viewportWidth = Math.max(window.innerWidth || STAGE_WIDTH, 1);
  const widthRatio = viewportWidth / STAGE_WIDTH;
  const sidebarWidth = clampNumber(293 * widthRatio, 220, 320);
  const detailWidth = clampNumber(552 * widthRatio, 360, 620);
  const detailContentWidth = Math.max(280, detailWidth - 44);
  const middleWidth = Math.max(0, viewportWidth - sidebarWidth - detailWidth);
  const feedLeft = clampNumber((middleWidth * 32) / 1075, 22, 40);
  const yearLabelWidth = clampNumber((middleWidth * 92) / 1075, 70, 104);
  const railWidth = clampNumber((middleWidth * 56) / 1075, 38, 64);
  const cardAvailableWidth = middleWidth - feedLeft - yearLabelWidth - railWidth - 44;
  const cardWidth = clampToAvailable((middleWidth * 531) / 1075, 360, Math.min(780, cardAvailableWidth));
  const textWidth = Math.max(260, cardWidth - 51);
  const titleWidth = Math.max(240, cardWidth - 141);
  const composerLeft = clampNumber((middleWidth * 61) / 1075, 28, 76);
  const composerAvailableWidth = middleWidth - composerLeft - 32;
  const composerWidth = clampToAvailable((middleWidth * 662) / 1075, 420, Math.min(920, composerAvailableWidth));

  stageStyle["--tn-sidebar-width"] = `${sidebarWidth}px`;
  stageStyle["--tn-detail-width"] = `${detailWidth}px`;
  stageStyle["--tn-detail-content-width"] = `${detailContentWidth}px`;
  stageStyle["--tn-feed-left"] = `${feedLeft}px`;
  stageStyle["--tn-year-label-width"] = `${yearLabelWidth}px`;
  stageStyle["--tn-rail-width"] = `${railWidth}px`;
  stageStyle["--tn-card-width"] = `${cardWidth}px`;
  stageStyle["--tn-card-text-width"] = `${textWidth}px`;
  stageStyle["--tn-card-title-width"] = `${titleWidth}px`;
  stageStyle["--tn-composer-left"] = `${composerLeft}px`;
  stageStyle["--tn-composer-width"] = `${composerWidth}px`;
}

function parseRouteMode() {
  const raw = String(Array.isArray(route?.query?.mode) ? route.query.mode[0] : route?.query?.mode || "view");
  return DETAIL_MODES.has(raw) ? raw : "view";
}

function parseRouteFilter() {
  const raw = String(Array.isArray(route?.query?.filter) ? route.query.filter[0] : route?.query?.filter || "all");
  return FILTERS.has(raw) ? raw : "all";
}

function parseRouteString(name) {
  const raw = route?.query?.[name];
  return String(Array.isArray(raw) ? raw[0] : raw || "");
}

async function syncRouteState(next = {}) {
  const nextQuery = {
    ...route.query,
    topic: next.topicId ? String(next.topicId) : undefined,
    event: next.eventId ? String(next.eventId) : undefined,
    mode: next.mode && next.mode !== "view" ? next.mode : undefined,
    filter: next.filter && next.filter !== "all" ? next.filter : undefined,
    tag: next.tag || undefined,
    date: next.date || undefined,
  };
  await router.replace({ query: nextQuery });
}

function resolveTopicId(topics, preferredTopicId = null) {
  if (preferredTopicId && topics.some((topic) => topic.id === preferredTopicId)) return preferredTopicId;
  const fromRoute = parseRouteNumber("topic");
  if (fromRoute && topics.some((topic) => topic.id === fromRoute)) return fromRoute;
  return topics[0]?.id ?? null;
}

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

function matchesTag(event, tag) {
  if (!tag) return true;
  return (event.tags || []).includes(tag) || (event.items || []).some((item) => item.tag === tag);
}

function filterEvents({ filter = state.sidebarFilter, tag = state.activeTag, search = state.searchQuery } = {}) {
  return [...state.events]
    .filter((event) => matchesMainFilter(event, filter))
    .filter((event) => matchesTag(event, tag))
    .filter((event) => matchesEventSearch(event, search))
    .sort(compareTimelineEvents);
}

function selectFirstVisible(filter = state.sidebarFilter, tag = state.activeTag) {
  const items = filterEvents({ filter, tag, search: state.searchQuery });
  state.selectedEventId = items[0]?.id ?? null;
  return state.selectedEventId;
}

function setSelectedEvent(items, preferredEventId = null, preserveCurrent = true) {
  if (preferredEventId && items.some((event) => event.id === preferredEventId)) {
    state.selectedEventId = preferredEventId;
    return;
  }
  if (preserveCurrent && items.some((event) => event.id === state.selectedEventId)) return;
  state.selectedEventId = items[0]?.id ?? null;
}

function canEditEvent(event) {
  return Boolean(event && !event.deletedAt);
}

async function loadWorkspace(options = {}) {
  const {
    preferredTopicId = null,
    preferredEventId = parseRouteNumber("event"),
    preserveSelection = true,
    preferredMode = parseRouteMode(),
    clearBeforeLoad = false,
  } = options;

  state.loading = true;
  state.error = "";
  state.detailError = "";
  state.sidebarFilter = parseRouteFilter();
  state.activeTag = parseRouteString("tag");
  state.locateDate = parseRouteString("date");

  if (clearBeforeLoad || preferredEventId !== null || preferredMode !== "view") {
    state.detailLoading = true;
  }

  if (clearBeforeLoad) {
    state.activeTopicMeta = null;
    state.events = [];
    state.eventBounds = null;
    state.hasMore = false;
    state.nextCursor = null;
    state.selectedEventId = null;
    state.detailLoading = false;
  }

  try {
    const [config, topics] = await Promise.all([api.getConfig(), api.listTopics()]);
    state.config = {
      brandName: String(config?.brandName || "").trim() || "时间线笔记",
    };
    state.topics = topics;

    const routeTopicId = parseRouteNumber("topic");
    if (routeTopicId !== null && !topics.some((topic) => topic.id === routeTopicId)) {
      state.activeTopicId = null;
      state.activeTopicMeta = null;
      state.events = [];
      state.eventBounds = null;
      state.selectedEventId = null;
      state.error = "指定笔记本不存在";
      state.detailLoading = false;
      document.title = "时间线笔记";
      return;
    }

    const nextTopicId = resolveTopicId(topics, preferredTopicId);
    state.activeTopicId = nextTopicId;

    if (nextTopicId && parseRouteNumber("topic") !== nextTopicId) {
      await router.replace({ query: { ...route.query, topic: String(nextTopicId) } });
    }

    if (!nextTopicId) {
      state.activeTopicMeta = null;
      state.events = [];
      state.selectedEventId = null;
      document.title = "时间线笔记";
      return;
    }

    const [meta, rawEvents] = await Promise.all([
      api.getTopicMeta(nextTopicId),
      api.getTimelineEvents(nextTopicId),
    ]);

    state.activeTopicMeta = meta;
    state.eventBounds = rawEvents.bounds || null;
    state.hasMore = Boolean(rawEvents.hasMore);
    state.nextCursor = rawEvents.nextCursor || null;
    state.events = [...(rawEvents.items || [])].sort(compareTimelineEvents);

    const filtered = filterEvents({ filter: state.sidebarFilter, tag: state.activeTag, search: state.searchQuery });
    if (preferredEventId !== null) {
      if (state.events.some((event) => event.id === preferredEventId)) {
        state.selectedEventId = preferredEventId;
        state.detailError = "";
      } else {
        state.selectedEventId = null;
        state.detailError = "指定事件不存在";
      }
    } else {
      setSelectedEvent(filtered, null, preserveSelection);
      state.detailError = "";
    }

    state.detailMode =
      preferredMode === "create"
        ? "create"
        : preferredMode === "edit" && canEditEvent(state.events.find((event) => event.id === state.selectedEventId))
          ? "edit"
          : "view";

    if (preferredMode === "edit" && state.detailMode === "view") {
      await syncRouteState({
        topicId: state.activeTopicId,
        eventId: state.selectedEventId,
        mode: "view",
        filter: state.sidebarFilter,
        tag: state.activeTag,
        date: state.locateDate,
      });
    }
    document.title = `${meta.title || meta.name || "时间线笔记"} - 时间线笔记`;
  } catch (error) {
    state.error = error.message || "加载失败";
    pushToast(`加载时间线失败：${error.message}`, "error");
  } finally {
    state.loading = false;
    state.detailLoading = false;
  }
}

const activeTopic = computed(() => state.topics.find((topic) => topic.id === state.activeTopicId) || null);
const activeTopicTitle = computed(
  () => state.activeTopicMeta?.title || activeTopic.value?.title || activeTopic.value?.name || "未选择笔记本"
);

const sidebarFilteredEvents = computed(() =>
  [...state.events]
    .filter((event) => matchesMainFilter(event, state.sidebarFilter))
    .filter((event) => matchesTag(event, state.activeTag))
    .sort(compareTimelineEvents)
);

const visibleEvents = computed(() => sidebarFilteredEvents.value.filter((event) => matchesEventSearch(event, state.searchQuery)));
const groupedEvents = computed(() => groupTimelineEvents(sidebarFilteredEvents.value, "year", state.searchQuery));

const selectedEvent = computed(() => state.events.find((event) => event.id === state.selectedEventId) || null);

const feedEmptyReason = computed(() => {
  if (state.error) return "";
  if (!state.activeTopicId) return "先创建或选择一个笔记本。";
  if (state.sidebarFilter === "trash" && sidebarFilteredEvents.value.length === 0) return "回收站为空。";
  if (state.searchQuery.trim()) return "当前搜索条件下没有找到记录。";
  if (state.activeTag) return "当前标签下没有记录。";
  return "当前筛选下没有记录。";
});

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
  runOrConfirm(() => {
    state.selectedEventId = eventId;
    state.detailError = "";
    state.detailMode = "view";
    syncRouteState({
      topicId: state.activeTopicId,
      eventId,
      mode: "view",
      filter: state.sidebarFilter,
      tag: state.activeTag,
      date: state.locateDate,
    });
  });
}

function openRelatedEvent(eventId) {
  if (!state.events.some((event) => event.id === eventId)) return;
  selectEvent(eventId);
}

function startCreateEvent() {
  runOrConfirm(() => {
    if (!state.activeTopicId) {
      pushToast("请先创建或选择一个笔记本", "error");
      return;
    }
    state.detailMode = "create";
    syncRouteState({
      topicId: state.activeTopicId,
      eventId: state.selectedEventId,
      mode: "create",
      filter: state.sidebarFilter,
      tag: state.activeTag,
      date: state.locateDate,
    });
  });
}

function startEditSelectedEvent() {
  if (!canEditEvent(selectedEvent.value)) return;
  state.detailMode = "edit";
  syncRouteState({
    topicId: state.activeTopicId,
    eventId: state.selectedEventId,
    mode: "edit",
    filter: state.sidebarFilter,
    tag: state.activeTag,
    date: state.locateDate,
  });
}

function cancelDetailEdit() {
  runOrConfirm(() => {
    state.detailMode = "view";
    if (!state.selectedEventId && visibleEvents.value.length > 0) {
      state.selectedEventId = visibleEvents.value[0].id;
    }
    syncRouteState({
      topicId: state.activeTopicId,
      eventId: state.selectedEventId,
      mode: "view",
      filter: state.sidebarFilter,
      tag: state.activeTag,
      date: state.locateDate,
    });
  });
}

async function cleanupDeletedImages(imageOps, currentImage) {
  const pending = [...new Set((imageOps?.deleteImages || []).filter((filename) => filename && filename !== currentImage))];
  if (pending.length === 0) return;
  await Promise.allSettled(pending.map((filename) => api.deleteImage(filename)));
}

async function saveEvent(payload) {
  if (!state.activeTopicId) {
    pushToast("请先选择一个笔记本", "error");
    return;
  }

  state.saving = true;
  try {
    const result = payload.id
      ? await api.updateEvent(payload.id, payload.data)
      : await api.createTopicEvent(state.activeTopicId, payload.data);

    await cleanupDeletedImages(payload.imageOps, payload.data.image);
    state.detailDirty = false;
    await loadWorkspace({
      preferredTopicId: state.activeTopicId,
      preferredEventId: result.id,
      preserveSelection: false,
      preferredMode: "view",
      clearBeforeLoad: false,
    });
    await syncRouteState({
      topicId: state.activeTopicId,
      eventId: result.id,
      mode: "view",
      filter: state.sidebarFilter,
      tag: state.activeTag,
      date: state.locateDate,
    });
    pushToast(payload.id ? "事件已更新" : "事件已创建");

    const afterSaveAction = state.afterSaveAction;
    state.afterSaveAction = null;
    if (afterSaveAction) {
      await nextTick();
      afterSaveAction();
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
    await loadWorkspace({
      preferredTopicId: topicId,
      preserveSelection: false,
      clearBeforeLoad: true,
    });
    selectFirstVisible();
    await syncRouteState({
      topicId,
      eventId: state.selectedEventId,
      mode: state.detailMode,
      filter: state.sidebarFilter,
      tag: state.activeTag,
      date: state.locateDate,
    });
  });
}

async function createTopic(name) {
  try {
    const created = await api.createTopic(name);
    pushToast(`已创建笔记本：${name}`);
    await loadWorkspace({
      preferredTopicId: created.id,
      preserveSelection: false,
      clearBeforeLoad: true,
    });
    await syncRouteState({
      topicId: created.id,
      eventId: state.selectedEventId,
      mode: state.detailMode,
      filter: state.sidebarFilter,
      tag: state.activeTag,
      date: state.locateDate,
    });
  } catch (error) {
    pushToast(`创建笔记本失败：${error.message}`, "error");
  }
}

function updateSidebarFilter(filter) {
  runOrConfirm(() => {
    state.sidebarFilter = filter;
    if (state.activeTag && !filterEvents({ filter, tag: state.activeTag, search: "" }).length) {
      state.activeTag = "";
    }
    const eventId = selectFirstVisible(state.sidebarFilter, state.activeTag);
    state.detailMode = "view";
    syncRouteState({
      topicId: state.activeTopicId,
      eventId,
      mode: "view",
      filter: state.sidebarFilter,
      tag: state.activeTag,
      date: state.locateDate,
    });
  });
}

function updateActiveTag(tag) {
  runOrConfirm(() => {
    state.activeTag = tag;
    const eventId = selectFirstVisible(state.sidebarFilter, state.activeTag);
    state.detailMode = "view";
    syncRouteState({
      topicId: state.activeTopicId,
      eventId,
      mode: "view",
      filter: state.sidebarFilter,
      tag: state.activeTag,
      date: state.locateDate,
    });
  });
}

function updateSearchQuery(value) {
  state.searchQuery = value;
  if (state.detailMode === "view" && !visibleEvents.value.some((event) => event.id === state.selectedEventId)) {
    state.selectedEventId = visibleEvents.value[0]?.id ?? null;
  }
}

function locateDate(value) {
  state.locateDate = value;
  syncRouteState({
    topicId: state.activeTopicId,
    eventId: state.selectedEventId,
    mode: state.detailMode,
    filter: state.sidebarFilter,
    tag: state.activeTag,
    date: value,
  });
}

async function toggleFavorite(event) {
  if (!event || event.deletedAt) return;
  try {
    const nextFavorite = !event.favorite;
    const result = await api.updateEventFavorite(event.id, nextFavorite);
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
    if (state.sidebarFilter !== "trash") {
      const nextId = selectFirstVisible();
      state.detailMode = "view";
      await syncRouteState({
        topicId: state.activeTopicId,
        eventId: nextId,
        mode: "view",
        filter: state.sidebarFilter,
        tag: state.activeTag,
        date: state.locateDate,
      });
    }
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
    if (state.sidebarFilter === "trash") {
      const nextId = selectFirstVisible();
      state.detailMode = "view";
      await syncRouteState({
        topicId: state.activeTopicId,
        eventId: nextId,
        mode: "view",
        filter: state.sidebarFilter,
        tag: state.activeTag,
        date: state.locateDate,
      });
    }
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
    let nextId = state.selectedEventId;
    if (state.selectedEventId === event.id) {
      nextId = selectFirstVisible();
    }
    closeEventMenu();
    await syncRouteState({
      topicId: state.activeTopicId,
      eventId: nextId,
      mode: "view",
      filter: state.sidebarFilter,
      tag: state.activeTag,
      date: state.locateDate,
    });
    pushToast("已永久删除");
  } catch (error) {
    pushToast(`永久删除失败：${error.message}`, "error");
  }
}

async function copyMarkdown(event) {
  const text = `# ${event.headline || event.displayLabel}\n\n${event.bodyMarkdown || ""}`.trim();
  try {
    await navigator.clipboard.writeText(text);
    pushToast("Markdown 已复制");
  } catch {
    pushToast("当前浏览器不允许写入剪贴板", "error");
  } finally {
    closeEventMenu();
  }
}

function exportEvent(event) {
  const text = `# ${event.headline || event.displayLabel}\n\n${event.bodyMarkdown || ""}`.trim();
  const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${event.headline || "timeline-event"}.md`;
  link.click();
  URL.revokeObjectURL(url);
  closeEventMenu();
}

function exportCurrentTopic() {
  if (!state.activeTopicId) return;
  api.exportCurrentDataRange(state.activeTopicId);
}

watch(
  () => [route.query.event, route.query.mode, route.query.filter, route.query.tag, route.query.date],
  () => {
    state.sidebarFilter = parseRouteFilter();
    state.activeTag = parseRouteString("tag");
    state.locateDate = parseRouteString("date");
    const nextEventId = parseRouteNumber("event");
    const nextMode = parseRouteMode();

    if (nextEventId && state.events.some((event) => event.id === nextEventId)) {
      state.selectedEventId = nextEventId;
      state.detailError = "";
    }

    if (nextMode === "create") {
      state.detailMode = "create";
    } else if (nextMode === "edit" && canEditEvent(selectedEvent.value)) {
      state.detailMode = "edit";
    } else if (nextMode === "edit") {
      state.detailMode = "view";
      syncRouteState({
        topicId: state.activeTopicId,
        eventId: state.selectedEventId,
        mode: "view",
        filter: state.sidebarFilter,
        tag: state.activeTag,
        date: state.locateDate,
      });
    } else if (!state.detailDirty) {
      state.detailMode = "view";
    }
  }
);

onMounted(() => {
  updateStageScale();
  window.addEventListener("resize", updateStageScale, { passive: true });
  loadWorkspace({ clearBeforeLoad: true });
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", updateStageScale);
});
</script>

<template>
  <div class="timeline-workspace" :style="stageStyle">
    <TopicSidebar
      :brand="state.config.brandName"
      :topics="state.topics"
      :events="state.events"
      :active-topic-id="state.activeTopicId"
      :active-filter="state.sidebarFilter"
      :active-tag="state.activeTag"
      :loading="state.loading"
      :error="state.error"
      @create-event="startCreateEvent"
      @create-topic="createTopic"
      @select-topic="selectTopic"
      @update:filter="updateSidebarFilter"
      @update:tag="updateActiveTag"
      @open-settings="state.settingsOpen = true"
    />

    <TimelineFeed
      :loading="state.loading"
      :error="state.error"
      :has-topic="Boolean(state.activeTopicId)"
      :event-count="visibleEvents.length"
      :empty-reason="feedEmptyReason"
      :search-query="state.searchQuery"
      :groups="groupedEvents"
      :selected-event-id="state.selectedEventId"
      :locate-date="state.locateDate"
      @create-event="startCreateEvent"
      @select-event="selectEvent"
      @update:searchQuery="updateSearchQuery"
      @locate-date="locateDate"
      @toggle-favorite="toggleFavorite"
      @open-menu="openEventMenu"
    />

    <EventDetailPane
      ref="detailPaneRef"
      :event="selectedEvent"
      :candidate-events="state.events"
      :topic-title="activeTopicTitle"
      :loading="state.detailLoading"
      :error="state.detailError"
      :mode="state.detailMode"
      :saving="state.saving"
      @cancel="cancelDetailEdit"
      @create="startCreateEvent"
      @edit="startEditSelectedEvent"
      @open-related="openRelatedEvent"
      @save="saveEvent"
      @toggle-favorite="toggleFavorite"
      @open-menu="openEventMenu"
      @dirty-change="state.detailDirty = $event"
    />

    <div v-if="state.menuEvent" class="timeline-menu-backdrop" @click="closeEventMenu">
      <div class="timeline-action-menu" @click.stop>
        <template v-if="state.menuEvent.deletedAt">
          <button type="button" @click="restoreEvent(state.menuEvent)">恢复</button>
          <button type="button" class="danger" @click="permanentlyDeleteEvent(state.menuEvent)">永久删除</button>
        </template>
        <template v-else>
          <button type="button" @click="moveEventToTrash(state.menuEvent)">移入回收站</button>
          <button type="button" @click="copyMarkdown(state.menuEvent)">复制 Markdown</button>
          <button type="button" @click="exportEvent(state.menuEvent)">导出当前事件</button>
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

    <div v-if="state.settingsOpen" class="timeline-modal-backdrop">
      <section class="timeline-settings-card" role="dialog" aria-modal="true" aria-label="设置">
        <div class="timeline-settings-head">
          <h3>设置</h3>
          <button type="button" class="timeline-icon-btn" aria-label="关闭设置" @click="state.settingsOpen = false">×</button>
        </div>
        <div class="timeline-settings-body">
          <button type="button" class="timeline-settings-action" @click="exportCurrentTopic">导出当前笔记本</button>
          <div class="timeline-settings-meta">
            <span>版本</span>
            <strong>timeline notes / 1920 one-view</strong>
          </div>
          <div class="timeline-settings-meta">
            <span>视觉基准</span>
            <strong>timeline_notes_pixel_perfect_1920x1080_one_view.html</strong>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>
