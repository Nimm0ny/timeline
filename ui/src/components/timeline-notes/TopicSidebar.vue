<script setup>
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from "vue";
import { CONTENT_LIMITS } from "@/constants/contentLimits";
import TimelineLucideIcon from "@/components/timeline-notes/TimelineLucideIcon.vue";
import { buildPropertyRows } from "@/utils/timelineNotes";

const props = defineProps({
  brand: {
    type: String,
    default: "编年",
  },
  topics: {
    type: Array,
    default: () => [],
  },
  events: {
    type: Array,
    default: () => [],
  },
  activeTopicId: {
    type: Number,
    default: null,
  },
  activeFilter: {
    type: String,
    default: "all",
  },
  globalFavoriteCount: {
    type: Number,
    default: 0,
  },
  globalFavoritesActive: {
    type: Boolean,
    default: false,
  },
  columns: {
    type: Array,
    default: () => [],
  },
  propertyFilter: {
    type: Object,
    default: () => ({ key: "", value: "" }),
  },
  activeEra: {
    type: String,
    default: "",
  },
  loading: {
    type: Boolean,
    default: false,
  },
  error: {
    type: String,
    default: "",
  },
  createTopicRequestKey: {
    type: Number,
    default: 0,
  },
});

const emit = defineEmits([
  "create-event",
  "create-event-in-topic",
  "create-topic",
  "rename-topic",
  "select-topic",
  "select-era",
  "update:filter",
  "update:property-filter",
  "delete-topic",
  "batch-delete-topics",
  "focus-search",
  "open-global-favorites",
  "open-settings",
  "select-ribbon",
]);

const state = reactive({
  ribbon: "files",
  sections: {
    views: false,
    topics: false,
    properties: false,
    stats: false,
  },
  topicCollapsed: {},
});

const topicName = ref("");
const creatingTopic = ref(false);
const topicCreateRef = ref(null);
const topicInputRef = ref(null);

// Notion-style notebook creation: a clean inline row at the BOTTOM of the 笔记本
// list (where the new notebook — ordered by id asc — actually lands), opened from
// either the group-head + or the persistent "新增" row. No floating box, no ✓/✗
// buttons — a borderless field that commits on Enter/blur and cancels on Esc.
function startCreateTopic() {
  state.sections.topics = false;
  creatingTopic.value = true;
  nextTick(() => {
    topicInputRef.value?.focus();
    topicCreateRef.value?.scrollIntoView({ block: "nearest" });
  });
}

function cancelCreateTopic() {
  creatingTopic.value = false;
  topicName.value = "";
}

// Commit-on-blur (Notion): clicking away saves a named draft, discards an empty one.
function onCreateBlur() {
  if (topicName.value.trim()) {
    submitTopic();
  } else {
    cancelCreateTopic();
  }
}

// Notion-style row hover actions (§2.1 列表行悬停操作组): each notebook row reveals
// a right-edge cluster on hover/active/menu-open — ⊕ (new note here) + ⋯ (more menu:
// rename / delete). Resting count fades out beneath it; nothing reflows.
const topicMenu = ref(null); // { topic, x, y } | null
const renamingTopicId = ref(null);
const renameValue = ref("");
const renameInputRef = ref(null);

function openTopicMenu(topic, event) {
  // Anchor a fixed-position menu under the ⋯ button, clamped to the viewport so it
  // never overflows (the pane scroll-clips, so the menu lives at the overlay layer).
  const rect = event.currentTarget.getBoundingClientRect();
  const width = 152;
  const x = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));
  const y = Math.min(rect.bottom + 4, window.innerHeight - 96);
  topicMenu.value = { topic, x, y };
}

function closeTopicMenu() {
  topicMenu.value = null;
}

function onPaneScroll() {
  if (topicMenu.value) closeTopicMenu();
}

function createInTopic(topicId) {
  closeTopicMenu();
  emit("create-event-in-topic", topicId);
}

// Inline rename reuses the borderless create-row field (one list-edit grammar):
// commit on Enter/blur (when changed & non-empty), cancel on Esc.
function startRenameTopic(topic) {
  closeTopicMenu();
  renamingTopicId.value = topic.id;
  renameValue.value = topic.title || topic.name || "";
  nextTick(() => {
    renameInputRef.value?.focus();
    renameInputRef.value?.select?.();
  });
}

function cancelRenameTopic() {
  renamingTopicId.value = null;
  renameValue.value = "";
}

