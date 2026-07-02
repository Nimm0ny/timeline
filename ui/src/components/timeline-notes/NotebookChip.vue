<script setup>
import { computed } from "vue";
import TimelineLucideIcon from "@/components/timeline-notes/TimelineLucideIcon.vue";

const props = defineProps({
  topicId: {
    type: Number,
    default: null,
  },
  topics: {
    type: Array,
    default: () => [],
  },
});

const NOTEBOOK_COLORS = [
  "var(--accent)",
  "var(--t-war)",
  "var(--t-politics)",
  "var(--t-culture)",
  "var(--t-reform)",
  "var(--t-diplomacy)",
  "var(--t-economy)",
  "var(--t-science)",
];

const topic = computed(() => props.topics.find((item) => Number(item.id) === Number(props.topicId)) || null);
const label = computed(() => topic.value?.title || topic.value?.name || (props.topicId ? `笔记本 ${props.topicId}` : "未知笔记本"));
const dotColor = computed(() => NOTEBOOK_COLORS[Math.abs(Number(props.topicId) || 0) % NOTEBOOK_COLORS.length]);
</script>

<template>
  <span class="notebook-chip" :title="label">
    <span class="notebook-chip-dot" :style="{ '--notebook-dot': dotColor }"></span>
    <TimelineLucideIcon name="notebook" :stroke-width="1.5" />
    <span class="notebook-chip-label">{{ label }}</span>
  </span>
</template>
