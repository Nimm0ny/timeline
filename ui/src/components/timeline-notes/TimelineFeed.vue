<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from "vue";
import TimelineEventCard from "@/components/timeline-notes/TimelineEventCard.vue";
import TimelineLucideIcon from "@/components/timeline-notes/TimelineLucideIcon.vue";
import {
  buildTimelineCardLayouts,
  buildTimelineOffsetIndex,
  waitForTimelineFonts,
} from "@/services/pretextLayout";
import { dateKeyFromLocator } from "@/utils/timelineNotes";

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
});

const emit = defineEmits([
  "create-event",
  "select-event",
  "update:searchQuery",
  "locate-date",
  "toggle-favorite",
  "open-menu",
]);

const locatorOpen = ref(false);
const locatorValue = ref("");
const searchOpen = ref(false);
const searchInputRef = ref(null);
const localSearchQuery = ref("");
const focusedEventId = ref(null);
const panelRef = ref(null);
const scrollRef = ref(null);
const layoutMap = shallowRef(new Map());
const cardRefs = new Map();
let layoutRequestId = 0;
let resizeObserver = null;

const flatEvents = computed(() => props.groups.flatMap((group) => group.items));
const searchExpanded = computed(() => searchOpen.value || String(localSearchQuery.value || "").trim().length > 0);
const offsetIndex = computed(() => buildTimelineOffsetIndex(props.groups, layoutMap.value));

