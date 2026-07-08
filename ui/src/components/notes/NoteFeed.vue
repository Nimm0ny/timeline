<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import ColumnConfigPopover from "@/components/notes/ColumnConfigPopover.vue";
import HighlightedText from "@/components/notes/HighlightedText.vue";
import NotebookChip from "@/components/notes/NotebookChip.vue";
import LucideIcon from "@/components/notes/LucideIcon.vue";
import {
  chunkGalleryRows,
  FEED_BOARD_COLUMN_OVERSCAN,
  FEED_GALLERY_DESKTOP_OVERSCAN,
  FEED_GALLERY_MOBILE_OVERSCAN,
  FEED_GROUP_DESKTOP_HEIGHT,
  FEED_GROUP_MOBILE_HEIGHT,
  FEED_LINEAR_DESKTOP_OVERSCAN,
  FEED_LINEAR_DESKTOP_ROW_HEIGHT,
  FEED_LINEAR_MOBILE_OVERSCAN,
  FEED_LINEAR_MOBILE_ROW_HEIGHT,
  FEED_LOAD_MORE_REMAINING,
  sliceVirtualWindow,
  useFeedVirtualRows,
} from "@/composables/useFeedVirtualRows";
import {
  aggregateOptionChips,
  availableDisplayViews,
  buildBoardGroups,
  buildNotePreview,
  buildTimelineGridTemplate,
  buildVisibleTimelineColumns,
  clampTimelineColumnWidth,
  compareNotesBySort,
  dateKeyFromLocator,
  DISPLAY_VIEW_META,
  noteColumnValue,
  noteHasDate,
  isCheckboxChecked,
  isDefaultSort,
  isOptionColumn,
  pickBoardColumn,
  reorderSortLevels,
  resolveDisplayStyle,
  resolvePropertyChips,
  SORT_FIELD_META,
  sortFieldsForView,
  shouldRequestMoreOnScroll,
  timelineHasTrailingSpacer,
  timelineTimeColumnWidth,
} from "@/utils/noteUtils";