function submitRenameTopic() {
  const id = renamingTopicId.value;
  if (id == null) return;
  const next = renameValue.value.trim().slice(0, CONTENT_LIMITS.topicTitle);
  const topic = props.topics.find((item) => item.id === id);
  const current = (topic?.title || topic?.name || "").trim();
  renamingTopicId.value = null;
  renameValue.value = "";
  if (next && next !== current) emit("rename-topic", { id, title: next });
}

function onRenameBlur() {
  if (renamingTopicId.value != null) submitRenameTopic();
}

function deleteFromMenu(topic) {
  closeTopicMenu();
  emit("delete-topic", topic.id);
}

function onMenuKeydown(event) {
  if (event.key === "Escape") closeTopicMenu();
}

watch(topicMenu, (value) => {
  if (value) document.addEventListener("keydown", onMenuKeydown);
  else document.removeEventListener("keydown", onMenuKeydown);
});

onBeforeUnmount(() => document.removeEventListener("keydown", onMenuKeydown));

// Batch multi-select for notebooks: a pane-head toggle reveals row checkboxes;
// row clicks then toggle selection instead of navigating, and a batch bar offers
// a multi-delete (confirmed in-app by the page).
const selectMode = ref(false);
const selectedTopicIds = ref([]);

function isTopicSelected(topicId) {
  return selectedTopicIds.value.includes(topicId);
}

function toggleSelectMode() {
  selectMode.value = !selectMode.value;
  if (!selectMode.value) selectedTopicIds.value = [];
}

function toggleTopicSelection(topicId) {
  selectedTopicIds.value = isTopicSelected(topicId)
    ? selectedTopicIds.value.filter((id) => id !== topicId)
    : [...selectedTopicIds.value, topicId];
}

function submitBatchDelete() {
  if (selectedTopicIds.value.length) emit("batch-delete-topics", [...selectedTopicIds.value]);
}

// Each ribbon owns a distinct left-pane panel (Obsidian-style). The notebook
// tree, tags, and stats are no longer stacked together under one tab.
const RIBBON_PANELS = {
  files: { title: "笔记本", sections: ["views", "topics"], tree: true },
  search: { title: "搜索", sections: ["views", "topics"], tree: true },
  star: { title: "收藏", sections: ["globalFavorites"], tree: false },
  tags: { title: "属性", sections: ["properties"], tree: false },
  stats: { title: "统计", sections: ["stats"], tree: false },
};
const activePanel = computed(() => RIBBON_PANELS[state.ribbon] || RIBBON_PANELS.files);
const panelHas = (section) => activePanel.value.sections.includes(section);

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

const liveEvents = computed(() => props.events.filter((event) => !event.deletedAt));
const deletedEvents = computed(() => props.events.filter((event) => event.deletedAt));

function countForFilter(filter) {
  if (filter === "today") return liveEvents.value.filter(isToday).length;
  if (filter === "week") return liveEvents.value.filter(isThisWeek).length;
  if (filter === "favorite") return liveEvents.value.filter((event) => event.favorite).length;
  if (filter === "trash") return deletedEvents.value.length;
  return liveEvents.value.length;
}

const quickFilters = computed(() => [
  { id: "all", label: "全部笔记", count: countForFilter("all"), icon: "library" },
  { id: "today", label: "今天", count: countForFilter("today"), icon: "calendar" },
  { id: "week", label: "本周", count: countForFilter("week"), icon: "clock" },
  { id: "favorite", label: "收藏", count: countForFilter("favorite"), icon: "star" },
  { id: "trash", label: "回收站", count: countForFilter("trash"), icon: "archive" },
]);

