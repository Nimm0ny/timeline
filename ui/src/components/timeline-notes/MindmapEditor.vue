<script setup>
import { onBeforeUnmount, onMounted, ref, shallowRef } from "vue";

// Thin Vue wrapper around simple-mind-map (the authorized mindmap dependency; see
// AGENTS.md §9). The library is framework-agnostic and DOM-driven, so we own only
// its lifecycle: init into a sized container on mount, persist the tree on change
// (debounced) and on unmount, and tear it down. The heavy full-feature bundle is
// dynamically imported so it only loads when a mindmap note is actually opened.
const props = defineProps({
  // Id of the note this canvas is bound to. The parent keys the editor per note, so
  // this is stable for the instance's life; it rides the save event so a flush during
  // a note switch (or after close) writes to the right note, never the new one.
  noteId: { type: [Number, String], default: null },
  // Stored body_json tree ({ data, children }); null/!data → seed a single root.
  tree: { type: [Object, Array, null], default: null },
  // Seeds the root node's text when there is no stored tree yet.
  title: { type: String, default: "" },
});

const emit = defineEmits(["update", "ready"]);

const canvasRef = ref(null);
const mindMap = shallowRef(null);
const loading = ref(true);
let saveTimer = null;
let resizeObserver = null;
let resizeTimer = null;

function seedTree() {
  const tree = props.tree;
  if (tree && typeof tree === "object" && tree.data && typeof tree.data === "object") return tree;
  return { data: { text: props.title?.trim() || "中心主题" }, children: [] };
}

function flushSave() {
  if (saveTimer) {
    clearTimeout(saveTimer);
    saveTimer = null;
  }
  if (!mindMap.value) return;
  try {
    emit("update", { id: props.noteId, tree: mindMap.value.getData(false) });
  } catch {
    /* instance already destroyed — nothing to persist */
  }
}

function scheduleSave() {
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = setTimeout(flushSave, 600);
}

function scheduleResize() {
  if (resizeTimer) clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => mindMap.value?.resize(), 80);
}

onMounted(async () => {
  const { default: MindMap } = await import("simple-mind-map/full.js");
  // Guard against the component unmounting before the async import resolved.
  if (!canvasRef.value) return;
  mindMap.value = new MindMap({
    el: canvasRef.value,
    data: seedTree(),
    layout: "logicalStructure",
  });
  mindMap.value.on("data_change", scheduleSave);
  if (typeof ResizeObserver !== "undefined") {
    resizeObserver = new ResizeObserver(scheduleResize);
    resizeObserver.observe(canvasRef.value);
  }
  loading.value = false;
  emit("ready");
});

onBeforeUnmount(() => {
  if (resizeTimer) clearTimeout(resizeTimer);
  resizeObserver?.disconnect();
  resizeObserver = null;
  // Persist a pending edit before the canvas goes away (quick edit-then-close).
  flushSave();
  if (mindMap.value) {
    mindMap.value.destroy();
    mindMap.value = null;
  }
});
</script>

<template>
  <div class="mm-editor">
    <div ref="canvasRef" class="mm-canvas"></div>
    <div v-if="loading" class="mm-loading">正在加载思维导图…</div>
  </div>
</template>
