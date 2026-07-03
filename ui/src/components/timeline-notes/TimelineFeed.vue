<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import ColumnConfigPopover from "@/components/timeline-notes/ColumnConfigPopover.vue";
import HighlightedText from "@/components/timeline-notes/HighlightedText.vue";
import NotebookChip from "@/components/timeline-notes/NotebookChip.vue";
import TimelineLucideIcon from "@/components/timeline-notes/TimelineLucideIcon.vue";
import {
  aggregateOptionChips,
  availableDisplayViews,
  buildBoardGroups,
  buildEventPreview,
  buildTimelineGridTemplate,
  buildVisibleTimelineColumns,
  clampTimelineColumnWidth,
  compareEventsBySort,
  dateKeyFromLocator,
  DISPLAY_VIEW_META,
  eventColumnValue,
  isCheckboxChecked,
  isDefaultSort,
  isOptionColumn,
  pickBoardColumn,
  reorderSortLevels,
  resolveDisplayStyle,
  resolvePropertyChips,
  SORT_FIELD_META,
  sortFieldsForView,
  timelineHasTrailingSpacer,
  timelineTimeColumnWidth,
} from "@/utils/timelineNotes";

// Center feed caps option chips per cell; any extras collapse into a muted "+N"
// so a multi-value event never silently hides tags. Single source for the cap so
// the slice and the overflow count can't drift.
const FEED_CHIP_LIMIT = 2;

