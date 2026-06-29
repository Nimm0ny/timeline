<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import TimelineLucideIcon from "@/components/timeline-notes/TimelineLucideIcon.vue";
import { buildEventPreview, formatEventDisplayDate } from "@/utils/timelineNotes";

const props = defineProps({
  error: {
    type: String,
    default: "",
  },
  event: {
    type: Object,
    default: null,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  open: {
    type: Boolean,
    default: false,
  },
  pinned: {
    type: Boolean,
    default: false,
  },
  placement: {
    type: String,
    default: "left",
  },
  styleVars: {
    type: Object,
    default: () => ({}),
  },
  topicTitle: {
    type: String,
    default: "",
  },
});

const emit = defineEmits(["close", "open-full"]);
const rootRef = ref(null);

const title = computed(() => props.event?.headline || props.event?.displayLabel || "关联事件");
const dateLabel = computed(() => formatEventDisplayDate(props.event) || props.event?.isoDate || "未设置日期");
const groupLabel = computed(() => [props.topicTitle, props.event?.era].filter(Boolean).join(" · ") || "未分组");
const previewText = computed(() => buildEventPreview(props.event, 220) || "暂无正文预览。");

function close() {
  emit("close");
}

function closeOnEscape(event) {
  if (event.key === "Escape") close();
}

function closeOnPointerDown(event) {
  const target = event.target instanceof Element ? event.target : null;
  if (props.open && rootRef.value && target && !rootRef.value.contains(target)) close();
}

watch(
  () => props.open,
  (open) => {
    if (open) {
      window.addEventListener("keydown", closeOnEscape);
      document.addEventListener("pointerdown", closeOnPointerDown);
      return;
    }
    window.removeEventListener("keydown", closeOnEscape);
    document.removeEventListener("pointerdown", closeOnPointerDown);
  },
  { immediate: true }
);

onBeforeUnmount(() => {
  window.removeEventListener("keydown", closeOnEscape);
  document.removeEventListener("pointerdown", closeOnPointerDown);
});
</script>

<template>
  <Teleport to="body">
    <aside
      v-if="props.open"
      ref="rootRef"
      class="related-preview-popover"
      :class="[`place-${props.placement}`, { pinned: props.pinned }]"
      :style="props.styleVars"
      role="dialog"
      aria-label="关联事件预览"
    >
      <span class="related-preview-pointer" aria-hidden="true"></span>
      <header class="related-preview-head">
        <div class="related-preview-title">
          <span class="related-preview-kicker">{{ props.pinned ? "已固定" : "关联预览" }}</span>
          <h3>{{ title }}</h3>
        </div>
        <div v-if="props.pinned" class="related-preview-actions">
          <button type="button" class="iconbtn sm" title="完整打开" aria-label="完整打开" :disabled="props.loading || Boolean(props.error)" @click="emit('open-full')">
            <TimelineLucideIcon name="arrowRight" :stroke-width="1.8" />
          </button>
          <button type="button" class="iconbtn sm" title="关闭" aria-label="关闭" @click="close">
            <TimelineLucideIcon name="close" :stroke-width="1.8" />
          </button>
        </div>
      </header>

      <div class="related-preview-meta">
        <span>
          <TimelineLucideIcon name="calendar" :stroke-width="1.8" />
          {{ dateLabel }}
        </span>
        <span>
          <TimelineLucideIcon name="leaf" :stroke-width="1.8" />
          {{ groupLabel }}
        </span>
      </div>

      <div v-if="props.loading" class="related-preview-state">正在加载关联事件详情...</div>
      <div v-else-if="props.error" class="related-preview-state error">{{ props.error }}</div>
      <p v-else class="related-preview-text">{{ previewText }}</p>
    </aside>
  </Teleport>
</template>
