<script setup>
import { computed, onBeforeUnmount, watch } from "vue";
import LucideIcon from "@/components/timeline-notes/LucideIcon.vue";
import { attachmentKind } from "@/utils/editorMarkdown";

const props = defineProps({
  attachment: {
    type: Object,
    default: null,
  },
  open: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["close"]);

const kind = computed(() => attachmentKind(props.attachment || {}));
const title = computed(() => props.attachment?.name || props.attachment?.filename || "附件");
const meta = computed(() => {
  if (!props.attachment) return "";
  const type = props.attachment.mimeType || kind.value;
  return `${type}${props.attachment.url ? " · 点击外链可下载原文件" : ""}`;
});

function closeOnEscape(event) {
  if (event.key === "Escape") {
    emit("close");
  }
}

watch(
  () => props.open,
  (open) => {
    if (open) {
      window.addEventListener("keydown", closeOnEscape);
      return;
    }
    window.removeEventListener("keydown", closeOnEscape);
  },
  { immediate: true }
);

onBeforeUnmount(() => {
  window.removeEventListener("keydown", closeOnEscape);
});
</script>

<template>
  <div v-if="props.open" class="modal open" @click="emit('close')">
    <div class="modal-scrim"></div>
    <section class="modal-card" @click.stop>
      <header class="modal-head">
        <b>{{ title }}</b>
        <span class="meta-min">{{ meta }}</span>
        <button type="button" class="iconbtn sm" @click="emit('close')">
          <LucideIcon name="close" :stroke-width="1.5" />
        </button>
      </header>
      <div class="modal-body">
        <img
          v-if="kind === 'image' && props.attachment?.imageUrl"
          class="modal-image"
          :src="props.attachment.url || props.attachment.imageUrl"
          :alt="title"
          loading="lazy"
          decoding="async"
        />
        <iframe
          v-else-if="kind === 'pdf' && props.attachment?.url"
          class="modal-frame"
          :src="props.attachment.url"
          :title="title"
        ></iframe>
        <div v-else class="filepreview">
          <p>当前附件类型不做内嵌预览。</p>
          <a v-if="props.attachment?.url" class="modal-link" :href="props.attachment.url" target="_blank" rel="noopener noreferrer">
            打开原文件
          </a>
        </div>
      </div>
    </section>
  </div>
</template>
