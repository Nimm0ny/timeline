<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import LucideIcon from "@/components/notes/LucideIcon.vue";
import { buildNotePreview, formatNoteDisplayDate } from "@/utils/noteUtils";

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
const viewportShift = ref(0);

const title = computed(() => props.event?.headline || props.event?.displayLabel || "关联事件");
const dateLabel = computed(() => formatNoteDisplayDate(props.event) || props.event?.isoDate || "未设置日期");
const groupLabel = computed(() => [props.topicTitle, props.event?.era].filter(Boolean).join(" · ") || "未分组");
const previewText = computed(() => buildNotePreview(props.event, 220) || "暂无正文预览。");
const mergedStyle = computed(() => {
  const top = pxNumber(props.styleVars?.top);
  const anchorY = pxNumber(props.styleVars?.["--related-anchor-y"], 38);
  return {
    ...props.styleVars,
    top: `${Math.round(top + viewportShift.value)}px`,
    "--related-anchor-y": `${Math.round(anchorY - viewportShift.value)}px`,
  };
});

function pxNumber(value, fallback = 0) {
  const parsed = Number.parseFloat(String(value ?? ""));
  return Number.isFinite(parsed) ? parsed : fallback;
}

function syncViewportFit() {
  if (!props.open) return;
  viewportShift.value = 0;
  nextTick(() => {
    const node = rootRef.value;
    if (!node || typeof window === "undefined") return;
    const margin = 12;
    const rect = node.getBoundingClientRect();
    let shift = 0;
    if (rect.bottom > window.innerHeight - margin) shift -= rect.bottom - (window.innerHeight - margin);
    if (rect.top + shift < margin) shift += margin - (rect.top + shift);
    viewportShift.value = Math.round(shift);
  });
}

function handleWindowResize() {
  syncViewportFit();
}

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
      window.addEventListener("resize", handleWindowResize);
      syncViewportFit();
      return;
    }
    window.removeEventListener("keydown", closeOnEscape);
    document.removeEventListener("pointerdown", closeOnPointerDown);
    window.removeEventListener("resize", handleWindowResize);
    viewportShift.value = 0;
  },
  { immediate: true }
);

watch(
  () => [props.loading, props.error, previewText.value, props.styleVars?.top, props.styleVars?.["--related-anchor-y"]],
  () => {
    if (props.open) syncViewportFit();
  }
);

onBeforeUnmount(() => {
  window.removeEventListener("keydown", closeOnEscape);
  document.removeEventListener("pointerdown", closeOnPointerDown);
  window.removeEventListener("resize", handleWindowResize);
});
</script>

<template>
  <Teleport to="body">
    <aside
      v-if="props.open"
      ref="rootRef"
      class="related-preview-popover"
      :class="[`place-${props.placement}`, { pinned: props.pinned }]"
      :style="mergedStyle"
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
            <LucideIcon name="arrowRight" :stroke-width="1.5" />
          </button>
          <button type="button" class="iconbtn sm" title="关闭" aria-label="关闭" @click="close">
            <LucideIcon name="close" :stroke-width="1.5" />
          </button>
        </div>
      </header>

      <div class="related-preview-meta">
        <span>
          <LucideIcon name="calendar" :stroke-width="1.5" />
          {{ dateLabel }}
        </span>
        <span>
          <LucideIcon name="leaf" :stroke-width="1.5" />
          {{ groupLabel }}
        </span>
      </div>

      <div v-if="props.loading" class="related-preview-state">正在加载关联事件详情...</div>
      <div v-else-if="props.error" class="related-preview-state error">{{ props.error }}</div>
      <p v-else class="related-preview-text">{{ previewText }}</p>
    </aside>
  </Teleport>
</template>