const eraRows = computed(() => {
  const counts = new Map();
  for (const event of liveEvents.value) {
    const key = String(event?.era || "未分期").trim() || "未分期";
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return [...counts.entries()]
    .map(([era, count]) => ({ era, count }))
    .sort((left, right) => right.count - left.count || left.era.localeCompare(right.era));
});

// Properties (and their option counts) for the left "属性" tab. Counts run over
// all live events so the list never blanks out under an active view filter.
const propertyRows = computed(() => buildPropertyRows(props.columns, liveEvents.value));

const PROPERTY_TYPE_LABELS = { text: "文本", number: "数字", date: "日期", select: "单选", multiselect: "多选" };
function propTypeLabel(type) {
  return PROPERTY_TYPE_LABELS[type] || "文本";
}

function isOptionActive(key, value) {
  return props.propertyFilter?.key === key && props.propertyFilter?.value === value;
}

function togglePropertyFilter(key, value) {
  emit("update:property-filter", isOptionActive(key, value) ? { key: "", value: "" } : { key, value });
}

const stats = computed(() => ({
  notes: liveEvents.value.length,
  week: liveEvents.value.filter(isThisWeek).length,
  favorite: liveEvents.value.filter((event) => event.favorite).length,
}));
const globalFavoritesCopy = computed(() => (props.globalFavoriteCount ? `共 ${props.globalFavoriteCount} 条收藏。` : "暂无收藏。"));

// Lightweight "new notes per week" trend (last 8 weeks) as CSS bars — no deps,
// no chart library; oldest week left, current week right.
const weeklyTrend = computed(() => {
  const weeks = 8;
  const buckets = Array.from({ length: weeks }, () => 0);
  const startOfWeek = (date) => {
    const value = new Date(date);
    const day = (value.getDay() + 6) % 7;
    value.setDate(value.getDate() - day);
    value.setHours(0, 0, 0, 0);
    return value;
  };
  const currentStart = startOfWeek(new Date());
  const weekMs = 7 * 24 * 3600 * 1000;
  for (const event of liveEvents.value) {
    const date = eventCreatedDate(event);
    if (!date) continue;
    const diff = Math.round((currentStart - startOfWeek(date)) / weekMs);
    if (diff >= 0 && diff < weeks) buckets[weeks - 1 - diff] += 1;
  }
  const max = Math.max(1, ...buckets);
  return buckets.map((count) => ({ count, pct: count ? Math.max(8, Math.round((count / max) * 100)) : 0 }));
});

function toggleSection(key) {
  state.sections[key] = !state.sections[key];
}

function isTopicExpanded(topicId) {
  return !selectMode.value && topicId === props.activeTopicId && state.topicCollapsed[topicId] !== true;
}

function toggleTopic(topicId) {
  if (selectMode.value) {
    toggleTopicSelection(topicId);
    return;
  }
  if (topicId === props.activeTopicId) {
    state.topicCollapsed[topicId] = isTopicExpanded(topicId);
  } else {
    state.topicCollapsed[topicId] = false;
    allCollapsed.value = false;
  }
  emit("select-topic", topicId);
}

function selectRibbon(ribbon) {
  state.ribbon = ribbon;
  emit("select-ribbon", ribbon);
}

function focusSearch() {
  selectRibbon("search");
  emit("focus-search");
}

function openGlobalFavorites() {
  emit("open-global-favorites");
}

function submitTopic() {
  const nextName = topicName.value
    .trim()
    .slice(0, CONTENT_LIMITS.topicTitle)
    .replace(/[^\w\-\u4e00-\u9fff]/g, "");
  if (!nextName) return;
  emit("create-topic", nextName);
  topicName.value = "";
  creatingTopic.value = false;
}

const allCollapsed = ref(false);

// One button toggles the whole active panel between fully collapsed and fully
// expanded (sections + notebook nodes), with the icon/label following suit.
function toggleCollapseAll() {
  const collapse = !allCollapsed.value;
  for (const key of activePanel.value.sections) {
    state.sections[key] = collapse;
  }
  for (const topic of props.topics) {
    state.topicCollapsed[topic.id] = collapse;
  }
  allCollapsed.value = collapse;
}

// Drop any selected ids whose notebook no longer exists (e.g. after a batch
// delete reloads the list), keeping the selection consistent.
watch(
  () => props.topics,
  (topics) => {
    const ids = new Set((topics || []).map((topic) => topic.id));
    selectedTopicIds.value = selectedTopicIds.value.filter((id) => ids.has(id));
  },
  { deep: true }
);

// Leaving the notebook tree (switching ribbons) exits multi-select so a hidden
// selection never lingers across panels.
watch(
  () => state.ribbon,
  () => {
    if (selectMode.value) {
      selectMode.value = false;
      selectedTopicIds.value = [];
    }
  }
);

watch(
  () => props.globalFavoritesActive,
  (active) => {
    if (active) state.ribbon = "star";
    else if (state.ribbon === "star") state.ribbon = "files";
  }
);

watch(
  () => props.createTopicRequestKey,
  (key, previous) => {
    if (!key || key === previous) return;
    state.ribbon = "files";
    startCreateTopic();
  }
);

watch(
  () => props.activeTopicId,
  (topicId, previous) => {
    if (topicId && topicId !== previous) {
      state.topicCollapsed[topicId] = false;
      allCollapsed.value = false;
    }
  }
);
</script>

<template>
  <aside class="col sidebar">
    <div class="ribbon">
      <button class="rb brand" :title="props.brand">
        <TimelineLucideIcon name="book" :stroke-width="1.8" />
      </button>
      <button class="rb" :class="{ active: state.ribbon === 'files' }" title="笔记本" @click="selectRibbon('files')">
        <TimelineLucideIcon name="folder" :stroke-width="1.8" />
      </button>
      <button class="rb" :class="{ active: state.ribbon === 'search' }" title="搜索" @click="focusSearch">
        <TimelineLucideIcon name="search" :stroke-width="1.8" />
      </button>
      <button class="rb" :class="{ active: state.ribbon === 'star' }" title="收藏" @click="openGlobalFavorites">
        <TimelineLucideIcon name="star" :stroke-width="1.8" />
      </button>
      <button class="rb" :class="{ active: state.ribbon === 'tags' }" title="属性" @click="selectRibbon('tags')">
        <TimelineLucideIcon name="sliders" :stroke-width="1.8" />
      </button>
      <button class="rb" :class="{ active: state.ribbon === 'stats' }" title="统计" @click="selectRibbon('stats')">
        <TimelineLucideIcon name="bar" :stroke-width="1.8" />
      </button>
    </div>

    <div class="pane">
      <div class="pane-head">
        <span class="ph-title">{{ activePanel.title }}</span>
        <template v-if="activePanel.tree">
          <button v-if="!selectMode" type="button" class="iconbtn" :title="allCollapsed ? '全部展开' : '全部折叠'" @click="toggleCollapseAll">
            <TimelineLucideIcon :name="allCollapsed ? 'unfold' : 'fold'" :stroke-width="1.8" />
          </button>
          <button type="button" class="iconbtn" :class="{ on: selectMode }" :title="selectMode ? '退出多选' : '多选'" @click="toggleSelectMode">
            <TimelineLucideIcon name="listChecks" :stroke-width="1.8" />
          </button>
        </template>
      </div>

      <div v-if="selectMode && activePanel.tree" class="batch-bar">
        <span class="batch-cnt">已选 {{ selectedTopicIds.length }} 个笔记本</span>
        <button
          type="button"
          class="iconbtn sm"
          :disabled="!selectedTopicIds.length"
          title="删除所选笔记本"
          @click="submitBatchDelete"
        >
          <TimelineLucideIcon name="trash" :stroke-width="1.8" />
        </button>
        <button type="button" class="iconbtn sm" title="退出多选" @click="toggleSelectMode">
          <TimelineLucideIcon name="close" :stroke-width="1.8" />
        </button>
      </div>

      <div class="pane-scroll scroll" @scroll="onPaneScroll">
        <div v-if="panelHas('globalFavorites')" class="tg">
          <div class="tg-body">
            <p class="sidebar-copy">{{ globalFavoritesCopy }}</p>
          </div>
        </div>

        <div v-if="panelHas('views')" class="tg" :class="{ collapsed: state.sections.views }">
          <div class="tg-head" @click="toggleSection('views')">
            <span class="tg-chev"><TimelineLucideIcon name="chevronDown" :stroke-width="1.8" /></span>
            <span class="tg-name">视图</span>
          </div>
          <div class="tg-body">
            <button
              v-for="filter in quickFilters"
              :key="filter.id"
              type="button"
              class="ti leaf"
              :class="{ active: filter.id === props.activeFilter }"
              @click="emit('update:filter', filter.id)"
            >
              <span class="ti-chev"></span>
              <span class="ti-ic"><TimelineLucideIcon :name="filter.icon" :stroke-width="1.8" /></span>
              <span class="ti-name">{{ filter.label }}</span>
              <span class="ti-cnt">{{ filter.count }}</span>
            </button>
          </div>
        </div>

        <div v-if="panelHas('topics')" class="tg" :class="{ collapsed: state.sections.topics }">
          <div class="tg-head" @click="toggleSection('topics')">
            <span class="tg-chev"><TimelineLucideIcon name="chevronDown" :stroke-width="1.8" /></span>
            <span class="tg-name">笔记本</span>
            <button type="button" class="iconbtn sm" :class="{ on: creatingTopic }" title="新建笔记本" @click.stop="startCreateTopic">
              <TimelineLucideIcon name="plusSign" :stroke-width="1.8" />
            </button>
          </div>
          <div class="tg-body">
            <p v-if="props.loading" class="sidebar-copy">正在加载笔记本...</p>
            <p v-else-if="props.error" class="sidebar-copy">{{ props.error }}</p>
            <template v-else>
              <div v-for="topic in props.topics" :key="topic.id">
                <div v-if="renamingTopicId === topic.id" class="ti folder ti-create">
                  <span class="ti-chev"></span>
                  <span class="ti-ic"><TimelineLucideIcon name="folder" :stroke-width="1.8" /></span>
                  <input
                    :ref="(el) => (renameInputRef.value = el)"
                    v-model="renameValue"
                    class="ti-create-input"
                    type="text"
                    :maxlength="CONTENT_LIMITS.topicTitle"
                    @keyup.enter="submitRenameTopic"
                    @keyup.esc="cancelRenameTopic"
                    @blur="onRenameBlur"
                  />
                </div>
                <button
                  v-else
                  type="button"
                  class="ti folder"
                  :class="{
                    active: !selectMode && topic.id === props.activeTopicId,
                    selected: selectMode && isTopicSelected(topic.id),
                    collapsed: !isTopicExpanded(topic.id),
                    'menu-open': topicMenu && topicMenu.topic.id === topic.id,
                  }"
                  @click="toggleTopic(topic.id)"
                >
                  <span v-if="selectMode" class="tcheck" :class="{ on: isTopicSelected(topic.id) }">
                    <TimelineLucideIcon v-if="isTopicSelected(topic.id)" name="check" :stroke-width="2.4" />
                  </span>
                  <span v-else class="ti-chev"><TimelineLucideIcon name="chevronDown" :stroke-width="1.8" /></span>
                  <span class="ti-ic"><TimelineLucideIcon name="folder" :stroke-width="1.8" /></span>
                  <span class="ti-name">{{ topic.title || topic.name }}</span>
                  <span class="ti-cnt">{{ topic.eventCount || 0 }}</span>
                  <span v-if="!selectMode" class="ti-acts">
                    <span class="ti-act" title="更多操作" @click.stop="openTopicMenu(topic, $event)">
                      <TimelineLucideIcon name="more" :stroke-width="1.8" />
                    </span>
                    <span class="ti-act" title="在此笔记本新建笔记" @click.stop="createInTopic(topic.id)">
                      <TimelineLucideIcon name="plusSign" :stroke-width="1.8" />
                    </span>
                  </span>
                </button>
                <Transition name="topic-kids-stack">
                  <div v-if="isTopicExpanded(topic.id)" class="ti-kids-shell">
                    <div class="ti-kids" :style="{ '--pdepth': 0 }">
                      <button
                        v-for="(era, index) in eraRows"
                        :key="era.era"
                        type="button"
                        class="ti leaf"
                        :class="{ active: era.era === props.activeEra }"
                        :style="{ '--depth': 1, '--stack-index': index }"
                        @click="emit('select-era', era.era === props.activeEra ? '' : era.era)"
                      >
                        <span class="ti-chev"></span>
                        <span class="ti-ic"><TimelineLucideIcon name="notebook" :stroke-width="1.8" /></span>
                        <span class="ti-name">{{ era.era }}</span>
                        <span class="ti-cnt">{{ era.count }}</span>
                      </button>
                    </div>
                  </div>
                </Transition>
              </div>
            </template>

            <div v-if="creatingTopic" ref="topicCreateRef" class="ti folder ti-create">
              <span class="ti-chev"></span>
              <span class="ti-ic"><TimelineLucideIcon name="folder" :stroke-width="1.8" /></span>
              <input
                ref="topicInputRef"
                v-model="topicName"
                class="ti-create-input"
                type="text"
                :maxlength="CONTENT_LIMITS.topicTitle"
                placeholder="新笔记本名称"
                @keyup.enter="submitTopic"
                @keyup.esc="cancelCreateTopic"
                @blur="onCreateBlur"
              />
            </div>

            <button
              v-if="!props.loading"
              type="button"
              class="ti leaf ti-add"
              title="新建笔记本"
              @click="startCreateTopic"
            >
              <span class="ti-chev"></span>
              <span class="ti-ic"><TimelineLucideIcon name="plusSign" :stroke-width="1.8" /></span>
              <span class="ti-name">新增</span>
            </button>
          </div>
        </div>

        <div v-if="panelHas('properties')" class="tg" :class="{ collapsed: state.sections.properties }">
          <div class="tg-head" @click="toggleSection('properties')">
            <span class="tg-chev"><TimelineLucideIcon name="chevronDown" :stroke-width="1.8" /></span>
            <span class="tg-name">属性</span>
          </div>
          <div class="tg-body">
            <p v-if="!props.activeTopicId" class="sidebar-copy">先选择一个笔记本。</p>
            <p v-else-if="!propertyRows.length" class="sidebar-copy">暂无属性。</p>
            <template v-else>
              <div v-for="prop in propertyRows" :key="prop.key" class="prop-group">
                <div class="prop-group-head">
                  <span class="prop-group-name">{{ prop.label }}</span>
                  <span class="prop-group-type">{{ propTypeLabel(prop.type) }}</span>
                </div>
                <template v-if="prop.isOption">
                  <button
                    v-for="option in prop.options"
                    :key="option.value"
                    type="button"
                    class="ti leaf tag"
                    :class="{ active: isOptionActive(prop.key, option.value) }"
                    @click="togglePropertyFilter(prop.key, option.value)"
                  >
                    <span class="ti-chev"></span>
                    <span class="ti-dot" :style="{ '--dot': option.color }"></span>
                    <span class="ti-name">{{ option.label }}</span>
                    <span class="ti-cnt">{{ option.count }}</span>
                  </button>
                  <p v-if="!prop.options.length" class="prop-empty">暂无选项</p>
                </template>
                <p v-else class="prop-empty">自由值</p>
              </div>
            </template>
          </div>
        </div>

        <div v-if="panelHas('stats')" class="tg" :class="{ collapsed: state.sections.stats }">
          <div class="tg-head" @click="toggleSection('stats')">
            <span class="tg-chev"><TimelineLucideIcon name="chevronDown" :stroke-width="1.8" /></span>
            <span class="tg-name">统计</span>
          </div>
          <div class="tg-body">
            <div class="mini-stats">
              <div class="ms-cell">
                <div class="ms-num">{{ stats.notes }}</div>
                <div class="ms-cap">笔记</div>
              </div>
              <div class="ms-cell">
                <div class="ms-num accent">{{ stats.week }}</div>
                <div class="ms-cap">本周新增</div>
              </div>
              <div class="ms-cell">
                <div class="ms-num">{{ stats.favorite }}</div>
                <div class="ms-cap">收藏</div>
              </div>
            </div>
            <div class="stat-trend">
              <div class="stat-trend-cap">近 8 周新增</div>
              <div class="spark">
                <span
                  v-for="(bar, index) in weeklyTrend"
                  :key="index"
                  class="spark-bar"
                  :class="{ on: bar.count }"
                  :style="{ height: bar.pct + '%' }"
                  :title="`${bar.count} 条`"
                ></span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="pane-foot">
        <button type="button" class="vault-switch">
          <TimelineLucideIcon name="chevronsUpDown" :stroke-width="1.8" />
          <b>{{ props.brand }}</b>
        </button>
        <button type="button" class="iconbtn" title="帮助">
          <TimelineLucideIcon name="help" :stroke-width="1.8" />
        </button>
        <button type="button" class="iconbtn" title="设置" @click="emit('open-settings')">
          <TimelineLucideIcon name="settings" :stroke-width="1.8" />
        </button>
      </div>
    </div>

    <div v-if="topicMenu" class="ti-menu-backdrop" @click="closeTopicMenu" @contextmenu.prevent="closeTopicMenu">
      <div class="popover ti-menu" :style="{ left: topicMenu.x + 'px', top: topicMenu.y + 'px' }" @click.stop>
        <button type="button" class="pop-item" @click="startRenameTopic(topicMenu.topic)">
          <TimelineLucideIcon name="squarePen" :stroke-width="1.8" class="pop-item-ic" />
          <span class="lbl">重命名</span>
        </button>
        <button type="button" class="pop-item danger" @click="deleteFromMenu(topicMenu.topic)">
          <TimelineLucideIcon name="trash" :stroke-width="1.8" class="pop-item-ic" />
          <span class="lbl">删除</span>
        </button>
      </div>
    </div>
  </aside>
</template>
