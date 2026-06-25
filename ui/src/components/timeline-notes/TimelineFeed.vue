<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import ColumnConfigPopover from "@/components/timeline-notes/ColumnConfigPopover.vue";
import TimelineLucideIcon from "@/components/timeline-notes/TimelineLucideIcon.vue";
import {
  buildEventPreview,
  buildTimelineGridTemplate,
  buildVisibleTimelineColumns,
  dateKeyFromLocator,
  eventColumnValue,
  isOptionColumn,
  resolvePropertyChips,
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
  columnSaving: {
    type: Boolean,
    default: false,
  },
  showPreview: {
    type: Boolean,
    default: true,
  },
  searchRequestKey: {
    type: Number,
    default: 0,
  },
  trashView: {
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
  activePopover.value = activePopover.value === name ? "" : name;
}

function visibleColumns() {
  return buildVisibleTimelineColumns(props.columns);
}

function rowGrid() {
  return buildTimelineGridTemplate(props.columns);
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

function handleEscape(event) {
  if (event.key !== "Escape") return;
  activePopover.value = "";
  closeSearchIfEmpty();
}

watch(
  () => props.searchRequestKey,
  () => openSearch()
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
  document.addEventListener("keydown", handleEscape);
});

onBeforeUnmount(() => {
  document.removeEventListener("click", closePopovers);
  document.removeEventListener("keydown", handleEscape);
});
</script>

<template>
  <section class="col timeline" :class="{ 'preview-off': !props.showPreview }">
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
            placeholder="搜索当前时间线"
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
          v-else-if="activePopover === 'columns'"
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
        <button type="button" class="iconbtn sm" :disabled="!selectedIds.length" title="批量收藏" @click="submitBatch('batch-favorite')">
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
              <b>{{ group.title }}</b>
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
              <span v-if="column.key === 'time'" class="c-time">{{ eventColumnValue(event, column) }}</span>
              <span v-else-if="column.key === 'title'" class="c-title">
                <b class="ev-name">{{ eventColumnValue(event, column) }}</b>
                <span v-if="event.attachments?.length" class="clip">
                  <TimelineLucideIcon name="paperclip" :stroke-width="1.8" />
                </span>
                <span class="ev-sum">{{ buildEventPreview(event, 90) }}</span>
              </span>
              <span v-else-if="isOptionColumn(column)" class="c-tags">
                <span
                  v-for="chip in resolvePropertyChips(event, column).slice(0, 2)"
                  :key="chip.value"
                  class="td"
                  :style="{ '--dot': chip.color }"
                >
                  <i></i>{{ chip.label }}
                </span>
                <span v-if="!resolvePropertyChips(event, column).length" class="c-source c-empty">—</span>
              </span>
              <span
                v-else
                class="c-source"
                :class="{ 'c-empty': eventColumnValue(event, column) === '—' }"
              >
                {{ eventColumnValue(event, column) }}
              </span>
            </template>
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
