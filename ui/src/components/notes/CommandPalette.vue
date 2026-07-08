<script setup>
import { computed, nextTick, ref, watch } from "vue";
import BaseModal from "@/components/BaseModal.vue";
import HighlightedText from "@/components/notes/HighlightedText.vue";
import NotebookChip from "@/components/notes/NotebookChip.vue";
import LucideIcon from "@/components/notes/LucideIcon.vue";

const props = defineProps({
  open: {
    type: Boolean,
    default: false,
  },
  query: {
    type: String,
    default: "",
  },
  events: {
    type: Array,
    default: () => [],
  },
  topics: {
    type: Array,
    default: () => [],
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

const emit = defineEmits(["close", "update:query", "select-event", "select-topic", "command"]);

const inputRef = ref(null);
const activeIndex = ref(0);

const commands = [
  { id: "new-event", label: "新建事件", icon: "plusCircle", shortcut: "Alt N", key: "n" },
  { id: "new-topic", label: "新建笔记本", icon: "folderPlus", shortcut: "Alt B", key: "b" },
  { id: "settings", label: "设置", icon: "settings", shortcut: "Alt ,", key: "," },
  { id: "export", label: "导出", icon: "download", shortcut: "Alt E", key: "e" },
];

const normalizedQuery = computed(() => props.query.trim().toLowerCase());

const topicResults = computed(() => {
  const query = normalizedQuery.value;
  const rows = query
    ? props.topics.filter((topic) => `${topic.title || ""} ${topic.name || ""}`.toLowerCase().includes(query))
    : props.topics.slice(0, 5);
  return rows.slice(0, 6);
});

const sections = computed(() => [
  {
    id: "events",
    label: "事件",
    items: props.events.map((event) => ({ type: "event", key: `event-${event.id}`, value: event })),
  },
  {
    id: "topics",
    label: "笔记本",
    items: topicResults.value.map((topic) => ({ type: "topic", key: `topic-${topic.id}`, value: topic })),
  },
  {
    id: "commands",
    label: "操作 / 命令",
    items: commands.map((command) => ({ type: "command", key: `command-${command.id}`, value: command })),
  },
]);

const visibleSections = computed(() => sections.value.filter((section) => section.items.length));
const flatItems = computed(() => visibleSections.value.flatMap((section) => section.items));

function close() {
  emit("close");
}

function updateQuery(event) {
  emit("update:query", event.target.value);
}

function moveActive(delta) {
  const count = flatItems.value.length;
  if (!count) return;
  activeIndex.value = (activeIndex.value + delta + count) % count;
}

function activate(item = flatItems.value[activeIndex.value]) {
  if (!item) return;
  if (item.type === "event") emit("select-event", item.value);
  if (item.type === "topic") emit("select-topic", item.value);
  if (item.type === "command") emit("command", item.value.id);
}

function onKeydown(event) {
  if (event.key === "ArrowDown") {
    event.preventDefault();
    moveActive(1);
    return;
  }
  if (event.key === "ArrowUp") {
    event.preventDefault();
    moveActive(-1);
    return;
  }
  if (event.key === "Enter") {
    event.preventDefault();
    activate();
    return;
  }
  if (event.key === "Escape") {
    event.preventDefault();
    close();
    return;
  }
  if (event.altKey && !event.ctrlKey && !event.metaKey && !event.shiftKey) {
    const command = commands.find((item) => item.key === event.key.toLowerCase());
    if (command) {
      event.preventDefault();
      emit("command", command.id);
    }
  }
}

function itemIndex(key) {
  return flatItems.value.findIndex((item) => item.key === key);
}

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    activeIndex.value = 0;
    nextTick(() => inputRef.value?.focus());
  }
);

watch(
  () => [flatItems.value.length, props.query],
  () => {
    if (activeIndex.value >= flatItems.value.length) activeIndex.value = 0;
  }
);
</script>

<template>
  <BaseModal
    :model-value="props.open"
    title="搜索命令面板"
    wide
    hide-header
    aria-label="搜索命令面板"
    card-class="command-palette-card"
    body-class="command-palette-body"
    @update:model-value="close"
  >
    <section class="command-palette" @keydown="onKeydown">
      <label class="command-search-field">
        <LucideIcon name="search" :stroke-width="1.5" />
        <input
          ref="inputRef"
          :value="props.query"
          type="search"
          placeholder="搜索事件、笔记本或命令"
          @input="updateQuery"
        />
        <span v-if="props.loading" class="command-search-state">搜索中</span>
      </label>

      <div class="command-results" role="listbox" aria-label="搜索结果">
        <p v-if="props.error" class="command-message">{{ props.error }}</p>
        <template v-for="section in visibleSections" :key="section.id">
          <div class="command-section-label">{{ section.label }}</div>
          <button
            v-for="item in section.items"
            :key="item.key"
            type="button"
            class="command-result-row"
            :class="{ active: itemIndex(item.key) === activeIndex }"
            role="option"
            :aria-selected="itemIndex(item.key) === activeIndex"
            @mouseenter="activeIndex = itemIndex(item.key)"
            @click="activate(item)"
          >
            <template v-if="item.type === 'event'">
              <span class="command-row-main">
                <span class="command-row-title"><HighlightedText :text="item.value.headline" :query="props.query" /></span>
                <span class="command-row-sub"><HighlightedText :text="item.value.snippet || '—'" :query="props.query" /></span>
              </span>
              <span class="command-row-meta">
                <NotebookChip :topic-id="item.value.topicId" :topics="props.topics" />
                <span class="command-date">{{ item.value.isoDate || item.value.dateKey || "未定时间" }}</span>
              </span>
            </template>

            <template v-else-if="item.type === 'topic'">
              <span class="command-row-main">
                <span class="command-row-title"><HighlightedText :text="item.value.title || item.value.name" :query="props.query" /></span>
                <span class="command-row-sub">笔记本</span>
              </span>
              <span class="command-row-meta">
                <span class="command-date">{{ item.value.eventCount || 0 }} 条</span>
              </span>
            </template>

            <template v-else>
              <span class="command-row-main command-command-main">
                <LucideIcon :name="item.value.icon" :stroke-width="1.5" />
                <span class="command-row-title">{{ item.value.label }}</span>
              </span>
              <span class="command-row-meta">
                <kbd class="command-shortcut">{{ item.value.shortcut }}</kbd>
              </span>
            </template>
          </button>
        </template>
      </div>
    </section>
  </BaseModal>
</template>
