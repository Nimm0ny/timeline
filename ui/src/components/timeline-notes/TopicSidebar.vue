<script setup>
import { computed, ref } from "vue";
import { buildTopicMetaLine, collectEventTags } from "@/utils/timelineNotes";
import { pushToast } from "@/composables/useToast";
import { CONTENT_LIMITS } from "@/constants/contentLimits";
import TimelineLucideIcon from "@/components/timeline-notes/TimelineLucideIcon.vue";

const props = defineProps({
  brand: {
    type: String,
    default: "时间线笔记",
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
  activeTag: {
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
  "update:filter",
  "update:tag",
  "open-settings",
]);

const creatingTopic = ref(false);
const topicName = ref("");

function eventCreatedDate(event) {
  const raw = event?.createdAt || event?.updatedAt;
  const date = raw ? new Date(raw) : null;
  return date && !Number.isNaN(date.getTime()) ? date : null;
}

function isToday(event) {
  const date = eventCreatedDate(event);
  if (!date) return false;
  const now = new Date();
  return (
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()
  );
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
  { id: "all", label: "全部笔记", count: countForFilter("all"), icon: "note" },
  { id: "today", label: "今天", count: countForFilter("today"), icon: "calendar" },
  { id: "week", label: "本周", count: countForFilter("week"), icon: "calendar" },
  { id: "favorite", label: "收藏", count: countForFilter("favorite"), icon: "star" },
  { id: "trash", label: "回收站", count: countForFilter("trash"), icon: "trash" },
]);

const currentFilterEvents = computed(() => {
  if (props.activeFilter === "today") return liveEvents.value.filter(isToday);
  if (props.activeFilter === "week") return liveEvents.value.filter(isThisWeek);
  if (props.activeFilter === "favorite") return liveEvents.value.filter((event) => event.favorite);
  if (props.activeFilter === "trash") return deletedEvents.value;
  return liveEvents.value;
});

const tagFilters = computed(() => {
  const counts = new Map();
  for (const event of currentFilterEvents.value) {
    for (const tag of collectEventTags(event)) {
      counts.set(tag.value, {
        value: tag.value,
        label: tag.label,
        count: (counts.get(tag.value)?.count || 0) + 1,
      });
    }
  }
  return [...counts.values()].sort((left, right) => right.count - left.count || left.label.localeCompare(right.label));
});

function submitTopic() {
  const nextName = topicName.value
    .trim()
    .slice(0, CONTENT_LIMITS.topicTitle)
    .replace(/[^\w\-\u4e00-\u9fff]/g, "");
  if (!nextName) {
    pushToast("请输入有效的笔记本名称", "error");
    return;
  }
  emit("create-topic", nextName);
  topicName.value = "";
  creatingTopic.value = false;
}
</script>

<template>
  <aside class="timeline-sidebar">
    <div class="timeline-brand">
      <div class="timeline-brand-main">
        <span class="timeline-brand-mark" aria-hidden="true"></span>
        <h1>{{ brand }}</h1>
      </div>
      <button type="button" class="timeline-icon-btn timeline-menu-btn" aria-label="菜单">
        <TimelineLucideIcon name="menu" :stroke-width="1.8" />
      </button>
    </div>

    <button type="button" class="timeline-sidebar-create" @click="emit('create-event')">
      <TimelineLucideIcon name="pen" :stroke-width="1.8" />
      <span>快速记录</span>
      <kbd>⌘N</kbd>
    </button>

    <nav class="timeline-quick-nav" aria-label="笔记分类">
      <button
        v-for="filter in quickFilters"
        :key="filter.id"
        type="button"
        class="timeline-quick-item"
        :class="{ active: filter.id === props.activeFilter }"
        @click="emit('update:filter', filter.id)"
      >
        <TimelineLucideIcon class="timeline-quick-icon" :name="filter.icon" :stroke-width="1.8" />
        <span>{{ filter.label }}</span>
        <strong>{{ filter.count }}</strong>
      </button>
    </nav>

    <nav class="timeline-sidebar-section" aria-label="笔记本">
      <div class="timeline-sidebar-head">
        <span>笔记本</span>
        <button type="button" class="timeline-mini-btn" @click="creatingTopic = !creatingTopic" aria-label="新建笔记本">
          <TimelineLucideIcon name="plus" :stroke-width="1.8" />
        </button>
      </div>

      <div v-if="creatingTopic" class="timeline-topic-create">
        <input
          v-model="topicName"
          type="text"
          :maxlength="CONTENT_LIMITS.topicTitle"
          placeholder="新笔记本名称"
          @keyup.enter="submitTopic"
        />
        <div class="timeline-inline-actions">
          <button type="button" class="timeline-secondary-btn" @click="creatingTopic = false">取消</button>
          <button type="button" class="timeline-primary-btn" @click="submitTopic">保存</button>
        </div>
      </div>

      <div v-if="props.loading" class="timeline-empty-copy">正在加载笔记本...</div>
      <div v-else-if="props.error" class="timeline-error-copy">{{ props.error }}</div>
      <div v-else-if="props.topics.length === 0" class="timeline-empty-copy">暂无笔记本。</div>

      <div v-else class="timeline-topic-list">
        <button
          v-for="topic in props.topics"
          :key="topic.id"
          type="button"
          class="timeline-topic-item"
          :data-topic-id="topic.id"
          :class="{ active: topic.id === props.activeTopicId }"
          @click="emit('select-topic', topic.id)"
        >
          <span class="timeline-topic-folder" aria-hidden="true"></span>
          <span class="timeline-topic-main">
            <strong>{{ topic.title || topic.name }}</strong>
            <span>{{ buildTopicMetaLine(topic) }}</span>
          </span>
          <strong class="timeline-topic-count">{{ topic.eventCount || 0 }}</strong>
        </button>
      </div>
    </nav>

    <nav class="timeline-sidebar-section timeline-tag-section" aria-label="标签">
      <div class="timeline-sidebar-head">
        <span>标签</span>
        <button
          v-if="props.activeTag"
          type="button"
          class="timeline-clear-tag"
          @click="emit('update:tag', '')"
        >
          清除
        </button>
        <button v-else type="button" class="timeline-mini-btn" aria-label="标签来自当前笔记">
          <TimelineLucideIcon name="plus" :stroke-width="1.8" />
        </button>
      </div>

      <div v-if="tagFilters.length" class="timeline-tag-list">
        <button
          v-for="tag in tagFilters"
          :key="tag.value"
          type="button"
          class="timeline-tag-item"
          :class="{ active: tag.value === props.activeTag }"
          @click="emit('update:tag', tag.value === props.activeTag ? '' : tag.value)"
        >
          <span class="timeline-tag-dot" aria-hidden="true"></span>
          <span>{{ tag.label }}</span>
          <strong>{{ tag.count }}</strong>
        </button>
      </div>
      <p v-else class="timeline-empty-copy timeline-empty-tags">暂无标签</p>
    </nav>

    <button type="button" class="timeline-settings-row" @click="emit('open-settings')">
      <TimelineLucideIcon name="settings" :stroke-width="1.7" />
      <span>设置</span>
    </button>
  </aside>
</template>
