<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import ColumnConfigPopover from "@/components/timeline-notes/ColumnConfigPopover.vue";
import TimelineLucideIcon from "@/components/timeline-notes/TimelineLucideIcon.vue";
import {
  buildEventPreview,
  buildTimelineGridTemplate,
  buildVisibleTimelineColumns,
  collectEventTags,
  dateKeyFromLocator,
  eventColumnValue,
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
  activeFilter: {
    type: String,
    default: "all",
  },
  builtinColumns: {
    type: Object,
    default: () => ({ type: true, tags: true }),
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
});

const emit = defineEmits([
  "create-event",
  "select-event",
  "update:searchQuery",
  "locate-date",
  "toggle-favorite",
  "update:filter",
  "toggle-preview",
  "save-columns",
  "toggle-builtin",
]);

const locatorOpen = ref(false);
const locatorValue = ref("");
const searchOpen = ref(false);
const filterOpen = ref(false);
const columnOpen = ref(false);
const searchInputRef = ref(null);
const feedRef = ref(null);
const rowRefs = new Map();

const FILTER_OPTIONS = [
  { id: "all", label: "全部笔记" },
  { id: "today", label: "今天" },
  { id: "week", label: "本周" },
  { id: "favorite", label: "收藏" },
  { id: "trash", label: "回收站" },
];

function visibleColumns() {
  return buildVisibleTimelineColumns(props.columns, props.builtinColumns);
}

function rowGrid() {
  return buildTimelineGridTemplate(props.columns, props.builtinColumns);
}

function setRowRef(id, element) {
  if (element) {
    rowRefs.set(id, element);
  } else {
    rowRefs.delete(id);
  }
}

function openSearch() {
  searchOpen.value = true;
  nextTick(() => searchInputRef.value?.focus());
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
  locatorOpen.value = false;
  emit("locate-date", value);
  focusDate(value);
}

function closePopovers(event) {
  if (!(event.target instanceof Element)) return;
  if (!event.target.closest(".tl-toolbar-group")) {
    filterOpen.value = false;
    columnOpen.value = false;
    locatorOpen.value = false;
  }
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
});

onBeforeUnmount(() => {
  document.removeEventListener("click", closePopovers);
});
</script>

<template>
  <section class="col timeline" :class="{ 'preview-off': !props.showPreview }">
    <div class="tl-bar">
      <div>
        <h2>历史事件</h2>
        <span class="tl-count">时间线 · 共 {{ props.eventCount }} 条</span>
      </div>
      <span class="spacer"></span>

      <label v-if="searchOpen" class="searchbox open" id="searchbox">
        <TimelineLucideIcon name="search" :stroke-width="1.8" />
        <input
          ref="searchInputRef"
          :value="props.searchQuery"
          type="search"
          placeholder="搜索当前时间线"
          @input="emit('update:searchQuery', $event.target.value)"
          @blur="closeSearchIfEmpty"
        />
      </label>
      <button v-else id="searchBtn" type="button" class="iconbtn lg" title="搜索" @click="openSearch">
        <TimelineLucideIcon name="search" :stroke-width="1.8" />
      </button>

      <div class="tl-toolbar-group">
        <button type="button" class="iconbtn lg" title="时间定位" @click.stop="locatorOpen = !locatorOpen">
          <TimelineLucideIcon name="calendarSearch" :stroke-width="1.8" />
        </button>
        <form v-if="locatorOpen" class="popover filter-pop" @submit.prevent="submitLocator">
          <div class="pop-title">时间定位</div>
          <label class="pop-field">
            <span>输入日期</span>
            <input v-model="locatorValue" type="text" placeholder="1840 / 1840-06 / 1840-06-01" />
          </label>
          <button type="submit" class="pop-submit">
            <TimelineLucideIcon name="check" :stroke-width="1.8" />
          </button>
        </form>
      </div>

      <div class="tl-toolbar-group">
        <button type="button" class="iconbtn lg" title="筛选" @click.stop="filterOpen = !filterOpen">
          <TimelineLucideIcon name="filter" :stroke-width="1.8" />
        </button>
        <div v-if="filterOpen" class="popover filter-pop">
          <div class="pop-title">主筛选</div>
          <button
            v-for="option in FILTER_OPTIONS"
            :key="option.id"
            type="button"
            class="pop-item"
            :class="{ on: option.id === props.activeFilter }"
            @click="emit('update:filter', option.id)"
          >
            <span class="pop-check">
              <TimelineLucideIcon name="check" :stroke-width="1.8" />
            </span>
            <span class="lbl">{{ option.label }}</span>
          </button>
        </div>
      </div>

      <div class="tl-toolbar-group">
        <button id="colBtn" type="button" class="iconbtn lg" title="列设置" @click.stop="columnOpen = !columnOpen">
          <TimelineLucideIcon name="columns" :stroke-width="1.8" />
        </button>
        <div v-if="columnOpen" class="popover col-pop-wrap">
          <ColumnConfigPopover
            :builtin-state="props.builtinColumns"
            :columns="props.columns"
            :saving="props.columnSaving"
            @save-columns="emit('save-columns', $event)"
            @toggle-builtin="emit('toggle-builtin', $event)"
          />
        </div>
      </div>

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

      <button type="button" class="iconbtn lg primary" title="新建时间点" @click="emit('create-event')">
        <TimelineLucideIcon name="plusCircle" :stroke-width="1.8" />
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
            :class="{ active: event.id === props.selectedEventId }"
            @click="emit('select-event', event.id)"
          >
            <span class="rdot"></span>
            <template v-for="column in visibleColumns()" :key="column.key">
              <span v-if="column.key === 'time'" class="c-time">{{ eventColumnValue(event, column) }}</span>
              <span v-else-if="column.key === 'title'" class="c-title">
                <b class="ev-name">{{ eventColumnValue(event, column) }}</b>
                <span v-if="event.attachments?.length" class="clip">
                  <TimelineLucideIcon name="paperclip" :stroke-width="1.8" />
                </span>
                <span class="ev-sum">{{ buildEventPreview(event, 90) }}</span>
              </span>
              <span v-else-if="column.key === 'type'" class="c-type">{{ eventColumnValue(event, column) }}</span>
              <span v-else-if="column.key === 'tags'" class="c-tags">
                <span v-for="tag in collectEventTags(event).slice(0, 2)" :key="tag.value" class="td" :style="{ '--dot': tag.color }">
                  <i></i>{{ tag.label }}
                </span>
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
