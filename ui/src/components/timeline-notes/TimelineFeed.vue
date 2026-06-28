<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import ColumnConfigPopover from "@/components/timeline-notes/ColumnConfigPopover.vue";
import HighlightedText from "@/components/timeline-notes/HighlightedText.vue";
import NotebookChip from "@/components/timeline-notes/NotebookChip.vue";
import TimelineLucideIcon from "@/components/timeline-notes/TimelineLucideIcon.vue";
import {
  buildEventPreview,
  buildTimelineGridTemplate,
  buildVisibleTimelineColumns,
  dateKeyFromLocator,
  eventColumnValue,
  isCheckboxChecked,
  isOptionColumn,
  resolvePropertyChips,
  timelineTimeColumnWidth,
} from "@/utils/timelineNotes";

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
  "select-event",
  "update:searchQuery",
  "locate-date",
  "toggle-favorite",
  "toggle-preview",
  "save-columns",
  "batch-favorite",
  "batch-trash",
  "batch-restore",
  "batch-permanent-delete",
  "open-command-palette",
]);

// Single mutually-exclusive popover layer for the toolbar (spec §2.1).
// '' | 'locator' | 'columns' — only one may be open at a time.
const activePopover = ref("");
const locatorValue = ref("");
const searchOpen = ref(false);
const searchInputRef = ref(null);
const feedRef = ref(null);
const rowRefs = new Map();

// Note-level batch multi-select: a toolbar toggle reveals row checkboxes; row
// clicks then toggle selection instead of opening the detail pane. Batch actions
// reuse the existing per-event state-patch endpoints (favorite/soft-delete/
// restore/permanent), so no full-payload reconstruction is needed.
const selectMode = ref(false);
const selectedIds = ref([]);

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
  activePopover.value = activePopover.value === name ? "" : name;
}

function visibleColumns() {
  const columns = buildVisibleTimelineColumns(props.columns, props.emptyColumnKeys);
  if (!props.mobile) return columns;
  return columns.filter((column) => column.key === "time" || column.key === "title");
}

function rowGrid() {
  if (props.mobile) return "28px 86px minmax(0, 1fr) 58px";
  const events = props.groups.flatMap((group) => group.items);
  return buildTimelineGridTemplate(props.columns, props.emptyColumnKeys, timelineTimeColumnWidth(events));
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
  // The single popover layer lives inside .tl-bar; any click outside it closes.
  if (!event.target.closest(".tl-bar")) {
    activePopover.value = "";
  }
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
  document.addEventListener("click", closePopovers);
  document.addEventListener("keydown", handleDocumentKeydown);
});

onBeforeUnmount(() => {
  document.removeEventListener("click", closePopovers);
  document.removeEventListener("keydown", handleDocumentKeydown);
});
</script>