const props = defineProps({
  loading: {
    type: Boolean,
    default: false,
  },
  error: {
    type: String,
    default: "",
  },
  hasTopic: {
    type: Boolean,
    default: false,
  },
  topicTitle: {
    type: String,
    default: "",
  },
  filterContextLabel: {
    type: String,
    default: "",
  },
  filterContextClearable: {
    type: Boolean,
    default: false,
  },
  topicId: {
    type: Number,
    default: null,
  },
  topics: {
    type: Array,
    default: () => [],
  },
  eventCount: {
    type: Number,
    default: 0,
  },
  emptyReason: {
    type: String,
    default: "",
  },
  searchQuery: {
    type: String,
    default: "",
  },
  groups: {
    type: Array,
    default: () => [],
  },
  allEvents: {
    type: Array,
    default: () => [],
  },
  selectedEventId: {
    type: Number,
    default: null,
  },
  locateDate: {
    type: String,
    default: "",
  },
  columns: {
    type: Array,
    default: () => [],
  },
  emptyColumnKeys: {
    type: Array,
    default: () => [],
  },
  columnSaving: {
    type: Boolean,
    default: false,
  },
  showPreview: {
    type: Boolean,
    default: true,
  },
  showSource: {
    type: Boolean,
    default: false,
  },
  globalFavoritesMode: {
    type: Boolean,
    default: false,
  },
  showColumnControls: {
    type: Boolean,
    default: true,
  },
  displayStyle: {
    type: String,
    default: "timeline",
  },
  // Ordered sort levels [{ field, dir }, …] for the center column, already clamped
  // by the page to what the effective view can sort (docs/center-sort-design.md).
  sort: {
    type: Array,
    default: () => [{ field: "time", dir: 1 }],
  },
  // Timeline/outline grouping dimension: era | year | month.
  groupBy: {
    type: String,
    default: "era",
  },
  capabilities: {
    type: Array,
    default: () => [],
  },
  showViewSwitcher: {
    type: Boolean,
    default: false,
  },
  searchPlaceholder: {
    type: String,
    default: "搜索当前时间线",
  },
  searchRequestKey: {
    type: Number,
    default: 0,
  },
  commandSearch: {
    type: Boolean,
    default: false,
  },
  trashView: {
    type: Boolean,
    default: false,
  },
  mobile: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits([
  "create-event",
  "create-mindmap",
  "select-event",
  "update:searchQuery",
  "locate-date",
  "toggle-favorite",
  "toggle-preview",
  "save-columns",
  "resize-column",
  "change-sort",
  "change-group-by",
  "batch-favorite",
  "batch-trash",
  "batch-restore",
  "batch-permanent-delete",
  "open-command-palette",
  "change-view",
  "clear-context-filter",
]);

// Single mutually-exclusive popover layer for the toolbar (spec §2.1).
// '' | 'locator' | 'columns' | 'views' | 'sort' | 'newtype' — only one open at a time.
const activePopover = ref("");
const locatorValue = ref("");
const searchOpen = ref(false);
const searchInputRef = ref(null);
const feedRef = ref(null);
const rowRefs = new Map();
const widthOverrides = ref({});
// 时间 / 事件 are built-in (not in the persisted column set), so their user widths
// live in localStorage keyed per notebook — no data-contract change. Custom column
// widths still persist to the backend via the existing resize-column path.
const builtinWidths = ref({});
const COLUMN_WIDTH_STORAGE_PREFIX = "tl-colw:";
const BUILTIN_WIDTH_BOUNDS = { time: [64, 240], title: [180, 760] };
let stopColumnResize = null;

// Note-level batch multi-select: a toolbar toggle reveals row checkboxes; row
// clicks then toggle selection instead of opening the detail pane. Batch actions
// reuse the existing per-event state-patch endpoints (favorite/soft-delete/
// restore/permanent), so no full-payload reconstruction is needed.
const selectMode = ref(false);
const selectedIds = ref([]);
// Outline view: era groups the user has collapsed (keyed by group.key).
const collapsedGroups = ref(new Set());

function isRowSelected(id) {
  return selectedIds.value.includes(id);
}

function toggleSelectMode() {
  selectMode.value = !selectMode.value;
  if (!selectMode.value) selectedIds.value = [];
}

function toggleRowSelection(id) {
  selectedIds.value = isRowSelected(id) ? selectedIds.value.filter((value) => value !== id) : [...selectedIds.value, id];
}

function onRowClick(id) {
  if (selectMode.value) toggleRowSelection(id);
  else emit("select-event", id);
}

function submitBatch(action) {
  if (selectedIds.value.length) emit(action, [...selectedIds.value]);
}

// Single-row delete (hover-revealed): reuse the batch endpoints with a one-id
// array — trash view permanently purges (page confirms), otherwise soft-trash.
function deleteRow(event) {
  emit(props.trashView ? "batch-permanent-delete" : "batch-trash", [event.id]);
}

// Drop selected ids that are no longer in the visible list (filter/search change).
watch(
  () => props.groups,
  () => {
    const visible = new Set(props.groups.flatMap((group) => group.items.map((event) => event.id)));
    selectedIds.value = selectedIds.value.filter((id) => visible.has(id));
  },
  { deep: true }
);

function togglePopover(name) {
  if (name === "columns" && !props.showColumnControls) return;
  if (name === "views" && !props.showViewSwitcher) return;
  activePopover.value = activePopover.value === name ? "" : name;
}

// Display-style views (axis 1). Mobile stays on the timeline; otherwise the
// effective view is the persisted style resolved against the live capability set
// (services/timeline.py is SSOT) so an unimplemented/incapable style degrades to
// table instead of rendering blank.
function effectiveView() {
  if (props.mobile) return "timeline";
  // Cross-notebook favorites always renders as a flat list (docs §4) so it can sort
  // by 收藏时间 without an era grouping to fight.
  if (props.globalFavoritesMode) return "list";
  return resolveDisplayStyle(props.displayStyle, props.capabilities);
}

function switcherViews() {
  return availableDisplayViews(props.capabilities);
}

function currentViewIcon() {
  return DISPLAY_VIEW_META[effectiveView()]?.icon || "timeline";
}

function pickView(view) {
  if (!view?.enabled) return;
  activePopover.value = "";
  if (view.key !== effectiveView()) emit("change-view", view.key);
}

// 新建 = note-type picker (hard requirement): entry runs the current create flow,
// mindmap creates + opens a canvas. The page owns both handlers.
function pickNoteType(type) {
  activePopover.value = "";
  emit(type === "mindmap" ? "create-mindmap" : "create-event");
}

function flatEvents() {
  return props.groups.flatMap((group) => group.items);
}

// Sort control (docs/center-sort-design.md). The page owns the ordered sort levels
// and clamps them per view; here we surface options and emit changes. Flat views
// (table/list/gallery) re-sort the flattened set directly, bypassing the era
// grouping; grouped views read props.groups (already ordered by the page).
const GROUP_BY_OPTIONS = [
  { key: "era", label: "时期", icon: "outline" },
  { key: "year", label: "年", icon: "calendar" },
  { key: "month", label: "月", icon: "calendar" },
];

function sortedFlatEvents() {
  return [...flatEvents()].sort(compareEventsBySort(props.sort, props.columns));
}

// Fields the active view offers (favorites is flat and adds 收藏时间).
function sortOptions() {
  return sortFieldsForView(effectiveView(), props.columns, props.globalFavoritesMode);
}

function primaryLevel() {
  return props.sort[0] || { field: "time", dir: 1 };
}

// The sort level (if any) for a field — drives the table header caret.
function levelForField(field) {
  return props.sort.find((level) => level.field === field) || null;
}

function sortLabel(field) {
  return sortOptions().find((option) => option.field === field)?.label || SORT_FIELD_META[field]?.label || field;
}

function sortIcon(field) {
  return sortOptions().find((option) => option.field === field)?.icon || SORT_FIELD_META[field]?.icon || "alignLeft";
}

// Fields not yet used by a level = the "添加排序层" candidates.
function addableSortFields() {
  const used = new Set(props.sort.map((level) => level.field));
  return sortOptions().filter((option) => !used.has(option.field));
}

// Table header / grouped-view direction click = set a single primary level (replace
// the whole sort); re-clicking the current sole sort flips its direction (fork A).
function applyHeaderSort(field) {
  const dir = props.sort.length === 1 && props.sort[0].field === field ? props.sort[0].dir * -1 : 1;
  emit("change-sort", [{ field, dir }]);
}

function applySortDir(dir) {
  emit("change-sort", [{ field: "time", dir }]);
}

// Multi-sort editor (flat views): flip one level, drop one, or append a new one.
function flipSortLevel(index) {
  emit("change-sort", props.sort.map((level, i) => (i === index ? { ...level, dir: level.dir * -1 } : level)));
}

function removeSortLevel(index) {
  const next = props.sort.filter((_, i) => i !== index);
  emit("change-sort", next.length ? next : [{ field: "time", dir: 1 }]);
}

function addSortLevel(field) {
  emit("change-sort", [...props.sort, { field, dir: 1 }]);
}

// Drag-to-reorder the sort levels (order = priority; dragging a level up promotes
// it toward the primary key). The grip is a sibling of the flip button — never a
// child — so a drag never fires the row's flip click: a click only fires when
// mousedown and mouseup share the flip button as their common ancestor. We track
// a from/over index and only emit once on drop (avoids a PUT per pointer step
// once sort persists to the backend).
const sortDragFrom = ref(-1);
const sortDragOver = ref(-1);
let sortDragStartY = 0;
let sortDragRowH = 32;

function sortDragging() {
  return sortDragFrom.value >= 0;
}

// Rows to render: a live preview of the pending reorder while dragging.
function displaySortLevels() {
  return sortDragging()
    ? reorderSortLevels(props.sort, sortDragFrom.value, sortDragOver.value)
    : props.sort;
}

function startSortLevelDrag(index, event) {
  if (props.sort.length < 2) return;
  sortDragFrom.value = index;
  sortDragOver.value = index;
  sortDragStartY = event.clientY;
  sortDragRowH = event.currentTarget?.closest(".pop-sort-level")?.offsetHeight || 32;
  window.addEventListener("mousemove", onSortLevelDragMove);
  window.addEventListener("mouseup", endSortLevelDrag);
  // Same fallbacks as the column-resize drag: a button-released check inside the
  // move handler and a blur listener, so releasing the mouse OUTSIDE the viewport
  // (or Alt-Tabbing away mid-drag) ends the drag instead of leaving a stuck
  // ghost-drag whose stale mouseup would silently commit on the next click.
  window.addEventListener("blur", endSortLevelDrag);
}

function onSortLevelDragMove(event) {
  if (event.buttons !== 1) {
    endSortLevelDrag();
    return;
  }
  const steps = Math.round((event.clientY - sortDragStartY) / sortDragRowH);
  const next = Math.max(0, Math.min(props.sort.length - 1, sortDragFrom.value + steps));
  if (next !== sortDragOver.value) sortDragOver.value = next;
}

function endSortLevelDrag() {
  window.removeEventListener("mousemove", onSortLevelDragMove);
  window.removeEventListener("mouseup", endSortLevelDrag);
  window.removeEventListener("blur", endSortLevelDrag);
  const from = sortDragFrom.value;
  const to = sortDragOver.value;
  if (from < 0) return;
  sortDragFrom.value = -1;
  sortDragOver.value = -1;
  if (to >= 0 && from !== to) {
    emit("change-sort", reorderSortLevels(props.sort, from, to));
  }
}

onBeforeUnmount(() => {
  window.removeEventListener("mousemove", onSortLevelDragMove);
  window.removeEventListener("mouseup", endSortLevelDrag);
  window.removeEventListener("blur", endSortLevelDrag);
});

function pickGroupBy(key) {
  emit("change-group-by", key);
}

// Board view: the option property to group by (SSOT-gated `board` capability
// guarantees one exists when this view is reachable) and the resulting columns.
function boardColumn() {
  return pickBoardColumn(props.columns);
}

function boardGroups() {
  return buildBoardGroups(flatEvents(), boardColumn(), props.sort);
}

// Gallery view: every entry as a card, ordered by the active sort; the primary
// image (thumb preferred) rides the index DTO, empty for imageless entries (which
// render a placeholder).
function galleryEvents() {
  return sortedFlatEvents();
}

function eventThumb(event) {
  return event?.thumbUrl || event?.imageUrl || "";
}

// List/gallery cards surface the same option chips as the timeline, aggregated
// across the visible (non-empty) option columns and capped by FEED_CHIP_LIMIT with
// a +N overflow (see aggregateOptionChips) so a card never invents or hides tags.
function rowChips(event) {
  return aggregateOptionChips(event, props.columns, props.emptyColumnKeys);
}

// Outline view: collapsible era groups (reuses the era grouping the page already
// computed in props.groups). Collapsed keys are component-local, reset per notebook.
function isGroupCollapsed(key) {
  return collapsedGroups.value.has(key);
}

function toggleGroup(key) {
  const next = new Set(collapsedGroups.value);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  collapsedGroups.value = next;
}

function columnsWithWidthOverrides() {
  return (Array.isArray(props.columns) ? props.columns : []).map((column) => ({
    ...column,
    width: widthOverrides.value[column.key] ?? column.width,
  }));
}

function clampBuiltinWidth(key, width, fallback = 96) {
  const [min, max] = BUILTIN_WIDTH_BOUNDS[key] || [72, 320];
  const next = Math.round(Number(width));
  if (!Number.isFinite(next)) return fallback;
  return Math.min(max, Math.max(min, next));
}

function loadBuiltinWidths(topicId) {
  if (!topicId || typeof localStorage === "undefined") return {};
  try {
    const raw = JSON.parse(localStorage.getItem(COLUMN_WIDTH_STORAGE_PREFIX + topicId) || "{}") || {};
    const next = {};
    for (const key of ["time", "title"]) {
      if (Number.isFinite(Number(raw[key]))) next[key] = clampBuiltinWidth(key, raw[key]);
    }
    return next;
  } catch {
    return {};
  }
}

function saveBuiltinWidth(key, width) {
  const next = { ...builtinWidths.value, [key]: width };
  builtinWidths.value = next;
  if (!props.topicId || typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(COLUMN_WIDTH_STORAGE_PREFIX + props.topicId, JSON.stringify(next));
  } catch {
    /* storage disabled/full — width still applies for the session */
  }
}

// 时间 default auto-sizes to content (96 / 128 for long BC dates) unless the user
// pinned it; 事件 is the flex fill column (null) until the user drags it.
function effectiveTimeWidth() {
  const override = builtinWidths.value.time;
  if (Number.isFinite(override)) return override;
  return timelineTimeColumnWidth(props.groups.flatMap((group) => group.items));
}

function effectiveTitleWidth() {
  const override = builtinWidths.value.title;
  return Number.isFinite(override) ? override : null;
}

function hasTrailingSpacer() {
  return !props.mobile && timelineHasTrailingSpacer(null, null, effectiveTitleWidth());
}

function visibleColumns() {
  const columns = buildVisibleTimelineColumns(columnsWithWidthOverrides(), props.emptyColumnKeys, effectiveTimeWidth(), effectiveTitleWidth());
  if (!props.mobile) return columns;
  return columns.filter((column) => column.key === "time" || column.key === "title");
}

function rowGrid() {
  if (props.mobile) return "28px 86px minmax(0, 1fr) 58px";
  return buildTimelineGridTemplate(columnsWithWidthOverrides(), props.emptyColumnKeys, effectiveTimeWidth(), effectiveTitleWidth());
}

function setRowRef(id, element) {
  if (element) {
    rowRefs.set(id, element);
  } else {
    rowRefs.delete(id);
  }
}

function openSearch() {
  activePopover.value = "";
  searchOpen.value = true;
  nextTick(() => searchInputRef.value?.focus());
}

// The fixed search icon toggles the field: open+focus when closed; when open it
// refocuses if there is a query, or collapses when empty.
function toggleSearch() {
  if (props.commandSearch) {
    activePopover.value = "";
    searchOpen.value = false;
    emit("open-command-palette");
    return;
  }
  if (searchOpen.value) {
    if (String(props.searchQuery || "").trim()) {
      searchInputRef.value?.focus();
    } else {
      searchOpen.value = false;
    }
  } else {
    openSearch();
  }
}

function closeSearchIfEmpty() {
  if (!String(props.searchQuery || "").trim()) {
    searchOpen.value = false;
  }
}

function stopResizingColumn() {
  stopColumnResize?.();
  stopColumnResize = null;
}

function startColumnResize(column, event) {
  if (props.mobile || !column?.key) return;
  event.preventDefault();
  event.stopPropagation();
  const key = column.key;
  const builtin = column.builtIn === true;
  // The flex 事件 column has no fixed width — seed the drag from its rendered
  // header width so the first drag doesn't jump.
  const headEl = event.currentTarget.closest?.(".tl-col-head");
  const measured = headEl ? Math.round(headEl.getBoundingClientRect().width) : 0;
  const startWidth = Number(column.width) || measured || 96;
  const startX = event.clientX;
  const onMove = (moveEvent) => {
    if (moveEvent.buttons !== 1) {
      onUp();
      return;
    }
    const raw = startWidth + (moveEvent.clientX - startX);
    if (builtin) {
      builtinWidths.value = { ...builtinWidths.value, [key]: clampBuiltinWidth(key, raw, startWidth) };
    } else {
      widthOverrides.value = { ...widthOverrides.value, [key]: clampTimelineColumnWidth(Math.round(raw), startWidth) };
    }
  };
  const onUp = () => {
    window.removeEventListener("mousemove", onMove);
    window.removeEventListener("mouseup", onUp);
    window.removeEventListener("blur", onUp);
    stopColumnResize = null;
    if (builtin) {
      saveBuiltinWidth(key, builtinWidths.value[key] ?? startWidth);
    } else {
      emit("resize-column", { key, width: widthOverrides.value[key] ?? startWidth });
    }
  };
  stopResizingColumn();
  stopColumnResize = () => {
    window.removeEventListener("mousemove", onMove);
    window.removeEventListener("mouseup", onUp);
    window.removeEventListener("blur", onUp);
  };
  window.addEventListener("mousemove", onMove);
  window.addEventListener("mouseup", onUp);
  window.addEventListener("blur", onUp);
}

function focusDate(value) {
  const targetKey = dateKeyFromLocator(value);
  if (targetKey === null) return;
  const events = props.groups.flatMap((group) => group.items);
  const target = events.find((event) => event.dateKey >= targetKey) || events.at(-1);
  if (!target) return;
  emit("select-event", target.id);
  nextTick(() => rowRefs.get(target.id)?.scrollIntoView({ behavior: "smooth", block: "center" }));
}

function submitLocator() {
  const value = String(locatorValue.value || "").trim();
  if (!value) return;
  activePopover.value = "";
  emit("locate-date", value);
  focusDate(value);
}

function closePopovers(event) {
  if (!(event.target instanceof Element)) return;
  if (event.target.closest(".tl-pop")) return;
  if (activePopover.value && event.target.closest(`[data-popover-anchor=\"${activePopover.value}\"]`)) return;
  activePopover.value = "";
}

function handleDocumentKeydown(event) {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k" && props.commandSearch) {
    activePopover.value = "";
    searchOpen.value = false;
    return;
  }
  if (event.key !== "Escape") return;
  activePopover.value = "";
  closeSearchIfEmpty();
}

watch(
  () => props.searchRequestKey,
  () => openSearch()
);

watch(
  () => props.showColumnControls,
  (enabled) => {
    if (!enabled && activePopover.value === "columns") activePopover.value = "";
  }
);

watch(
  () => props.columns,
  () => {
    widthOverrides.value = {};
  },
  { deep: true }
);

// Built-in (时间 / 事件) widths are per-notebook in localStorage — reload them
// whenever the active notebook changes (and on first mount).
watch(
  () => props.topicId,
  (topicId) => {
    builtinWidths.value = loadBuiltinWidths(topicId);
    // Drop outline collapse state (era keys are per-notebook) on notebook switch.
    collapsedGroups.value = new Set();
  },
  { immediate: true }
);

watch(
  () => props.locateDate,
  (value) => {
    locatorValue.value = value || "";
    if (value) {
      focusDate(value);
    }
  },
  { immediate: true }
);

watch(
  () => props.searchQuery,
  (value) => {
    if (String(value || "").trim()) {
      searchOpen.value = true;
    }
  },
  { immediate: true }
);

watch(
  () => props.selectedEventId,
  (eventId) => {
    if (!eventId) return;
    nextTick(() => rowRefs.get(eventId)?.scrollIntoView({ block: "nearest" }));
  }
);

watch(
  () => props.groups,
  () => {
    if (props.locateDate) {
      nextTick(() => focusDate(props.locateDate));
    }
  },
  { deep: true }
);

onMounted(() => {
  document.addEventListener("pointerdown", closePopovers);
  document.addEventListener("keydown", handleDocumentKeydown);
});

onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", closePopovers);
  document.removeEventListener("keydown", handleDocumentKeydown);
  stopResizingColumn();
});
</script>

