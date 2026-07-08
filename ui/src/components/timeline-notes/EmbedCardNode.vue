<script setup>
// A canvas note-embed card, rendered as a real DOM node via @antv/x6-vue-shape (a foreignObject
// host). Presentation only: it reads its note id from the X6 node's data and shows the embedded
// note's title + preview from the reactive embed store (filled by one batch-preview on canvas
// open, §7.4). Interaction (open / select / drag) is handled at the graph level in CanvasEditor
// via node:dblclick, so this component never wires navigation and a drag is never read as a click.
import { computed, inject, onBeforeUnmount, onMounted, ref } from "vue";
import { getEmbedEntry } from "@/utils/embedPreviewStore.js";

const getNode = inject("getNode", null);
const node = typeof getNode === "function" ? getNode() : null;

// Mirror the node's data into a ref and keep it synced — the id is fixed, but the cached
// headline/preview fallback can be rewritten on a save, and the card should follow.
const data = ref(node ? { ...(node.getData() || {}) } : {});
function syncData() {
  data.value = { ...(node?.getData() || {}) };
}
onMounted(() => node?.on("change:data", syncData));
onBeforeUnmount(() => node?.off("change:data", syncData));

// Size the card's box in px from the X6 node. A CSS percentage height would resolve against the
// SVG viewport (Chrome foreignObject quirk) and balloon the card, so we set it explicitly. Read
// once — embed cards are a fixed size and the canvas wires no node resizing.
const nodeSize = node ? node.getSize() : { width: 240, height: 120 };
const boxStyle = { width: `${nodeSize.width}px`, height: `${nodeSize.height}px` };

const noteId = computed(() => data.value.noteId ?? null);
const entry = computed(() => getEmbedEntry(noteId.value));
const isTombstone = computed(() => entry.value?.status === "missing");

// Tri-state title: fresh (store) → cached fallback (node data, pre-fetch) → placeholder / tombstone.
const title = computed(() => {
  if (isTombstone.value) return "笔记已删除";
  return entry.value?.headline || (data.value.headline || "").trim() || "无标题";
});
const preview = computed(() => {
  if (isTombstone.value) return "原笔记已被删除，可选中卡片后移除。";
  return entry.value?.preview ?? (data.value.preview || "").trim();
});
const container = computed(() => (isTombstone.value ? "" : entry.value?.container || ""));
</script>

<template>
  <div class="cv-embed-card" :class="{ 'is-tombstone': isTombstone }" :style="boxStyle" :title="title">
    <span class="cv-embed-spine" aria-hidden="true"></span>
    <div class="cv-embed-main">
      <div class="cv-embed-headline">{{ title }}</div>
      <p v-if="preview" class="cv-embed-preview">{{ preview }}</p>
      <div v-if="container" class="cv-embed-container">{{ container }}</div>
    </div>
  </div>
</template>