function readTimelineNumberVar(name, fallback) {
  if (typeof window === "undefined") return fallback;
  const source = panelRef.value?.closest(".timeline-workspace") || panelRef.value || document.documentElement;
  const value = Number.parseFloat(window.getComputedStyle(source).getPropertyValue(name));
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function currentCardLayoutOptions() {
  return {
    cardWidth: readTimelineNumberVar("--tn-card-width", 531),
    textWidth: readTimelineNumberVar("--tn-card-text-width", 480),
    titleWidth: readTimelineNumberVar("--tn-card-title-width", 390),
  };
}

async function refreshCardLayouts() {
  const requestId = ++layoutRequestId;
  await waitForTimelineFonts();
  if (requestId !== layoutRequestId) return;
  layoutMap.value = buildTimelineCardLayouts(flatEvents.value, currentCardLayoutOptions());
}

function setCardRef(id, element) {
  if (element) {
    cardRefs.set(id, element);
  } else {
    cardRefs.delete(id);
  }
}

function onSearchInput(event) {
  localSearchQuery.value = event.target.value;
  emit("update:searchQuery", localSearchQuery.value);
  if (!localSearchQuery.value.trim()) {
    searchOpen.value = false;
  }
}

async function openSearch() {
  searchOpen.value = true;
  await nextTick();
  searchInputRef.value?.focus();
}

function closeSearchIfEmpty(event) {
  const nextValue = event?.currentTarget?.value ?? localSearchQuery.value;
  if (!String(nextValue || "").trim()) {
    searchOpen.value = false;
  }
}

function onSearchKeydown(event) {
  if (event.key === "Escape" && !String(event.currentTarget.value || "").trim()) {
    searchOpen.value = false;
    event.currentTarget.blur();
  }
}

function findEventForDate(value) {
  const targetKey = dateKeyFromLocator(value);
  if (targetKey === null || flatEvents.value.length === 0) return null;
  return flatEvents.value.find((event) => event.dateKey >= targetKey) || flatEvents.value[flatEvents.value.length - 1];
}

function scrollToEstimatedEvent(eventId) {
  const container = scrollRef.value;
  const entry = offsetIndex.value.find((item) => item.eventId === eventId);
  if (!container || !entry) return;
  const viewportHeight = container.clientHeight || 0;
  container.scrollTop = Math.max(0, entry.estimatedTop - viewportHeight / 2 + entry.estimatedHeight / 2);
}

async function focusDate(value) {
  const target = findEventForDate(value);
  if (!target) return;
  focusedEventId.value = target.id;
  emit("select-event", target.id);
  scrollToEstimatedEvent(target.id);
  await nextTick();
  const element = cardRefs.get(target.id);
  if (element) {
    element.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}

function submitLocator() {
  const value = locatorValue.value.trim();
  if (!value || dateKeyFromLocator(value) === null) return;
  locatorOpen.value = false;
  emit("locate-date", value);
  focusDate(value);
}

watch(
  () => props.searchQuery,
  (value) => {
    localSearchQuery.value = value || "";
  },
  { immediate: true }
);

watch(flatEvents, refreshCardLayouts, { immediate: true });

watch(
  () => props.locateDate,
  (value) => {
    if (value) {
      locatorValue.value = value;
      focusDate(value);
    }
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
  window.addEventListener("resize", refreshCardLayouts, { passive: true });
  if (typeof ResizeObserver !== "undefined" && panelRef.value) {
    resizeObserver = new ResizeObserver(refreshCardLayouts);
    resizeObserver.observe(panelRef.value);
  }
  refreshCardLayouts();
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", refreshCardLayouts);
  resizeObserver?.disconnect();
  resizeObserver = null;
  layoutRequestId += 1;
});
</script>

<template>
  <section ref="panelRef" class="timeline-main-panel">
    <header class="timeline-main-head">
      <button
        v-if="!searchExpanded"
        type="button"
        class="timeline-search-trigger"
        aria-label="展开搜索"
        @click="openSearch"
      >
        <TimelineLucideIcon name="search" :stroke-width="1.8" />
      </button>
      <label v-else class="timeline-search">
        <TimelineLucideIcon name="search" :stroke-width="1.8" />
        <input
          ref="searchInputRef"
          :value="localSearchQuery"
          type="search"
          placeholder="搜索笔记"
          @input="onSearchInput"
          @blur="closeSearchIfEmpty"
          @keydown="onSearchKeydown"
        />
      </label>
      <div class="timeline-date-locator">
        <button type="button" class="timeline-date-button" aria-label="时间筛选" @click="locatorOpen = !locatorOpen">
          <TimelineLucideIcon name="calendar" :stroke-width="1.7" />
          <TimelineLucideIcon name="chevronDown" :stroke-width="1.8" />
        </button>
        <form v-if="locatorOpen" class="timeline-date-popover" @submit.prevent="submitLocator">
          <label>
            <span>定位到</span>
            <input v-model="locatorValue" type="text" placeholder="1840 / 1840-06 / 1840-06-01" />
          </label>
          <button type="submit" class="timeline-primary-btn">定位</button>
        </form>
      </div>
    </header>

    <div v-if="props.loading" class="timeline-empty-state">正在加载时间线...</div>

    <div v-else-if="props.error" class="timeline-error-state">
      <h3>加载失败</h3>
      <p>{{ props.error }}</p>
    </div>

    <div v-else-if="props.groups.length === 0" class="timeline-empty-state">
      {{ props.emptyReason }}
    </div>

    <div v-else ref="scrollRef" class="timeline-feed-scroll">
      <div class="timeline-feed-shell">
        <section
          v-for="group in props.groups"
          :key="group.key"
          class="timeline-year-group"
        >
          <div class="timeline-year-label">
            <strong>{{ group.title }}</strong>
            <span v-if="group.subtitle">{{ group.subtitle }}</span>
          </div>

          <div class="timeline-year-rail" aria-hidden="true">
            <span class="timeline-year-dot"></span>
          </div>

          <div class="timeline-card-stack">
            <TimelineEventCard
              v-for="event in group.items"
              :key="event.id"
              :ref="(element) => setCardRef(event.id, element?.$el || element)"
              :event="event"
              :layout="layoutMap.get(event.id)"
              :active="event.id === props.selectedEventId || event.id === focusedEventId"
              @select="emit('select-event', event.id)"
              @toggle-favorite="emit('toggle-favorite', $event)"
              @open-menu="emit('open-menu', $event)"
            />
          </div>
        </section>
      </div>
    </div>

    <div class="timeline-quick-composer" :class="{ disabled: !props.hasTopic }">
      <button
        type="button"
        class="timeline-composer-add"
        :disabled="!props.hasTopic"
        aria-label="快速记录"
        @click="emit('create-event')"
      >
        <TimelineLucideIcon name="plus" :stroke-width="1.8" />
      </button>
      <button
        type="button"
        class="timeline-composer-input"
        :disabled="!props.hasTopic"
        @click="emit('create-event')"
      >
        记录一个想法、事件或里程碑...
      </button>
      <div class="timeline-composer-tools" aria-label="快速记录工具">
        <button
          type="button"
          class="timeline-composer-tool"
          :disabled="!props.hasTopic"
          aria-label="选择时间"
          @click="emit('create-event')"
        >
          <TimelineLucideIcon name="calendar" :stroke-width="1.7" />
        </button>
        <button
          type="button"
          class="timeline-composer-tool"
          :disabled="!props.hasTopic"
          aria-label="添加图片"
          @click="emit('create-event')"
        >
          <TimelineLucideIcon name="image" :stroke-width="1.7" />
        </button>
        <button
          type="button"
          class="timeline-composer-tool"
          :disabled="!props.hasTopic"
          aria-label="标记里程碑"
          @click="emit('create-event')"
        >
          <TimelineLucideIcon name="flag" :stroke-width="1.7" />
        </button>
      </div>
      <button
        type="button"
        class="timeline-composer-send"
        :disabled="!props.hasTopic"
        aria-label="创建"
        @click="emit('create-event')"
      >
        <TimelineLucideIcon name="send" :stroke-width="1.8" />
      </button>
    </div>
  </section>
</template>