<template>
  <section class="col timeline" :class="{ 'preview-off': !props.showPreview, 'source-on': props.showSource }">
    <div class="tl-bar">
      <div class="tl-head">
        <h2>{{ props.topicTitle || "历史事件" }}</h2>
        <span class="tl-count">· 共 {{ props.eventCount }} 条</span>
        <span v-if="props.filterContextLabel" class="tl-context">
          <span class="tl-context-label">{{ props.filterContextLabel }}</span>
          <button
            v-if="props.filterContextClearable"
            type="button"
            class="iconbtn sm tl-context-clear"
            title="清空当前筛选"
            @click.stop="emit('clear-context-filter')"
          >
            <TimelineLucideIcon name="close" :stroke-width="1.5" />
          </button>
        </span>
      </div>
      <span class="spacer"></span>

      <div class="tl-actions">
        <div class="searchbox" :class="{ open: searchOpen }" id="searchbox">
          <input
            ref="searchInputRef"
            :value="props.searchQuery"
            type="search"
            :placeholder="props.searchPlaceholder"
            @input="emit('update:searchQuery', $event.target.value)"
            @blur="closeSearchIfEmpty"
          />
          <button id="searchBtn" type="button" class="sb-icon" title="搜索" @mousedown.prevent @click.stop="toggleSearch">
            <TimelineLucideIcon name="search" :stroke-width="1.5" />
          </button>
        </div>

        <button
          type="button"
          class="iconbtn lg"
          data-popover-anchor="locator"
          :class="{ on: activePopover === 'locator' }"
          title="时间定位"
          @click.stop="togglePopover('locator')"
        >
          <TimelineLucideIcon name="calendarSearch" :stroke-width="1.5" />
        </button>

        <button
          v-if="props.showColumnControls"
          id="colBtn"
          type="button"
          class="iconbtn lg"
          data-popover-anchor="columns"
          :class="{ on: activePopover === 'columns' }"
          title="列设置"
          @click.stop="togglePopover('columns')"
        >
          <TimelineLucideIcon name="columns" :stroke-width="1.5" />
        </button>

        <button
          v-if="effectiveView() === 'timeline'"
          id="previewBtn"
          type="button"
          class="iconbtn lg"
          :class="{ on: props.showPreview }"
          title="显示预览"
          @click="emit('toggle-preview')"
        >
          <TimelineLucideIcon name="alignLeft" :stroke-width="1.5" />
        </button>

        <button
          type="button"
          class="iconbtn lg"
          :class="{ on: selectMode }"
          :title="selectMode ? '退出多选' : '多选'"
          @click.stop="toggleSelectMode"
        >
          <TimelineLucideIcon name="listChecks" :stroke-width="1.5" />
        </button>

        <button
          v-if="!props.mobile"
          type="button"
          class="iconbtn lg"
          data-popover-anchor="sort"
          :class="{ on: activePopover === 'sort' || !isDefaultSort(props.sort) }"
          title="排序"
          @click.stop="togglePopover('sort')"
        >
          <TimelineLucideIcon name="arrowUpDown" :stroke-width="1.5" />
        </button>

        <button
          v-if="props.showViewSwitcher"
          type="button"
          class="iconbtn lg"
          data-popover-anchor="views"
          :class="{ on: activePopover === 'views' }"
          title="切换视图"
          @click.stop="togglePopover('views')"
        >
          <TimelineLucideIcon :name="currentViewIcon()" :stroke-width="1.5" />
        </button>
      </div>

      <span class="tl-divider" aria-hidden="true"></span>

      <button
        type="button"
        class="iconbtn lg primary"
        data-popover-anchor="newtype"
        :class="{ on: activePopover === 'newtype' }"
        title="新建笔记"
        @click.stop="togglePopover('newtype')"
      >
        <TimelineLucideIcon name="plusCircle" :stroke-width="1.5" />
      </button>

      <div v-if="activePopover" class="popover tl-pop" :class="`tl-pop-${activePopover}`">
        <form v-if="activePopover === 'locator'" class="tl-pop-body" @submit.prevent="submitLocator">
          <div class="pop-title">时间定位</div>
          <label class="pop-field">
            <span>输入日期</span>
            <input v-model="locatorValue" type="text" placeholder="1840 / 1840-06 / 1840-06-01" />
          </label>
          <div class="pop-foot">
            <button type="submit" class="iconbtn sm primary" title="定位">
              <TimelineLucideIcon name="check" :stroke-width="1.5" />
            </button>
          </div>
        </form>

        <ColumnConfigPopover
          v-else-if="activePopover === 'columns' && props.showColumnControls"
          :key="props.topicId"
          :topic-id="props.topicId"
          :columns="props.columns"
          :events="props.allEvents"
          :saving="props.columnSaving"
          @save-columns="emit('save-columns', $event)"
        />

        <template v-else-if="activePopover === 'views' && props.showViewSwitcher">
          <div class="pop-title">视图</div>
          <button
            v-for="view in switcherViews()"
            :key="view.key"
            type="button"
            class="pop-item"
            :class="{ 'is-active': view.key === effectiveView(), 'is-locked': !view.enabled }"
            :disabled="!view.enabled"
            :title="view.enabled ? '' : view.requires"
            @click="pickView(view)"
          >
            <TimelineLucideIcon class="pop-item-ic" :name="view.icon" :stroke-width="1.5" />
            <span class="pop-item-label">{{ view.label }}</span>
            <TimelineLucideIcon v-if="view.key === effectiveView()" class="pop-item-check" name="check" :stroke-width="2" />
          </button>
        </template>

        <template v-else-if="activePopover === 'sort'">
          <template v-if="effectiveView() === 'timeline' || effectiveView() === 'outline'">
            <div class="pop-title">分组</div>
            <button
              v-for="opt in GROUP_BY_OPTIONS"
              :key="opt.key"
              type="button"
              class="pop-item"
              :class="{ 'is-active': props.groupBy === opt.key }"
              @click="pickGroupBy(opt.key)"
            >
              <TimelineLucideIcon class="pop-item-ic" :name="opt.icon" :stroke-width="1.5" />
              <span class="pop-item-label">{{ opt.label }}</span>
              <TimelineLucideIcon v-if="props.groupBy === opt.key" class="pop-item-check" name="check" :stroke-width="2" />
            </button>
            <div class="pop-subtitle">方向</div>
            <button type="button" class="pop-item" :class="{ 'is-active': primaryLevel().dir >= 0 }" @click="applySortDir(1)">
              <TimelineLucideIcon class="pop-item-ic" name="chevronUp" :stroke-width="1.5" />
              <span class="pop-item-label">时间正序</span>
              <TimelineLucideIcon v-if="primaryLevel().dir >= 0" class="pop-item-check" name="check" :stroke-width="2" />
            </button>
            <button type="button" class="pop-item" :class="{ 'is-active': primaryLevel().dir < 0 }" @click="applySortDir(-1)">
              <TimelineLucideIcon class="pop-item-ic" name="chevronDown" :stroke-width="1.5" />
              <span class="pop-item-label">时间倒序</span>
              <TimelineLucideIcon v-if="primaryLevel().dir < 0" class="pop-item-check" name="check" :stroke-width="2" />
            </button>
          </template>
          <template v-else>
            <div class="pop-title">排序</div>
            <div
              v-for="(level, i) in displaySortLevels()"
              :key="level.field"
              class="pop-item pop-sort-level"
              :class="{ 'is-dragging': sortDragging() && i === sortDragOver }"
            >
              <span
                v-if="props.sort.length > 1"
                class="pop-sort-grip"
                title="拖拽调整排序优先级"
                @mousedown.prevent.stop="startSortLevelDrag(i, $event)"
                @click.stop
              >
                <TimelineLucideIcon name="grip" :stroke-width="1.5" />
              </span>
              <button
                type="button"
                class="pop-sort-flip"
                :title="`点按切换「${sortLabel(level.field)}」升/降序`"
                @click="flipSortLevel(i)"
              >
                <TimelineLucideIcon class="pop-item-ic" :name="sortIcon(level.field)" :stroke-width="1.5" />
                <span class="pop-item-label">{{ sortLabel(level.field) }}</span>
                <TimelineLucideIcon class="pop-item-check" :name="level.dir < 0 ? 'chevronDown' : 'chevronUp'" :stroke-width="2" />
              </button>
              <span v-if="props.sort.length > 1" class="pop-sort-del" title="移除该排序层" @click.stop="removeSortLevel(i)">
                <TimelineLucideIcon name="close" :stroke-width="1.6" />
              </span>
            </div>
            <template v-if="addableSortFields().length">
              <div class="pop-subtitle">添加排序层</div>
              <button
                v-for="field in addableSortFields()"
                :key="field.field"
                type="button"
                class="pop-item pop-sort-add"
                @click="addSortLevel(field.field)"
              >
                <TimelineLucideIcon class="pop-item-ic" :name="field.icon" :stroke-width="1.5" />
                <span class="pop-item-label">{{ field.label }}</span>
                <TimelineLucideIcon class="pop-item-add-ic" name="plusSign" :stroke-width="1.8" />
              </button>
            </template>
          </template>
        </template>

        <template v-else-if="activePopover === 'newtype'">
          <div class="pop-title">新建</div>
          <button type="button" class="pop-item" @click="pickNoteType('entry')">
            <TimelineLucideIcon class="pop-item-ic" name="note" :stroke-width="1.5" />
            <span class="pop-item-label">条目</span>
          </button>
          <button type="button" class="pop-item" @click="pickNoteType('mindmap')">
            <TimelineLucideIcon class="pop-item-ic" name="mindmap" :stroke-width="1.5" />
            <span class="pop-item-label">思维导图</span>
          </button>
        </template>
      </div>
    </div>

    <div v-if="selectMode" class="batch-bar">
      <span class="batch-cnt">已选 {{ selectedIds.length }} 条</span>
      <template v-if="props.trashView">
        <button type="button" class="iconbtn sm" :disabled="!selectedIds.length" title="批量恢复" @click="submitBatch('batch-restore')">
          <TimelineLucideIcon name="restore" :stroke-width="1.5" />
        </button>
        <button type="button" class="iconbtn sm" :disabled="!selectedIds.length" title="批量永久删除" @click="submitBatch('batch-permanent-delete')">
          <TimelineLucideIcon name="trash" :stroke-width="1.5" />
        </button>
      </template>
      <template v-else>
        <button v-if="!props.globalFavoritesMode" type="button" class="iconbtn sm" :disabled="!selectedIds.length" title="批量收藏" @click="submitBatch('batch-favorite')">
          <TimelineLucideIcon name="star" :stroke-width="1.5" />
        </button>
        <button type="button" class="iconbtn sm" :disabled="!selectedIds.length" title="批量移入回收站" @click="submitBatch('batch-trash')">
          <TimelineLucideIcon name="trash" :stroke-width="1.5" />
        </button>
      </template>
      <button type="button" class="iconbtn sm" title="退出多选" @click="toggleSelectMode">
        <TimelineLucideIcon name="close" :stroke-width="1.5" />
      </button>
    </div>

    <div v-if="props.loading" class="feed-empty">正在加载时间线...</div>
    <div v-else-if="props.error" class="feed-empty">{{ props.error }}</div>
    <div v-else-if="!props.groups.length" class="feed-empty">{{ props.emptyReason }}</div>
    <div v-else-if="effectiveView() === 'timeline'" ref="feedRef" class="feed scroll">
      <div class="feed-inner" :style="{ '--rowgrid': rowGrid() }">
        <div class="tl-cols" id="tlCols">
          <span></span>
          <span
            v-for="column in visibleColumns()"
            :key="column.key"
            class="tl-col-head"
            :class="{ 'is-resizable': !props.mobile }"
          >
            <span>{{ column.label }}</span>
            <button
              v-if="!props.mobile"
              type="button"
              class="tl-col-resizer"
              :title="`拖动调整${column.label}列宽`"
              @mousedown="startColumnResize(column, $event)"
              @click.stop
            ></button>
          </span>
          <span v-if="hasTrailingSpacer()" aria-hidden="true"></span>
          <span></span>
        </div>

        <section v-for="group in props.groups" :key="group.key" class="era">
          <div class="era-head">
            <span class="rdot"></span>
            <div class="era-main">
              <b><HighlightedText :text="group.title" :query="props.searchQuery" /></b>
              <span>{{ group.subtitle }}</span>
            </div>
          </div>

          <button
            v-for="event in group.items"
            :key="event.id"
            :ref="(element) => setRowRef(event.id, element)"
            type="button"
            class="row"
            :class="{
              active: !selectMode && event.id === props.selectedEventId,
              selected: selectMode && isRowSelected(event.id),
            }"
            @click="onRowClick(event.id)"
          >
            <span v-if="selectMode" class="tcheck" :class="{ on: isRowSelected(event.id) }">
              <TimelineLucideIcon v-if="isRowSelected(event.id)" name="check" :stroke-width="2.4" />
            </span>
            <span v-else class="rdot"></span>
            <template v-for="column in visibleColumns()" :key="column.key">
              <span v-if="column.key === 'time'" class="c-time" :title="eventColumnValue(event, column)"><HighlightedText :text="eventColumnValue(event, column)" :query="props.searchQuery" /></span>
              <span v-else-if="column.key === 'title'" class="c-title">
                <b class="ev-name" :title="eventColumnValue(event, column)"><HighlightedText :text="eventColumnValue(event, column)" :query="props.searchQuery" /></b>
                <span v-if="event.noteType === 'mindmap'" class="ev-type" title="思维导图">
                  <TimelineLucideIcon name="mindmap" :stroke-width="1.5" />
                </span>
                <span v-if="event.attachments?.length || event.attachmentCount" class="clip">
                  <TimelineLucideIcon name="paperclip" :stroke-width="1.5" />
                </span>
                <NotebookChip v-if="props.showSource" :topic-id="event.topicId" :topics="props.topics" />
                <span class="ev-sum"><HighlightedText :text="buildEventPreview(event, 90)" :query="props.searchQuery" /></span>
              </span>
              <span v-else-if="isOptionColumn(column)" class="c-tags">
                <span
                  v-for="chip in resolvePropertyChips(event, column).slice(0, FEED_CHIP_LIMIT)"
                  :key="chip.value"
                  class="td"
                  :style="{ '--dot': chip.color }"
                >
                  <i></i><HighlightedText :text="chip.label" :query="props.searchQuery" />
                </span>
                <span
                  v-if="resolvePropertyChips(event, column).length > FEED_CHIP_LIMIT"
                  class="td-more"
                  :title="resolvePropertyChips(event, column).slice(FEED_CHIP_LIMIT).map((chip) => chip.label).join('、')"
                  >+{{ resolvePropertyChips(event, column).length - FEED_CHIP_LIMIT }}</span
                >
                <span v-if="!resolvePropertyChips(event, column).length" class="c-source c-empty">—</span>
              </span>
              <span v-else-if="column.type === 'checkbox'" class="c-source c-check">
                <TimelineLucideIcon
                  v-if="isCheckboxChecked(event.extra?.[column.key])"
                  name="check"
                  :stroke-width="2.2"
                />
                <span v-else class="c-empty">—</span>
              </span>
              <span
                v-else
                class="c-source"
                :class="{ 'c-empty': eventColumnValue(event, column) === '—' }"
                :title="eventColumnValue(event, column) === '—' ? null : eventColumnValue(event, column)"
              ><HighlightedText :text="eventColumnValue(event, column)" :query="props.searchQuery" /></span>
            </template>
            <span v-if="hasTrailingSpacer()" class="c-spacer" aria-hidden="true"></span>
            <span
              v-if="!selectMode"
              class="row-act"
              :title="props.trashView ? '永久删除' : '移入回收站'"
              @click.stop="deleteRow(event)"
            >
              <TimelineLucideIcon name="trash" :stroke-width="1.5" />
            </span>
            <span
              class="c-star"
              :class="{ on: event.favorite }"
              @click.stop="emit('toggle-favorite', event)"
            >
              <TimelineLucideIcon name="star" :stroke-width="1.5" />
            </span>
          </button>
        </section>
      </div>
    </div>

    <div v-else-if="effectiveView() === 'table'" ref="feedRef" class="feed scroll">
      <div class="feed-inner view-table" :style="{ '--rowgrid': rowGrid() }">
        <div class="tl-cols">
          <span></span>
          <button
            v-for="column in visibleColumns()"
            :key="column.key"
            type="button"
            class="tl-col-head th-sort"
            :class="{ 'is-sorted': levelForField(column.key) }"
            @click.stop="applyHeaderSort(column.key)"
          >
            <span>{{ column.label }}</span>
            <TimelineLucideIcon
              v-if="levelForField(column.key)"
              class="th-caret"
              :name="levelForField(column.key).dir < 0 ? 'chevronDown' : 'chevronUp'"
              :stroke-width="2"
            />
          </button>
          <span v-if="hasTrailingSpacer()" aria-hidden="true"></span>
          <span></span>
        </div>

        <button
          v-for="event in sortedFlatEvents()"
          :key="event.id"
          :ref="(element) => setRowRef(event.id, element)"
          type="button"
          class="row"
          :class="{
            active: !selectMode && event.id === props.selectedEventId,
            selected: selectMode && isRowSelected(event.id),
          }"
          @click="onRowClick(event.id)"
        >
          <span v-if="selectMode" class="tcheck" :class="{ on: isRowSelected(event.id) }">
            <TimelineLucideIcon v-if="isRowSelected(event.id)" name="check" :stroke-width="2.4" />
          </span>
          <span v-else aria-hidden="true"></span>
          <template v-for="column in visibleColumns()" :key="column.key">
            <span v-if="column.key === 'time'" class="c-time" :title="eventColumnValue(event, column)"><HighlightedText :text="eventColumnValue(event, column)" :query="props.searchQuery" /></span>
            <span v-else-if="column.key === 'title'" class="c-title">
              <b class="ev-name" :title="eventColumnValue(event, column)"><HighlightedText :text="eventColumnValue(event, column)" :query="props.searchQuery" /></b>
              <span v-if="event.noteType === 'mindmap'" class="ev-type" title="思维导图">
                <TimelineLucideIcon name="mindmap" :stroke-width="1.5" />
              </span>
              <span v-if="event.attachments?.length || event.attachmentCount" class="clip">
                <TimelineLucideIcon name="paperclip" :stroke-width="1.5" />
              </span>
            </span>
            <span v-else-if="isOptionColumn(column)" class="c-tags">
              <span
                v-for="chip in resolvePropertyChips(event, column).slice(0, FEED_CHIP_LIMIT)"
                :key="chip.value"
                class="td"
                :style="{ '--dot': chip.color }"
              >
                <i></i><HighlightedText :text="chip.label" :query="props.searchQuery" />
              </span>
              <span
                v-if="resolvePropertyChips(event, column).length > FEED_CHIP_LIMIT"
                class="td-more"
                :title="resolvePropertyChips(event, column).slice(FEED_CHIP_LIMIT).map((chip) => chip.label).join('、')"
                >+{{ resolvePropertyChips(event, column).length - FEED_CHIP_LIMIT }}</span
              >
              <span v-if="!resolvePropertyChips(event, column).length" class="c-source c-empty">—</span>
            </span>
            <span v-else-if="column.type === 'checkbox'" class="c-source c-check">
              <TimelineLucideIcon
                v-if="isCheckboxChecked(event.extra?.[column.key])"
                name="check"
                :stroke-width="2.2"
              />
              <span v-else class="c-empty">—</span>
            </span>
            <span
              v-else
              class="c-source"
              :class="{ 'c-empty': eventColumnValue(event, column) === '—' }"
              :title="eventColumnValue(event, column) === '—' ? null : eventColumnValue(event, column)"
            ><HighlightedText :text="eventColumnValue(event, column)" :query="props.searchQuery" /></span>
          </template>
          <span v-if="hasTrailingSpacer()" class="c-spacer" aria-hidden="true"></span>
          <span
            v-if="!selectMode"
            class="row-act"
            :title="props.trashView ? '永久删除' : '移入回收站'"
            @click.stop="deleteRow(event)"
          >
            <TimelineLucideIcon name="trash" :stroke-width="1.5" />
          </span>
          <span class="c-star" :class="{ on: event.favorite }" @click.stop="emit('toggle-favorite', event)">
            <TimelineLucideIcon name="star" :stroke-width="1.5" />
          </span>
        </button>
      </div>
    </div>

    <div v-else-if="effectiveView() === 'board'" ref="feedRef" class="feed scroll feed-x">
      <div class="feed-inner view-board">
        <section v-for="bucket in boardGroups()" :key="bucket.id" class="bd-col">
          <header class="bd-col-head">
            <span class="bd-dot" :style="{ '--dot': bucket.color }"></span>
            <b class="bd-col-name">{{ bucket.label }}</b>
            <span class="bd-col-count">{{ bucket.items.length }}</span>
          </header>
          <div class="bd-col-body">
            <button
              v-for="event in bucket.items"
              :key="`${bucket.id}:${event.id}`"
              :ref="(element) => setRowRef(event.id, element)"
              type="button"
              class="bd-card"
              :class="{
                active: !selectMode && event.id === props.selectedEventId,
                selected: selectMode && isRowSelected(event.id),
              }"
              @click="onRowClick(event.id)"
            >
              <b class="bd-card-name"><HighlightedText :text="eventColumnValue(event, { key: 'title' })" :query="props.searchQuery" /></b>
              <span class="bd-card-sum"><HighlightedText :text="buildEventPreview(event, 70)" :query="props.searchQuery" /></span>
              <span class="bd-card-foot">
                <span class="bd-card-date">{{ eventColumnValue(event, { key: 'time' }) }}</span>
                <span class="c-star" :class="{ on: event.favorite }" @click.stop="emit('toggle-favorite', event)">
                  <TimelineLucideIcon name="star" :stroke-width="1.5" />
                </span>
              </span>
            </button>
            <p v-if="!bucket.items.length" class="bd-col-empty">空</p>
          </div>
        </section>
      </div>
    </div>

    <div v-else-if="effectiveView() === 'gallery'" ref="feedRef" class="feed scroll">
      <div class="feed-inner view-gallery">
        <button
          v-for="event in galleryEvents()"
          :key="event.id"
          :ref="(element) => setRowRef(event.id, element)"
          type="button"
          class="gl-card"
          :class="{
            active: !selectMode && event.id === props.selectedEventId,
            selected: selectMode && isRowSelected(event.id),
          }"
          @click="onRowClick(event.id)"
        >
          <span class="gl-thumb" :class="{ 'is-empty': !eventThumb(event) }">
            <img
              v-if="eventThumb(event)"
              :src="eventThumb(event)"
              :alt="eventColumnValue(event, { key: 'title' })"
              loading="lazy"
              decoding="async"
              fetchpriority="low"
            />
            <TimelineLucideIcon v-else name="image" :stroke-width="1.6" />
            <span v-if="selectMode" class="gl-check tcheck" :class="{ on: isRowSelected(event.id) }">
              <TimelineLucideIcon v-if="isRowSelected(event.id)" name="check" :stroke-width="2.4" />
            </span>
            <span v-else-if="event.noteType === 'mindmap'" class="gl-badge" title="思维导图">
              <TimelineLucideIcon name="mindmap" :stroke-width="1.5" />
            </span>
          </span>
          <span class="gl-meta">
            <b class="gl-name"><HighlightedText :text="eventColumnValue(event, { key: 'title' })" :query="props.searchQuery" /></b>
            <span v-if="rowChips(event).length" class="gl-tags c-tags">
              <span
                v-for="chip in rowChips(event).slice(0, FEED_CHIP_LIMIT)"
                :key="chip.value"
                class="td"
                :style="{ '--dot': chip.color }"
              >
                <i></i><HighlightedText :text="chip.label" :query="props.searchQuery" />
              </span>
              <span
                v-if="rowChips(event).length > FEED_CHIP_LIMIT"
                class="td-more"
                :title="rowChips(event).slice(FEED_CHIP_LIMIT).map((chip) => chip.label).join('、')"
                >+{{ rowChips(event).length - FEED_CHIP_LIMIT }}</span
              >
            </span>
            <span class="gl-date">{{ eventColumnValue(event, { key: 'time' }) }}</span>
          </span>
          <span
            v-if="!selectMode"
            class="gl-del"
            :title="props.trashView ? '永久删除' : '移入回收站'"
            @click.stop="deleteRow(event)"
          >
            <TimelineLucideIcon name="trash" :stroke-width="1.5" />
          </span>
          <span class="c-star" :class="{ on: event.favorite }" @click.stop="emit('toggle-favorite', event)">
            <TimelineLucideIcon name="star" :stroke-width="1.5" />
          </span>
        </button>
      </div>
    </div>

    <div v-else-if="effectiveView() === 'outline'" ref="feedRef" class="feed scroll">
      <div class="feed-inner view-outline">
        <section v-for="group in props.groups" :key="group.key" class="ol-group">
          <button
            type="button"
            class="ol-head"
            :class="{ collapsed: isGroupCollapsed(group.key) }"
            @click="toggleGroup(group.key)"
          >
            <TimelineLucideIcon class="ol-caret" :name="isGroupCollapsed(group.key) ? 'chevronRight' : 'chevronDown'" :stroke-width="2" />
            <b class="ol-title"><HighlightedText :text="group.title" :query="props.searchQuery" /></b>
            <span class="ol-sub">{{ group.subtitle }}</span>
          </button>
          <div v-if="!isGroupCollapsed(group.key)" class="ol-body">
            <button
              v-for="event in group.items"
              :key="event.id"
              :ref="(element) => setRowRef(event.id, element)"
              type="button"
              class="ol-row"
              :class="{
                active: !selectMode && event.id === props.selectedEventId,
                selected: selectMode && isRowSelected(event.id),
              }"
              @click="onRowClick(event.id)"
            >
              <span class="ol-bullet" aria-hidden="true"></span>
              <b class="ol-name"><HighlightedText :text="eventColumnValue(event, { key: 'title' })" :query="props.searchQuery" /></b>
              <span class="ol-date">{{ eventColumnValue(event, { key: 'time' }) }}</span>
              <span class="c-star" :class="{ on: event.favorite }" @click.stop="emit('toggle-favorite', event)">
                <TimelineLucideIcon name="star" :stroke-width="1.5" />
              </span>
            </button>
          </div>
        </section>
      </div>
    </div>

    <div v-else ref="feedRef" class="feed scroll">
      <div class="feed-inner view-list">
        <button
          v-for="event in sortedFlatEvents()"
          :key="event.id"
          :ref="(element) => setRowRef(event.id, element)"
          type="button"
          class="lv-row"
          :class="{
            active: !selectMode && event.id === props.selectedEventId,
            selected: selectMode && isRowSelected(event.id),
          }"
          @click="onRowClick(event.id)"
        >
          <span v-if="selectMode" class="tcheck" :class="{ on: isRowSelected(event.id) }">
            <TimelineLucideIcon v-if="isRowSelected(event.id)" name="check" :stroke-width="2.4" />
          </span>
          <span class="lv-lead">
            <b class="lv-name" :title="eventColumnValue(event, { key: 'title' })"><HighlightedText :text="eventColumnValue(event, { key: 'title' })" :query="props.searchQuery" /></b>
            <span v-if="event.noteType === 'mindmap'" class="ev-type" title="思维导图">
              <TimelineLucideIcon name="mindmap" :stroke-width="1.5" />
            </span>
            <span v-if="event.attachments?.length || event.attachmentCount" class="clip">
              <TimelineLucideIcon name="paperclip" :stroke-width="1.5" />
            </span>
            <NotebookChip v-if="props.showSource" :topic-id="event.topicId" :topics="props.topics" />
          </span>
          <span class="lv-sum"><HighlightedText :text="buildEventPreview(event, 80)" :query="props.searchQuery" /></span>
          <span v-if="rowChips(event).length" class="lv-tags c-tags">
            <span
              v-for="chip in rowChips(event).slice(0, FEED_CHIP_LIMIT)"
              :key="chip.value"
              class="td"
              :style="{ '--dot': chip.color }"
            >
              <i></i><HighlightedText :text="chip.label" :query="props.searchQuery" />
            </span>
            <span
              v-if="rowChips(event).length > FEED_CHIP_LIMIT"
              class="td-more"
              :title="rowChips(event).slice(FEED_CHIP_LIMIT).map((chip) => chip.label).join('、')"
              >+{{ rowChips(event).length - FEED_CHIP_LIMIT }}</span
            >
          </span>
          <span class="lv-date">{{ eventColumnValue(event, { key: 'time' }) }}</span>
          <span
            v-if="!selectMode"
            class="lv-del"
            :title="props.trashView ? '永久删除' : '移入回收站'"
            @click.stop="deleteRow(event)"
          >
            <TimelineLucideIcon name="trash" :stroke-width="1.5" />
          </span>
          <span class="c-star" :class="{ on: event.favorite }" @click.stop="emit('toggle-favorite', event)">
            <TimelineLucideIcon name="star" :stroke-width="1.5" />
          </span>
        </button>
      </div>
    </div>
  </section>
</template>