<template>
  <section class="col timeline" :class="{ 'preview-off': !props.showPreview, 'source-on': props.showSource }">
    <div class="tl-bar">
      <div class="tl-head">
        <h2>{{ props.topicTitle || "历史事件" }}</h2>
        <span class="tl-count">· 共 {{ props.eventCount }} 条</span>
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
            <TimelineLucideIcon name="search" :stroke-width="1.8" />
          </button>
        </div>

        <button
          type="button"
          class="iconbtn lg"
          :class="{ on: activePopover === 'locator' }"
          title="时间定位"
          @click.stop="togglePopover('locator')"
        >
          <TimelineLucideIcon name="calendarSearch" :stroke-width="1.8" />
        </button>

        <button
          v-if="props.showColumnControls"
          id="colBtn"
          type="button"
          class="iconbtn lg"
          :class="{ on: activePopover === 'columns' }"
          title="列设置"
          @click.stop="togglePopover('columns')"
        >
          <TimelineLucideIcon name="columns" :stroke-width="1.8" />
        </button>

        <button
          id="previewBtn"
          type="button"
          class="iconbtn lg"
          :class="{ on: props.showPreview }"
          title="显示预览"
          @click="emit('toggle-preview')"
        >
          <TimelineLucideIcon name="alignLeft" :stroke-width="1.8" />
        </button>

        <button
          type="button"
          class="iconbtn lg"
          :class="{ on: selectMode }"
          :title="selectMode ? '退出多选' : '多选'"
          @click.stop="toggleSelectMode"
        >
          <TimelineLucideIcon name="listChecks" :stroke-width="1.8" />
        </button>
      </div>

      <span class="tl-divider" aria-hidden="true"></span>

      <button type="button" class="iconbtn lg primary" title="新建时间点" @click="emit('create-event')">
        <TimelineLucideIcon name="plusCircle" :stroke-width="1.8" />
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
              <TimelineLucideIcon name="check" :stroke-width="1.8" />
            </button>
          </div>
        </form>

        <ColumnConfigPopover
          v-else-if="activePopover === 'columns' && props.showColumnControls"
          :columns="props.columns"
          :saving="props.columnSaving"
          @save-columns="emit('save-columns', $event)"
        />
      </div>
    </div>

    <div v-if="selectMode" class="batch-bar">
      <span class="batch-cnt">已选 {{ selectedIds.length }} 条</span>
      <template v-if="props.trashView">
        <button type="button" class="iconbtn sm" :disabled="!selectedIds.length" title="批量恢复" @click="submitBatch('batch-restore')">
          <TimelineLucideIcon name="restore" :stroke-width="1.8" />
        </button>
        <button type="button" class="iconbtn sm" :disabled="!selectedIds.length" title="批量永久删除" @click="submitBatch('batch-permanent-delete')">
          <TimelineLucideIcon name="trash" :stroke-width="1.8" />
        </button>
      </template>
      <template v-else>
        <button v-if="!props.globalFavoritesMode" type="button" class="iconbtn sm" :disabled="!selectedIds.length" title="批量收藏" @click="submitBatch('batch-favorite')">
          <TimelineLucideIcon name="star" :stroke-width="1.8" />
        </button>
        <button type="button" class="iconbtn sm" :disabled="!selectedIds.length" title="批量移入回收站" @click="submitBatch('batch-trash')">
          <TimelineLucideIcon name="trash" :stroke-width="1.8" />
        </button>
      </template>
      <button type="button" class="iconbtn sm" title="退出多选" @click="toggleSelectMode">
        <TimelineLucideIcon name="close" :stroke-width="1.8" />
      </button>
    </div>

    <div v-if="props.loading" class="feed-empty">正在加载时间线...</div>
    <div v-else-if="props.error" class="feed-empty">{{ props.error }}</div>
    <div v-else-if="!props.groups.length" class="feed-empty">{{ props.emptyReason }}</div>
    <div v-else ref="feedRef" class="feed scroll">
      <div class="feed-inner" :style="{ '--rowgrid': rowGrid() }">
        <div class="tl-cols" id="tlCols">
          <span></span>
          <span v-for="column in visibleColumns()" :key="column.key">{{ column.label }}</span>
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
                <span v-if="event.attachments?.length || event.attachmentCount" class="clip">
                  <TimelineLucideIcon name="paperclip" :stroke-width="1.8" />
                </span>
                <NotebookChip v-if="props.showSource" :topic-id="event.topicId" :topics="props.topics" />
                <span class="ev-sum"><HighlightedText :text="buildEventPreview(event, 90)" :query="props.searchQuery" /></span>
              </span>
              <span v-else-if="isOptionColumn(column)" class="c-tags">
                <span
                  v-for="chip in resolvePropertyChips(event, column).slice(0, 2)"
                  :key="chip.value"
                  class="td"
                  :style="{ '--dot': chip.color }"
                >
                  <i></i><HighlightedText :text="chip.label" :query="props.searchQuery" />
                </span>
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
            <span
              v-if="!selectMode"
              class="row-act"
              :title="props.trashView ? '永久删除' : '移入回收站'"
              @click.stop="deleteRow(event)"
            >
              <TimelineLucideIcon name="trash" :stroke-width="1.8" />
            </span>
            <span
              class="c-star"
              :class="{ on: event.favorite }"
              @click.stop="emit('toggle-favorite', event)"
            >
              <TimelineLucideIcon name="star" :stroke-width="1.8" />
            </span>
          </button>
        </section>
      </div>
    </div>
  </section>
</template>
