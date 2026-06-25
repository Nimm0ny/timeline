<script setup>
import { computed, reactive, ref } from "vue";
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
});

const emit = defineEmits([
  "create-event",
  "create-topic",
  "select-topic",
  "select-era",
  "update:filter",
  "update:property-filter",
  "delete-topic",
  "focus-search",
  "open-settings",
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

// Each ribbon owns a distinct left-pane panel (Obsidian-style). The notebook
// tree, tags, and stats are no longer stacked together under one tab.
const RIBBON_PANELS = {
  files: { title: "笔记本", sections: ["views", "topics"], tree: true },
  search: { title: "搜索", sections: ["views", "topics"], tree: true },
  star: { title: "收藏", sections: ["views", "topics"], tree: true },
  tags: { title: "属性", sections: ["properties"], tree: false },
  stats: { title: "统计", sections: ["stats"], tree: false },
  trash: { title: "回收站", sections: ["views", "topics"], tree: true },
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
  { id: "trash", label: "回收站", count: countForFilter("trash"), icon: "trash" },
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

function toggleSection(key) {
  state.sections[key] = !state.sections[key];
}

function toggleTopic(topicId) {
  state.topicCollapsed[topicId] = !state.topicCollapsed[topicId];
  emit("select-topic", topicId);
}

function focusSearch() {
  state.ribbon = "search";
  emit("focus-search");
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
</script>

<template>
  <aside class="col sidebar">
    <div class="ribbon">
      <button class="rb brand" :title="props.brand">
        <TimelineLucideIcon name="book" :stroke-width="1.8" />
      </button>
      <button class="rb" :class="{ active: state.ribbon === 'files' }" title="笔记本" @click="state.ribbon = 'files'">
        <TimelineLucideIcon name="folder" :stroke-width="1.8" />
      </button>
      <button class="rb" :class="{ active: state.ribbon === 'search' }" title="搜索" @click="focusSearch">
        <TimelineLucideIcon name="search" :stroke-width="1.8" />
      </button>
      <button class="rb" :class="{ active: state.ribbon === 'star' }" title="收藏" @click="state.ribbon = 'star'">
        <TimelineLucideIcon name="star" :stroke-width="1.8" />
      </button>
      <button class="rb" :class="{ active: state.ribbon === 'tags' }" title="属性" @click="state.ribbon = 'tags'">
        <TimelineLucideIcon name="sliders" :stroke-width="1.8" />
      </button>
      <button class="rb" :class="{ active: state.ribbon === 'stats' }" title="统计" @click="state.ribbon = 'stats'">
        <TimelineLucideIcon name="bar" :stroke-width="1.8" />
      </button>
      <span class="sp"></span>
      <button class="rb" :class="{ active: state.ribbon === 'trash' }" title="回收站" @click="state.ribbon = 'trash'">
        <TimelineLucideIcon name="trash" :stroke-width="1.8" />
      </button>
    </div>

    <div class="pane">
      <div class="pane-head">
        <span class="ph-title">{{ activePanel.title }}</span>
        <template v-if="activePanel.tree">
          <button
            v-if="props.activeTopicId"
            type="button"
            class="iconbtn"
            title="删除当前笔记本"
            @click="emit('delete-topic', props.activeTopicId)"
          >
            <TimelineLucideIcon name="trash" :stroke-width="1.8" />
          </button>
          <button type="button" class="iconbtn" title="新建笔记" @click="emit('create-event')">
            <TimelineLucideIcon name="squarePen" :stroke-width="1.8" />
          </button>
          <button type="button" class="iconbtn" title="新建笔记本" @click="creatingTopic = !creatingTopic">
            <TimelineLucideIcon name="folderPlus" :stroke-width="1.8" />
          </button>
          <button type="button" class="iconbtn" title="排序">
            <TimelineLucideIcon name="arrowUpDown" :stroke-width="1.8" />
          </button>
          <button type="button" class="iconbtn" :title="allCollapsed ? '全部展开' : '全部折叠'" @click="toggleCollapseAll">
            <TimelineLucideIcon :name="allCollapsed ? 'unfold' : 'fold'" :stroke-width="1.8" />
          </button>
        </template>
      </div>

      <div class="pane-scroll scroll">
        <div v-if="creatingTopic" class="topic-inline-create">
          <input
            v-model="topicName"
            type="text"
            :maxlength="CONTENT_LIMITS.topicTitle"
            placeholder="新笔记本名称"
            @keyup.enter="submitTopic"
          />
          <div class="topic-inline-actions">
            <button type="button" class="iconbtn sm" @click="creatingTopic = false">
              <TimelineLucideIcon name="close" :stroke-width="1.8" />
            </button>
            <button type="button" class="iconbtn sm primary" @click="submitTopic">
              <TimelineLucideIcon name="check" :stroke-width="1.8" />
            </button>
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
            <button type="button" class="iconbtn sm" title="新建笔记本" @click.stop="creatingTopic = !creatingTopic">
              <TimelineLucideIcon name="folderPlus" :stroke-width="1.8" />
            </button>
          </div>
          <div class="tg-body">
            <p v-if="props.loading" class="sidebar-copy">正在加载笔记本...</p>
            <p v-else-if="props.error" class="sidebar-copy">{{ props.error }}</p>
            <template v-else>
              <div v-for="topic in props.topics" :key="topic.id">
                <button
                  type="button"
                  class="ti folder"
                  :class="{ active: topic.id === props.activeTopicId, collapsed: state.topicCollapsed[topic.id] }"
                  @click="toggleTopic(topic.id)"
                >
                  <span class="ti-chev"><TimelineLucideIcon name="chevronDown" :stroke-width="1.8" /></span>
                  <span class="ti-ic"><TimelineLucideIcon name="folder" :stroke-width="1.8" /></span>
                  <span class="ti-name">{{ topic.title || topic.name }}</span>
                  <span class="ti-cnt">{{ topic.eventCount || 0 }}</span>
                </button>
                <div
                  v-if="topic.id === props.activeTopicId && !state.topicCollapsed[topic.id]"
                  class="ti-kids"
                  :style="{ '--pdepth': 0 }"
                >
                  <button
                    v-for="era in eraRows"
                    :key="era.era"
                    type="button"
                    class="ti leaf"
                    :class="{ active: era.era === props.activeEra }"
                    :style="{ '--depth': 1 }"
                    @click="emit('select-era', era.era === props.activeEra ? '' : era.era)"
                  >
                    <span class="ti-chev"></span>
                    <span class="ti-ic"><TimelineLucideIcon name="notebook" :stroke-width="1.8" /></span>
                    <span class="ti-name">{{ era.era }}</span>
                    <span class="ti-cnt">{{ era.count }}</span>
                  </button>
                </div>
              </div>
            </template>
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
  </aside>
</template>