// Center feed caps option chips per cell; any extras collapse into a muted "+N"
// so a multi-value event never silently hides tags. Single source for the cap so
// the slice and the overflow count can't drift.
const FEED_CHIP_LIMIT = 2;
const LINEAR_VIEWS = new Set(["timeline", "table", "list", "outline"]);
const BOARD_CARD_ESTIMATE = 119;
const GALLERY_CARD_MIN_WIDTH = 196;
const GALLERY_GRID_GAP = 14;
const GALLERY_ROW_META_HEIGHT = 96;

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
  noteCount: {
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
  allNotes: {
    type: Array,
    default: () => [],
  },
  selectedNoteId: {
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
  hasMore: {
    type: Boolean,
    default: false,
  },
  loadingMore: {
    type: Boolean,
    default: false,
  },
  canRetryLoadMore: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits([
  "create-note",
  "create-mindmap",
  "create-canvas",
  "select-note",
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
  "load-more",
  "pane-drag-start",
]);

// Single mutually-exclusive popover layer for the toolbar (spec §2.1).
// '' | 'locator' | 'columns' | 'views' | 'sort' | 'newtype' — only one open at a time.
const activePopover = ref("");
const locatorValue = ref("");
const searchOpen = ref(false);
const searchInputRef = ref(null);
const feedRef = ref(null);
const rowRefs = new Map();
const galleryMetrics = ref({ itemsPerRow: 1, rowHeight: 243 });
const boardViewport = ref({ scrollTop: 0, clientHeight: 0 });
const boardCardHeights = ref({});
const widthOverrides = ref({});
// 时间 / 事件 are built-in (not in the persisted column set), so their user widths
// live in localStorage keyed per notebook — no data-contract change. Custom column
// widths still persist to the backend via the existing resize-column path.
const builtinWidths = ref({});
const COLUMN_WIDTH_STORAGE_PREFIX = "tl-colw:";
const BUILTIN_WIDTH_BOUNDS = { time: [64, 240], title: [180, 760] };
let stopColumnResize = null;
let feedResizeObserver = null;

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
  else emit("select-note", id);
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
// mindmap / canvas create + open their own center surface. The page owns the handlers.
function pickNoteType(type) {
  activePopover.value = "";
  emit(type === "mindmap" ? "create-mindmap" : type === "canvas" ? "create-canvas" : "create-note");
}

function flatNotes() {
  return props.groups.flatMap((group) => group.items);
}

function isLinearView(view) {
  return LINEAR_VIEWS.has(view);
}

function buildProjectedNote(event, columns, { previewLength = 0 } = {}) {
  const resolvedColumnValues = {};
  const chipsByColumn = {};
  for (const column of columns || []) {
    resolvedColumnValues[column.key] = noteColumnValue(event, column);
    if (isOptionColumn(column)) chipsByColumn[column.key] = resolvePropertyChips(event, column);
  }
  return {
    key: `event:${event.id}`,
    event,
    titleText: resolvedColumnValues.title || noteColumnValue(event, { key: "title" }),
    timeText: resolvedColumnValues.time || noteColumnValue(event, { key: "time" }),
    previewText: previewLength > 0 ? buildNotePreview(event, previewLength) : "",
    resolvedColumnValues,
    chipsByColumn,
    rowChips: aggregateOptionChips(event, props.columns, props.emptyColumnKeys),
    hasAttachment: Boolean(event.attachments?.length || event.attachmentCount),
    isMindmap: event.noteType === "mindmap",
    isCanvas: event.noteType === "canvas",
    thumbUrl: eventThumb(event),
  };
}

function buildTimelineRows(groups, columns) {
  return (groups || []).flatMap((group) => [
    {
      kind: "group-header",
      key: `group:${group.key}`,
      groupKey: group.key,
      title: group.title,
      subtitle: group.subtitle,
    },
    ...((group.items || []).map((event, index, items) => ({
      kind: "event-row",
      key: `event:${event.id}`,
      groupKey: group.key,
      isFirstInGroup: index === 0,
      isLastInGroup: index === items.length - 1,
      projected: buildProjectedNote(event, columns, { previewLength: 90 }),
    })) || []),
  ]);
}

function buildOutlineRows(groups) {
  return (groups || []).flatMap((group) => {
    const rows = [
      {
        kind: "group-header",
        key: `outline:${group.key}`,
        groupKey: group.key,
        title: group.title,
        subtitle: group.subtitle,
        collapsed: isGroupCollapsed(group.key),
      },
    ];
    if (!isGroupCollapsed(group.key)) {
      rows.push(
        ...((group.items || []).map((event) => ({
          kind: "event-row",
          key: `event:${event.id}`,
          groupKey: group.key,
          projected: buildProjectedNote(event, [], {}),
        })) || [])
      );
    }
    return rows;
  });
}

function galleryItemsPerRow(width) {
  const available = Math.max(GALLERY_CARD_MIN_WIDTH, Math.floor(width || 0) - 52);
  return Math.max(1, Math.floor((available + GALLERY_GRID_GAP) / (GALLERY_CARD_MIN_WIDTH + GALLERY_GRID_GAP)));
}

function galleryRowHeight(width, itemsPerRow) {
  const available = Math.max(GALLERY_CARD_MIN_WIDTH, Math.floor(width || 0) - 52);
  const columns = Math.max(1, Number.parseInt(itemsPerRow, 10) || 1);
  const cardWidth = (available - GALLERY_GRID_GAP * (columns - 1)) / columns;
  return Math.round(cardWidth * 0.75 + GALLERY_ROW_META_HEIGHT + GALLERY_GRID_GAP);
}

function updateGalleryMetrics() {
  if (!feedRef.value) return;
  const itemsPerRow = galleryItemsPerRow(feedRef.value.clientWidth);
  galleryMetrics.value = {
    itemsPerRow,
    rowHeight: galleryRowHeight(feedRef.value.clientWidth, itemsPerRow),
  };
}

function updateBoardViewport(target = feedRef.value) {
  if (!target) return;
  boardViewport.value = {
    scrollTop: Math.max(0, target.scrollTop || 0),
    clientHeight: Math.max(0, target.clientHeight || 0),
  };
}

function recordBoardCardHeight(bucketId, element) {
  if (!bucketId || !element) return;
  const measured = Math.round((element.getBoundingClientRect().height || 0) + 7);
  if (!measured || measured === boardCardHeights.value[bucketId]) return;
  boardCardHeights.value = { ...boardCardHeights.value, [bucketId]: measured };
}

// Sort control (docs/center-sort-design.md). The page owns the ordered sort levels
// and clamps them per view; here we surface options and emit changes. Flat views
// (table/list/gallery) re-sort the flattened set directly, bypassing the era
// grouping; grouped views read props.groups (already ordered by the page).
const GROUP_BY_OPTIONS = [
  { key: "era", label: "分组", icon: "outline" },
  { key: "year", label: "年", icon: "calendar" },
  { key: "month", label: "月", icon: "calendar" },
];

const sortedFlatNotes = computed(() => [...flatNotes()].sort(compareNotesBySort(props.sort, props.columns)));

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

const boardGroups = computed(() =>
  buildBoardGroups(flatNotes(), boardColumn(), props.sort).map((bucket) => ({
    ...bucket,
    projectedItems: bucket.items.map((event) => buildProjectedNote(event, [], { previewLength: 70 })),
  }))
);
const boardNoteIndexById = computed(() => {
  const map = new Map();
  for (const bucket of boardGroups.value) {
    bucket.projectedItems.forEach((projected, index) => {
      map.set(projected.event.id, { bucketId: bucket.id, index });
    });
  }
  return map;
});

function boardEstimateSize(bucketId) {
  return boardCardHeights.value[bucketId] || BOARD_CARD_ESTIMATE;
}

function boardWindow(bucket) {
  const window = sliceVirtualWindow({
    count: bucket?.projectedItems?.length || 0,
    scrollTop: boardViewport.value.scrollTop,
    viewportHeight: boardViewport.value.clientHeight,
    estimateSize: boardEstimateSize(bucket?.id),
    overscan: FEED_BOARD_COLUMN_OVERSCAN,
  });
  return {
    ...window,
    visibleItems: (bucket?.projectedItems || []).slice(window.startIndex, window.endIndex + 1),
  };
}

const boardRenderedBuckets = computed(() =>
  boardGroups.value.map((bucket) => ({
    ...bucket,
    window: boardWindow(bucket),
  }))
);

// Gallery view: every entry as a card, ordered by the active sort; the primary
// image (thumb preferred) rides the index DTO, empty for imageless entries (which
// render a placeholder).
const galleryNotes = computed(() => sortedFlatNotes.value.map((event) => buildProjectedNote(event, [], {})));

function eventThumb(event) {
  return event?.thumbUrl || event?.imageUrl || "";
}

// List/gallery cards surface the same option chips as the timeline, aggregated
// across the visible (non-empty) option columns and capped by FEED_CHIP_LIMIT with
// a +N overflow (see aggregateOptionChips) so a card never invents or hides tags.
function rowChips(event) {
  return event?.rowChips || aggregateOptionChips(event, props.columns, props.emptyColumnKeys);
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

const visibleColumnsComputed = computed(() => {
  const columns = buildVisibleTimelineColumns(columnsWithWidthOverrides(), props.emptyColumnKeys, effectiveTimeWidth(), effectiveTitleWidth());
  if (!props.mobile) return columns;
  return columns.filter((column) => column.key === "time" || column.key === "title");
});

function visibleColumns() {
  return visibleColumnsComputed.value;
}

const rowGridComputed = computed(() => {
  if (props.mobile) return "28px 86px minmax(0, 1fr) 58px";
  return buildTimelineGridTemplate(columnsWithWidthOverrides(), props.emptyColumnKeys, effectiveTimeWidth(), effectiveTitleWidth());
});

function rowGrid() {
  return rowGridComputed.value;
}

const timelineRows = computed(() => buildTimelineRows(props.groups, visibleColumnsComputed.value));
const tableRows = computed(() => sortedFlatNotes.value.map((event) => buildProjectedNote(event, visibleColumnsComputed.value, {})));
const listRows = computed(() => sortedFlatNotes.value.map((event) => buildProjectedNote(event, [], { previewLength: 80 })));
const outlineRows = computed(() => buildOutlineRows(props.groups));

const activeLinearRows = computed(() => {
  switch (effectiveView()) {
    case "timeline":
      return timelineRows.value;
    case "table":
      return tableRows.value.map((projected) => ({ kind: "event-row", key: projected.key, projected }));
    case "list":
      return listRows.value.map((projected) => ({ kind: "event-row", key: projected.key, projected }));
    case "outline":
      return outlineRows.value;
    default:
      return [];
  }
});

const activeLinearIndexByNoteId = computed(() => {
  const map = new Map();
  activeLinearRows.value.forEach((item, index) => {
    if (item.kind === "event-row") map.set(item.projected.event.id, index);
  });
  return map;
});

const linearVirtual = useFeedVirtualRows({
  items: activeLinearRows,
  estimateSize(index, item) {
    if (item?.kind === "group-header") return props.mobile ? FEED_GROUP_MOBILE_HEIGHT : FEED_GROUP_DESKTOP_HEIGHT;
    return props.mobile ? FEED_LINEAR_MOBILE_ROW_HEIGHT : FEED_LINEAR_DESKTOP_ROW_HEIGHT;
  },
  overscan: computed(() => (props.mobile ? FEED_LINEAR_MOBILE_OVERSCAN : FEED_LINEAR_DESKTOP_OVERSCAN)),
  scrollElement: feedRef,
  hasMore: computed(() => props.hasMore),
  loading: computed(() => props.loading),
  loadingMore: computed(() => props.loadingMore),
  globalFavoritesMode: computed(() => props.globalFavoritesMode),
  error: computed(() => props.error),
  threshold: FEED_LOAD_MORE_REMAINING,
  getItemKey(item, index) {
    return item?.key ?? index;
  },
});
const linearVirtualItems = linearVirtual.virtualItems;
const linearTopSpacerPx = linearVirtual.topSpacerPx;
const linearBottomSpacerPx = linearVirtual.bottomSpacerPx;

const galleryRows = computed(() => chunkGalleryRows(galleryNotes.value, galleryMetrics.value.itemsPerRow));
const galleryIndexByNoteId = computed(() => {
  const map = new Map();
  galleryRows.value.forEach((row, rowIndex) => {
    for (const projected of row.items) map.set(projected.event.id, rowIndex);
  });
  return map;
});

const galleryVirtual = useFeedVirtualRows({
  items: galleryRows,
  estimateSize() {
    return galleryMetrics.value.rowHeight;
  },
  overscan: computed(() => (props.mobile ? FEED_GALLERY_MOBILE_OVERSCAN : FEED_GALLERY_DESKTOP_OVERSCAN)),
  scrollElement: feedRef,
  hasMore: computed(() => props.hasMore),
  loading: computed(() => props.loading),
  loadingMore: computed(() => props.loadingMore),
  globalFavoritesMode: computed(() => props.globalFavoritesMode),
  error: computed(() => props.error),
  threshold: FEED_LOAD_MORE_REMAINING,
  getItemKey(item, index) {
    return item?.key ?? index;
  },
});
const galleryVirtualItems = galleryVirtual.virtualItems;
const galleryTopSpacerPx = galleryVirtual.topSpacerPx;
const galleryBottomSpacerPx = galleryVirtual.bottomSpacerPx;

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
// Pane-swap drag entry point: only the toolbar's own empty area (the bar itself or
// its flex spacer) starts a drag — a whitelist so buttons/search/popovers are never
// hijacked, and any button added later is safe by default (pane-swap-drag-design.md §4).
// NotesPage owns the state machine; this only reports the press.
function onBarPointerDown(event) {
  const target = event.target;
  if (target !== event.currentTarget && !target.classList?.contains("spacer")) return;
  if (event.button !== 0 || event.pointerType !== "mouse") return;
  event.preventDefault(); // suppress text selection / focus jitter on the bar
  emit("pane-drag-start", {
    pane: "feed",
    x: event.clientX,
    y: event.clientY,
    pointerType: event.pointerType,
    button: event.button,
  });
}

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

function maybeRequestMore(target = feedRef.value, { auto = true } = {}) {
  if (!target) return;
  const view = effectiveView();
  const requestMore = isLinearView(view)
    ? linearVirtual.maybeRequestMore()
    : view === "gallery"
      ? galleryVirtual.maybeRequestMore()
      : shouldRequestMoreOnScroll({
          scrollHeight: target.scrollHeight,
          scrollTop: target.scrollTop,
          clientHeight: target.clientHeight,
          hasMore: props.hasMore,
          loadingMore: props.loadingMore,
          globalFavoritesMode: props.globalFavoritesMode,
          loading: props.loading,
          error: props.error,
        });
  if (requestMore) emit("load-more", { auto });
}

function onFeedScroll(event) {
  if (effectiveView() === "board") updateBoardViewport(event?.target);
  maybeRequestMore(event?.target, { auto: false });
}

function currentScrollTop() {
  return Math.max(0, Number(feedRef.value?.scrollTop) || 0);
}

function rememberFeedScroll() {
  const view = effectiveView();
  if (isLinearView(view)) return linearVirtual.rememberScroll();
  if (view === "gallery") return galleryVirtual.rememberScroll();
  return currentScrollTop();
}

async function restoreFeedScroll(value) {
  const view = effectiveView();
  if (isLinearView(view)) return linearVirtual.restoreScroll(value);
  if (view === "gallery") return galleryVirtual.restoreScroll(value);
  await nextTick();
  if (feedRef.value) feedRef.value.scrollTop = Math.max(0, Number(value) || 0);
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
  emit("select-note", target.id);
  nextTick(() => {
    const view = effectiveView();
    if (isLinearView(view)) {
      const index = activeLinearIndexByNoteId.value.get(target.id);
      if (Number.isInteger(index)) {
        linearVirtual.scrollToIndex(index, "center");
        return;
      }
    } else if (view === "gallery") {
      const index = galleryIndexByNoteId.value.get(target.id);
      if (Number.isInteger(index)) {
        galleryVirtual.scrollToIndex(index, "center");
        return;
      }
    }
    rowRefs.get(target.id)?.scrollIntoView({ behavior: "smooth", block: "center" });
  });
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
  () => props.selectedNoteId,
  (eventId) => {
    if (!eventId) return;
    nextTick(() => {
      const view = effectiveView();
      if (isLinearView(view)) {
        const index = activeLinearIndexByNoteId.value.get(eventId);
        if (Number.isInteger(index)) {
          linearVirtual.scrollToIndex(index, view === "timeline" || view === "outline" ? "center" : "auto");
          return;
        }
      } else if (view === "gallery") {
        const index = galleryIndexByNoteId.value.get(eventId);
        if (Number.isInteger(index)) {
          galleryVirtual.scrollToIndex(index, "center");
          return;
        }
      } else if (view === "board") {
        const match = boardNoteIndexById.value.get(eventId);
        if (match && feedRef.value) {
          const cardHeight = boardEstimateSize(match.bucketId);
          feedRef.value.scrollTop = Math.max(0, match.index * cardHeight - Math.floor(feedRef.value.clientHeight / 3));
          updateBoardViewport(feedRef.value);
          return;
        }
      }
      rowRefs.get(eventId)?.scrollIntoView({ block: "nearest" });
    });
  }
);

watch(
  () => props.groups,
  () => {
    if (props.locateDate) {
      nextTick(() => focusDate(props.locateDate));
    }
    nextTick(() => maybeRequestMore(feedRef.value, { auto: true }));
  },
  { deep: true }
);

watch(
  () => [props.hasMore, props.loadingMore, props.loading],
  () => {
    nextTick(() => maybeRequestMore(feedRef.value, { auto: true }));
  }
);

watch(
  () => effectiveView(),
  () => {
    nextTick(() => {
      feedResizeObserver?.disconnect();
      if (feedRef.value && feedResizeObserver) feedResizeObserver.observe(feedRef.value);
      updateGalleryMetrics();
      updateBoardViewport();
    });
  }
);

onMounted(() => {
  document.addEventListener("pointerdown", closePopovers);
  document.addEventListener("keydown", handleDocumentKeydown);
  if (typeof ResizeObserver !== "undefined") {
    feedResizeObserver = new ResizeObserver(() => {
      updateGalleryMetrics();
      updateBoardViewport();
    });
    if (feedRef.value) feedResizeObserver.observe(feedRef.value);
  }
  nextTick(() => {
    updateGalleryMetrics();
    updateBoardViewport();
  });
});

onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", closePopovers);
  document.removeEventListener("keydown", handleDocumentKeydown);
  feedResizeObserver?.disconnect();
  feedResizeObserver = null;
  stopResizingColumn();
});

defineExpose({
  currentScrollTop,
  rememberScroll: rememberFeedScroll,
  restoreScroll: restoreFeedScroll,
});
</script>

<template>
  <section class="col timeline" :class="{ 'preview-off': !props.showPreview, 'source-on': props.showSource }">
    <div class="tl-bar" @pointerdown="onBarPointerDown">
      <div class="tl-head">
        <h2>{{ props.topicTitle || "历史事件" }}</h2>
        <span class="tl-count">· 共 {{ props.noteCount }} 条</span>
        <span v-if="props.filterContextLabel" class="tl-context">
          <span class="tl-context-label">{{ props.filterContextLabel }}</span>
          <button
            v-if="props.filterContextClearable"
            type="button"
            class="iconbtn sm tl-context-clear"
            title="清空当前筛选"
            @click.stop="emit('clear-context-filter')"
          >
            <LucideIcon name="close" :stroke-width="1.5" />
          </button>
        </span>
      </div>
      <span class="spacer"></span>

      <div class="tl-actions">
        <!-- 查找组：搜索 + 时间定位 -->
        <div class="tl-group" role="group" aria-label="查找">
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
              <LucideIcon name="search" :stroke-width="1.5" />
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
            <LucideIcon name="calendarSearch" :stroke-width="1.5" />
          </button>
        </div>

        <!-- 视图组：视图切换 + 排序 + 列设置 + 显示预览（决定「怎么看」） -->
        <div class="tl-group" role="group" aria-label="视图">
          <button
            v-if="props.showViewSwitcher"
            type="button"
            class="iconbtn lg"
            data-popover-anchor="views"
            :class="{ on: activePopover === 'views' }"
            title="切换视图"
            @click.stop="togglePopover('views')"
          >
            <LucideIcon :name="currentViewIcon()" :stroke-width="1.5" />
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
            <LucideIcon name="arrowUpDown" :stroke-width="1.5" />
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
            <LucideIcon name="columns" :stroke-width="1.5" />
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
            <LucideIcon name="alignLeft" :stroke-width="1.5" />
          </button>
        </div>

        <!-- 选择组：多选（批量操作入口） -->
        <div class="tl-group" role="group" aria-label="选择">
          <button
            type="button"
            class="iconbtn lg"
            :class="{ on: selectMode }"
            :title="selectMode ? '退出多选' : '多选'"
            @click.stop="toggleSelectMode"
          >
            <LucideIcon name="listChecks" :stroke-width="1.5" />
          </button>
        </div>
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
        <LucideIcon name="plusCircle" :stroke-width="1.5" />
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
              <LucideIcon name="check" :stroke-width="1.5" />
            </button>
          </div>
        </form>

        <ColumnConfigPopover
          v-else-if="activePopover === 'columns' && props.showColumnControls"
          :key="props.topicId"
          :topic-id="props.topicId"
          :columns="props.columns"
          :events="props.allNotes"
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
            <LucideIcon class="pop-item-ic" :name="view.icon" :stroke-width="1.5" />
            <span class="pop-item-label">{{ view.label }}</span>
            <LucideIcon v-if="view.key === effectiveView()" class="pop-item-check" name="check" :stroke-width="2" />
          </button>
        </template>

        <template v-else-if="activePopover === 'sort'">
          <template v-if="effectiveView() === 'timeline' || effectiveView() === 'outline'">
            <div class="pop-title">分组依据</div>
            <button
              v-for="opt in GROUP_BY_OPTIONS"
              :key="opt.key"
              type="button"
              class="pop-item"
              :class="{ 'is-active': props.groupBy === opt.key }"
              @click="pickGroupBy(opt.key)"
            >
              <LucideIcon class="pop-item-ic" :name="opt.icon" :stroke-width="1.5" />
              <span class="pop-item-label">{{ opt.label }}</span>
              <LucideIcon v-if="props.groupBy === opt.key" class="pop-item-check" name="check" :stroke-width="2" />
            </button>
            <div class="pop-subtitle">方向</div>
            <button type="button" class="pop-item" :class="{ 'is-active': primaryLevel().dir >= 0 }" @click="applySortDir(1)">
              <LucideIcon class="pop-item-ic" name="chevronUp" :stroke-width="1.5" />
              <span class="pop-item-label">时间正序</span>
              <LucideIcon v-if="primaryLevel().dir >= 0" class="pop-item-check" name="check" :stroke-width="2" />
            </button>
            <button type="button" class="pop-item" :class="{ 'is-active': primaryLevel().dir < 0 }" @click="applySortDir(-1)">
              <LucideIcon class="pop-item-ic" name="chevronDown" :stroke-width="1.5" />
              <span class="pop-item-label">时间倒序</span>
              <LucideIcon v-if="primaryLevel().dir < 0" class="pop-item-check" name="check" :stroke-width="2" />
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
                <LucideIcon name="grip" :stroke-width="1.5" />
              </span>
              <button
                type="button"
                class="pop-sort-flip"
                :title="`点按切换「${sortLabel(level.field)}」升/降序`"
                @click="flipSortLevel(i)"
              >
                <LucideIcon class="pop-item-ic" :name="sortIcon(level.field)" :stroke-width="1.5" />
                <span class="pop-item-label">{{ sortLabel(level.field) }}</span>
                <LucideIcon class="pop-item-check" :name="level.dir < 0 ? 'chevronDown' : 'chevronUp'" :stroke-width="2" />
              </button>
              <span v-if="props.sort.length > 1" class="pop-sort-del" title="移除该排序层" @click.stop="removeSortLevel(i)">
                <LucideIcon name="close" :stroke-width="1.6" />
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
                <LucideIcon class="pop-item-ic" :name="field.icon" :stroke-width="1.5" />
                <span class="pop-item-label">{{ field.label }}</span>
                <LucideIcon class="pop-item-add-ic" name="plusSign" :stroke-width="1.8" />
              </button>
            </template>
          </template>
        </template>

        <template v-else-if="activePopover === 'newtype'">
          <div class="pop-title">新建</div>
          <button type="button" class="pop-item" @click="pickNoteType('entry')">
            <LucideIcon class="pop-item-ic" name="note" :stroke-width="1.5" />
            <span class="pop-item-label">条目</span>
          </button>
          <button type="button" class="pop-item" @click="pickNoteType('mindmap')">
            <LucideIcon class="pop-item-ic" name="mindmap" :stroke-width="1.5" />
            <span class="pop-item-label">思维导图</span>
          </button>
          <button type="button" class="pop-item" @click="pickNoteType('canvas')">
            <LucideIcon class="pop-item-ic" name="canvas" :stroke-width="1.5" />
            <span class="pop-item-label">画布</span>
          </button>
        </template>
      </div>
    </div>

    <div v-if="selectMode" class="batch-bar">
      <span class="batch-cnt">已选 {{ selectedIds.length }} 条</span>
      <template v-if="props.trashView">
        <button type="button" class="iconbtn sm" :disabled="!selectedIds.length" title="批量恢复" @click="submitBatch('batch-restore')">
          <LucideIcon name="restore" :stroke-width="1.5" />
        </button>
        <button type="button" class="iconbtn sm" :disabled="!selectedIds.length" title="批量永久删除" @click="submitBatch('batch-permanent-delete')">
          <LucideIcon name="trash" :stroke-width="1.5" />
        </button>
      </template>
      <template v-else>
        <button v-if="!props.globalFavoritesMode" type="button" class="iconbtn sm" :disabled="!selectedIds.length" title="批量收藏" @click="submitBatch('batch-favorite')">
          <LucideIcon name="star" :stroke-width="1.5" />
        </button>
        <button type="button" class="iconbtn sm" :disabled="!selectedIds.length" title="批量移入回收站" @click="submitBatch('batch-trash')">
          <LucideIcon name="trash" :stroke-width="1.5" />
        </button>
      </template>
      <button type="button" class="iconbtn sm" title="退出多选" @click="toggleSelectMode">
        <LucideIcon name="close" :stroke-width="1.5" />
      </button>
    </div>

    <div v-if="props.loading" class="feed-empty">正在加载时间线...</div>
    <div v-else-if="props.error" class="feed-empty">{{ props.error }}</div>
    <div v-else-if="!props.groups.length" class="feed-empty">
      <span>{{ props.emptyReason }}</span>
      <button
        v-if="props.canRetryLoadMore"
        type="button"
        class="iconbtn sm"
        title="继续加载"
        @click="emit('load-more', { auto: false })"
      >
        <LucideIcon name="refreshCw" :stroke-width="1.5" />
      </button>
    </div>
      <div v-else-if="effectiveView() === 'timeline'" ref="feedRef" class="feed scroll" @scroll="onFeedScroll">
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
        <div v-if="linearTopSpacerPx" class="feed-virtual-spacer" :style="{ height: `${linearTopSpacerPx}px` }"></div>
        <template v-for="vRow in linearVirtualItems" :key="vRow.key">
          <div
            v-if="activeLinearRows[vRow.index]?.kind === 'group-header'"
            class="era tlv-era tlv-era-group"
          >
            <div class="era-head">
              <span class="rdot"></span>
              <div class="era-main">
                <b><HighlightedText :text="activeLinearRows[vRow.index].title" :query="props.searchQuery" /></b>
                <span>{{ activeLinearRows[vRow.index].subtitle }}</span>
              </div>
            </div>
          </div>
          <div
            v-else
            class="era tlv-era tlv-era-row"
            :class="{ 'is-last': activeLinearRows[vRow.index]?.isLastInGroup }"
          >
            <button
              :ref="(element) => setRowRef(activeLinearRows[vRow.index].projected.event.id, element)"
              type="button"
              class="row"
              :class="{
                active: !selectMode && activeLinearRows[vRow.index].projected.event.id === props.selectedNoteId,
                selected: selectMode && isRowSelected(activeLinearRows[vRow.index].projected.event.id),
              }"
              @click="onRowClick(activeLinearRows[vRow.index].projected.event.id)"
            >
              <span
                v-if="selectMode"
                class="tcheck"
                :class="{ on: isRowSelected(activeLinearRows[vRow.index].projected.event.id) }"
              >
                <LucideIcon v-if="isRowSelected(activeLinearRows[vRow.index].projected.event.id)" name="check" :stroke-width="2.4" />
              </span>
              <span v-else class="rdot"></span>
              <template v-for="column in visibleColumns()" :key="column.key">
                <span
                  v-if="column.key === 'time'"
                  class="c-time"
                  :title="activeLinearRows[vRow.index].projected.resolvedColumnValues[column.key]"
                ><HighlightedText :text="activeLinearRows[vRow.index].projected.resolvedColumnValues[column.key]" :query="props.searchQuery" /></span>
                <span v-else-if="column.key === 'title'" class="c-title">
                  <b class="ev-name" :title="activeLinearRows[vRow.index].projected.titleText"><HighlightedText :text="activeLinearRows[vRow.index].projected.titleText" :query="props.searchQuery" /></b>
                  <span v-if="activeLinearRows[vRow.index].projected.isMindmap" class="ev-type" title="思维导图">
                    <LucideIcon name="mindmap" :stroke-width="1.5" />
                  </span>
                  <span v-else-if="activeLinearRows[vRow.index].projected.isCanvas" class="ev-type" title="画布">
                    <LucideIcon name="canvas" :stroke-width="1.5" />
                  </span>
                  <span v-if="activeLinearRows[vRow.index].projected.hasAttachment" class="clip">
                    <LucideIcon name="paperclip" :stroke-width="1.5" />
                  </span>
                  <NotebookChip
                    v-if="props.showSource"
                    :topic-id="activeLinearRows[vRow.index].projected.event.topicId"
                    :topics="props.topics"
                  />
                  <span class="ev-sum"><HighlightedText :text="activeLinearRows[vRow.index].projected.previewText" :query="props.searchQuery" /></span>
                </span>
                <span v-else-if="isOptionColumn(column)" class="c-tags">
                  <span
                    v-for="chip in activeLinearRows[vRow.index].projected.chipsByColumn[column.key].slice(0, FEED_CHIP_LIMIT)"
                    :key="chip.value"
                    class="td"
                    :style="{ '--dot': chip.color }"
                  >
                    <i></i><HighlightedText :text="chip.label" :query="props.searchQuery" />
                  </span>
                  <span
                    v-if="activeLinearRows[vRow.index].projected.chipsByColumn[column.key].length > FEED_CHIP_LIMIT"
                    class="td-more"
                    :title="activeLinearRows[vRow.index].projected.chipsByColumn[column.key].slice(FEED_CHIP_LIMIT).map((chip) => chip.label).join('、')"
                    >+{{ activeLinearRows[vRow.index].projected.chipsByColumn[column.key].length - FEED_CHIP_LIMIT }}</span
                  >
                  <span v-if="!activeLinearRows[vRow.index].projected.chipsByColumn[column.key].length" class="c-source c-empty">—</span>
                </span>
                <span v-else-if="column.type === 'checkbox'" class="c-source c-check">
                  <LucideIcon
                    v-if="isCheckboxChecked(activeLinearRows[vRow.index].projected.event.extra?.[column.key])"
                    name="check"
                    :stroke-width="2.2"
                  />
                  <span v-else class="c-empty">—</span>
                </span>
                <span
                  v-else
                  class="c-source"
                  :class="{ 'c-empty': activeLinearRows[vRow.index].projected.resolvedColumnValues[column.key] === '—' }"
                  :title="activeLinearRows[vRow.index].projected.resolvedColumnValues[column.key] === '—' ? null : activeLinearRows[vRow.index].projected.resolvedColumnValues[column.key]"
                ><HighlightedText :text="activeLinearRows[vRow.index].projected.resolvedColumnValues[column.key]" :query="props.searchQuery" /></span>
              </template>
              <span v-if="hasTrailingSpacer()" class="c-spacer" aria-hidden="true"></span>
              <span
                v-if="!selectMode"
                class="row-act"
                :title="props.trashView ? '永久删除' : '移入回收站'"
                @click.stop="deleteRow(activeLinearRows[vRow.index].projected.event)"
              >
                <LucideIcon name="trash" :stroke-width="1.5" />
              </span>
              <span
                class="c-star"
                :class="{ on: activeLinearRows[vRow.index].projected.event.favorite }"
                @click.stop="emit('toggle-favorite', activeLinearRows[vRow.index].projected.event)"
              >
                <LucideIcon name="star" :stroke-width="1.5" />
              </span>
            </button>
          </div>
        </template>
        <div v-if="linearBottomSpacerPx" class="feed-virtual-spacer" :style="{ height: `${linearBottomSpacerPx}px` }"></div>
      </div>
    </div>

      <div v-else-if="effectiveView() === 'table'" ref="feedRef" class="feed scroll" @scroll="onFeedScroll">
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
            <LucideIcon
              v-if="levelForField(column.key)"
              class="th-caret"
              :name="levelForField(column.key).dir < 0 ? 'chevronDown' : 'chevronUp'"
              :stroke-width="2"
            />
          </button>
          <span v-if="hasTrailingSpacer()" aria-hidden="true"></span>
          <span></span>
        </div>
        <div v-if="linearTopSpacerPx" class="feed-virtual-spacer" :style="{ height: `${linearTopSpacerPx}px` }"></div>
        <button
          v-for="vRow in linearVirtualItems"
          :key="vRow.key"
          :ref="(element) => setRowRef(activeLinearRows[vRow.index].projected.event.id, element)"
          type="button"
          class="row"
          :class="{
            active: !selectMode && activeLinearRows[vRow.index].projected.event.id === props.selectedNoteId,
            selected: selectMode && isRowSelected(activeLinearRows[vRow.index].projected.event.id),
          }"
          @click="onRowClick(activeLinearRows[vRow.index].projected.event.id)"
        >
          <span v-if="selectMode" class="tcheck" :class="{ on: isRowSelected(activeLinearRows[vRow.index].projected.event.id) }">
            <LucideIcon v-if="isRowSelected(activeLinearRows[vRow.index].projected.event.id)" name="check" :stroke-width="2.4" />
          </span>
          <span v-else aria-hidden="true"></span>
          <template v-for="column in visibleColumns()" :key="column.key">
            <span
              v-if="column.key === 'time'"
              class="c-time"
              :title="activeLinearRows[vRow.index].projected.resolvedColumnValues[column.key]"
            ><HighlightedText :text="activeLinearRows[vRow.index].projected.resolvedColumnValues[column.key]" :query="props.searchQuery" /></span>
            <span v-else-if="column.key === 'title'" class="c-title">
              <b class="ev-name" :title="activeLinearRows[vRow.index].projected.titleText"><HighlightedText :text="activeLinearRows[vRow.index].projected.titleText" :query="props.searchQuery" /></b>
              <span v-if="activeLinearRows[vRow.index].projected.isMindmap" class="ev-type" title="思维导图">
                <LucideIcon name="mindmap" :stroke-width="1.5" />
              </span>
              <span v-else-if="activeLinearRows[vRow.index].projected.isCanvas" class="ev-type" title="画布">
                <LucideIcon name="canvas" :stroke-width="1.5" />
              </span>
              <span v-if="activeLinearRows[vRow.index].projected.hasAttachment" class="clip">
                <LucideIcon name="paperclip" :stroke-width="1.5" />
              </span>
            </span>
            <span v-else-if="isOptionColumn(column)" class="c-tags">
              <span
                v-for="chip in activeLinearRows[vRow.index].projected.chipsByColumn[column.key].slice(0, FEED_CHIP_LIMIT)"
                :key="chip.value"
                class="td"
                :style="{ '--dot': chip.color }"
              >
                <i></i><HighlightedText :text="chip.label" :query="props.searchQuery" />
              </span>
              <span
                v-if="activeLinearRows[vRow.index].projected.chipsByColumn[column.key].length > FEED_CHIP_LIMIT"
                class="td-more"
                :title="activeLinearRows[vRow.index].projected.chipsByColumn[column.key].slice(FEED_CHIP_LIMIT).map((chip) => chip.label).join('、')"
                >+{{ activeLinearRows[vRow.index].projected.chipsByColumn[column.key].length - FEED_CHIP_LIMIT }}</span
              >
              <span v-if="!activeLinearRows[vRow.index].projected.chipsByColumn[column.key].length" class="c-source c-empty">—</span>
            </span>
            <span v-else-if="column.type === 'checkbox'" class="c-source c-check">
              <LucideIcon
                v-if="isCheckboxChecked(activeLinearRows[vRow.index].projected.event.extra?.[column.key])"
                name="check"
                :stroke-width="2.2"
              />
              <span v-else class="c-empty">—</span>
            </span>
            <span
              v-else
              class="c-source"
              :class="{ 'c-empty': activeLinearRows[vRow.index].projected.resolvedColumnValues[column.key] === '—' }"
              :title="activeLinearRows[vRow.index].projected.resolvedColumnValues[column.key] === '—' ? null : activeLinearRows[vRow.index].projected.resolvedColumnValues[column.key]"
            ><HighlightedText :text="activeLinearRows[vRow.index].projected.resolvedColumnValues[column.key]" :query="props.searchQuery" /></span>
          </template>
          <span v-if="hasTrailingSpacer()" class="c-spacer" aria-hidden="true"></span>
          <span
            v-if="!selectMode"
            class="row-act"
            :title="props.trashView ? '永久删除' : '移入回收站'"
            @click.stop="deleteRow(activeLinearRows[vRow.index].projected.event)"
          >
            <LucideIcon name="trash" :stroke-width="1.5" />
          </span>
          <span class="c-star" :class="{ on: activeLinearRows[vRow.index].projected.event.favorite }" @click.stop="emit('toggle-favorite', activeLinearRows[vRow.index].projected.event)">
            <LucideIcon name="star" :stroke-width="1.5" />
          </span>
        </button>
        <div v-if="linearBottomSpacerPx" class="feed-virtual-spacer" :style="{ height: `${linearBottomSpacerPx}px` }"></div>
      </div>
    </div>

      <div v-else-if="effectiveView() === 'board'" ref="feedRef" class="feed scroll feed-x" @scroll="onFeedScroll">
      <div class="feed-inner view-board">
        <section v-for="bucket in boardRenderedBuckets" :key="bucket.id" class="bd-col">
          <header class="bd-col-head">
            <span class="bd-dot" :style="{ '--dot': bucket.color }"></span>
            <b class="bd-col-name">{{ bucket.label }}</b>
            <span class="bd-col-count">{{ bucket.items.length }}</span>
          </header>
          <div class="bd-col-body">
            <div v-if="bucket.window.topSpacerPx" class="feed-virtual-spacer" :style="{ height: `${bucket.window.topSpacerPx}px` }"></div>
            <button
              v-for="projected in bucket.window.visibleItems"
              :key="`${bucket.id}:${projected.event.id}`"
              :ref="(element) => { setRowRef(projected.event.id, element); recordBoardCardHeight(bucket.id, element); }"
              type="button"
              class="bd-card"
              :class="{
                active: !selectMode && projected.event.id === props.selectedNoteId,
                selected: selectMode && isRowSelected(projected.event.id),
              }"
              @click="onRowClick(projected.event.id)"
            >
              <b class="bd-card-name"><HighlightedText :text="projected.titleText" :query="props.searchQuery" /></b>
              <span class="bd-card-sum"><HighlightedText :text="projected.previewText" :query="props.searchQuery" /></span>
              <span class="bd-card-foot">
                <span class="bd-card-date">{{ noteHasDate(projected.event) ? projected.timeText : "" }}</span>
                <span class="c-star" :class="{ on: projected.event.favorite }" @click.stop="emit('toggle-favorite', projected.event)">
                  <LucideIcon name="star" :stroke-width="1.5" />
                </span>
              </span>
            </button>
            <div v-if="bucket.window.bottomSpacerPx" class="feed-virtual-spacer" :style="{ height: `${bucket.window.bottomSpacerPx}px` }"></div>
            <p v-if="!bucket.items.length" class="bd-col-empty">空</p>
          </div>
        </section>
      </div>
    </div>

      <div v-else-if="effectiveView() === 'gallery'" ref="feedRef" class="feed scroll" @scroll="onFeedScroll">
      <div class="feed-inner view-gallery" :style="{ '--gallery-cols': galleryMetrics.itemsPerRow }">
        <div v-if="galleryTopSpacerPx" class="feed-virtual-spacer" :style="{ height: `${galleryTopSpacerPx}px` }"></div>
        <div v-for="vRow in galleryVirtualItems" :key="vRow.key" class="gl-row">
          <button
            v-for="projected in galleryRows[vRow.index].items"
            :key="projected.event.id"
            :ref="(element) => setRowRef(projected.event.id, element)"
            type="button"
            class="gl-card"
            :class="{
              active: !selectMode && projected.event.id === props.selectedNoteId,
              selected: selectMode && isRowSelected(projected.event.id),
            }"
            @click="onRowClick(projected.event.id)"
          >
            <span class="gl-thumb" :class="{ 'is-empty': !projected.thumbUrl }">
              <img
                v-if="projected.thumbUrl"
                :src="projected.thumbUrl"
                :alt="projected.titleText"
                loading="lazy"
                decoding="async"
                fetchpriority="low"
              />
              <LucideIcon v-else name="image" :stroke-width="1.6" />
              <span v-if="selectMode" class="gl-check tcheck" :class="{ on: isRowSelected(projected.event.id) }">
                <LucideIcon v-if="isRowSelected(projected.event.id)" name="check" :stroke-width="2.4" />
              </span>
              <span v-else-if="projected.isMindmap" class="gl-badge" title="思维导图">
                <LucideIcon name="mindmap" :stroke-width="1.5" />
              </span>
              <span v-else-if="projected.isCanvas" class="gl-badge" title="画布">
                <LucideIcon name="canvas" :stroke-width="1.5" />
              </span>
            </span>
            <span class="gl-meta">
              <b class="gl-name"><HighlightedText :text="projected.titleText" :query="props.searchQuery" /></b>
              <span v-if="projected.rowChips.length" class="gl-tags c-tags">
                <span
                  v-for="chip in projected.rowChips.slice(0, FEED_CHIP_LIMIT)"
                  :key="chip.value"
                  class="td"
                  :style="{ '--dot': chip.color }"
                >
                  <i></i><HighlightedText :text="chip.label" :query="props.searchQuery" />
                </span>
                <span
                  v-if="projected.rowChips.length > FEED_CHIP_LIMIT"
                  class="td-more"
                  :title="projected.rowChips.slice(FEED_CHIP_LIMIT).map((chip) => chip.label).join('、')"
                  >+{{ projected.rowChips.length - FEED_CHIP_LIMIT }}</span
                >
              </span>
              <span class="gl-date">{{ noteHasDate(projected.event) ? projected.timeText : "" }}</span>
            </span>
            <span
              v-if="!selectMode"
              class="gl-del"
              :title="props.trashView ? '永久删除' : '移入回收站'"
              @click.stop="deleteRow(projected.event)"
            >
              <LucideIcon name="trash" :stroke-width="1.5" />
            </span>
            <span class="c-star" :class="{ on: projected.event.favorite }" @click.stop="emit('toggle-favorite', projected.event)">
              <LucideIcon name="star" :stroke-width="1.5" />
            </span>
          </button>
        </div>
        <div v-if="galleryBottomSpacerPx" class="feed-virtual-spacer" :style="{ height: `${galleryBottomSpacerPx}px` }"></div>
      </div>
    </div>

      <div v-else-if="effectiveView() === 'outline'" ref="feedRef" class="feed scroll" @scroll="onFeedScroll">
      <div class="feed-inner view-outline">
        <div v-if="linearTopSpacerPx" class="feed-virtual-spacer" :style="{ height: `${linearTopSpacerPx}px` }"></div>
        <template v-for="vRow in linearVirtualItems" :key="vRow.key">
          <button
            v-if="activeLinearRows[vRow.index]?.kind === 'group-header'"
            type="button"
            class="ol-head"
            :class="{ collapsed: activeLinearRows[vRow.index].collapsed }"
            @click="toggleGroup(activeLinearRows[vRow.index].groupKey)"
          >
            <LucideIcon class="ol-caret" :name="activeLinearRows[vRow.index].collapsed ? 'chevronRight' : 'chevronDown'" :stroke-width="2" />
            <b class="ol-title"><HighlightedText :text="activeLinearRows[vRow.index].title" :query="props.searchQuery" /></b>
            <span class="ol-sub">{{ activeLinearRows[vRow.index].subtitle }}</span>
          </button>
          <button
            v-else
            :ref="(element) => setRowRef(activeLinearRows[vRow.index].projected.event.id, element)"
            type="button"
            class="ol-row"
            :class="{
              active: !selectMode && activeLinearRows[vRow.index].projected.event.id === props.selectedNoteId,
              selected: selectMode && isRowSelected(activeLinearRows[vRow.index].projected.event.id),
            }"
            @click="onRowClick(activeLinearRows[vRow.index].projected.event.id)"
          >
            <span class="ol-bullet" aria-hidden="true"></span>
            <b class="ol-name"><HighlightedText :text="activeLinearRows[vRow.index].projected.titleText" :query="props.searchQuery" /></b>
            <span class="ol-date">{{ noteHasDate(activeLinearRows[vRow.index].projected.event) ? activeLinearRows[vRow.index].projected.timeText : "" }}</span>
            <span class="c-star" :class="{ on: activeLinearRows[vRow.index].projected.event.favorite }" @click.stop="emit('toggle-favorite', activeLinearRows[vRow.index].projected.event)">
              <LucideIcon name="star" :stroke-width="1.5" />
            </span>
          </button>
        </template>
        <div v-if="linearBottomSpacerPx" class="feed-virtual-spacer" :style="{ height: `${linearBottomSpacerPx}px` }"></div>
      </div>
    </div>

      <div v-else ref="feedRef" class="feed scroll" @scroll="onFeedScroll">
      <div class="feed-inner view-list">
        <div v-if="linearTopSpacerPx" class="feed-virtual-spacer" :style="{ height: `${linearTopSpacerPx}px` }"></div>
        <button
          v-for="vRow in linearVirtualItems"
          :key="vRow.key"
          :ref="(element) => setRowRef(activeLinearRows[vRow.index].projected.event.id, element)"
          type="button"
          class="lv-row"
          :class="{
            active: !selectMode && activeLinearRows[vRow.index].projected.event.id === props.selectedNoteId,
            selected: selectMode && isRowSelected(activeLinearRows[vRow.index].projected.event.id),
          }"
          @click="onRowClick(activeLinearRows[vRow.index].projected.event.id)"
        >
          <span v-if="selectMode" class="tcheck" :class="{ on: isRowSelected(activeLinearRows[vRow.index].projected.event.id) }">
            <LucideIcon v-if="isRowSelected(activeLinearRows[vRow.index].projected.event.id)" name="check" :stroke-width="2.4" />
          </span>
          <span class="lv-lead">
            <b class="lv-name" :title="activeLinearRows[vRow.index].projected.titleText"><HighlightedText :text="activeLinearRows[vRow.index].projected.titleText" :query="props.searchQuery" /></b>
            <span v-if="activeLinearRows[vRow.index].projected.isMindmap" class="ev-type" title="思维导图">
              <LucideIcon name="mindmap" :stroke-width="1.5" />
            </span>
            <span v-else-if="activeLinearRows[vRow.index].projected.isCanvas" class="ev-type" title="画布">
              <LucideIcon name="canvas" :stroke-width="1.5" />
            </span>
            <span v-if="activeLinearRows[vRow.index].projected.hasAttachment" class="clip">
              <LucideIcon name="paperclip" :stroke-width="1.5" />
            </span>
            <NotebookChip v-if="props.showSource" :topic-id="activeLinearRows[vRow.index].projected.event.topicId" :topics="props.topics" />
          </span>
          <span class="lv-sum"><HighlightedText :text="activeLinearRows[vRow.index].projected.previewText" :query="props.searchQuery" /></span>
          <span v-if="activeLinearRows[vRow.index].projected.rowChips.length" class="lv-tags c-tags">
            <span
              v-for="chip in activeLinearRows[vRow.index].projected.rowChips.slice(0, FEED_CHIP_LIMIT)"
              :key="chip.value"
              class="td"
              :style="{ '--dot': chip.color }"
            >
              <i></i><HighlightedText :text="chip.label" :query="props.searchQuery" />
            </span>
            <span
              v-if="activeLinearRows[vRow.index].projected.rowChips.length > FEED_CHIP_LIMIT"
              class="td-more"
              :title="activeLinearRows[vRow.index].projected.rowChips.slice(FEED_CHIP_LIMIT).map((chip) => chip.label).join('、')"
              >+{{ activeLinearRows[vRow.index].projected.rowChips.length - FEED_CHIP_LIMIT }}</span
            >
          </span>
          <span class="lv-date">{{ noteHasDate(activeLinearRows[vRow.index].projected.event) ? activeLinearRows[vRow.index].projected.timeText : "" }}</span>
          <span
            v-if="!selectMode"
            class="lv-del"
            :title="props.trashView ? '永久删除' : '移入回收站'"
            @click.stop="deleteRow(activeLinearRows[vRow.index].projected.event)"
          >
            <LucideIcon name="trash" :stroke-width="1.5" />
          </span>
          <span class="c-star" :class="{ on: activeLinearRows[vRow.index].projected.event.favorite }" @click.stop="emit('toggle-favorite', activeLinearRows[vRow.index].projected.event)">
            <LucideIcon name="star" :stroke-width="1.5" />
          </span>
        </button>
        <div v-if="linearBottomSpacerPx" class="feed-virtual-spacer" :style="{ height: `${linearBottomSpacerPx}px` }"></div>
      </div>
    </div>
  </section>
</template>
