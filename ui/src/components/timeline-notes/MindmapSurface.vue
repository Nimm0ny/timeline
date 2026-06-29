<script setup>
import { ref } from "vue";
import MindmapEditor from "@/components/timeline-notes/MindmapEditor.vue";
import TimelineLucideIcon from "@/components/timeline-notes/TimelineLucideIcon.vue";

// Center-column host for a mindmap note (D-2: 中栏内嵌 + 可全屏). Owns the frame
// chrome (back to list / title / save status / fullscreen) and the canvas; the
// page owns persistence (@save) and which note is open (@back).
const props = defineProps({
  note: { type: Object, required: true },
  saving: { type: Boolean, default: false },
});
const emit = defineEmits(["back", "save"]);

const fullscreen = ref(false);
function toggleFullscreen() {
  fullscreen.value = !fullscreen.value;
}
</script>

<template>
  <section class="col mm-surface" :class="{ 'is-fullscreen': fullscreen }">
    <header class="mm-bar">
      <button type="button" class="iconbtn lg" title="返回列表" @click="emit('back')">
        <TimelineLucideIcon name="arrowLeft" :stroke-width="1.8" />
      </button>
      <div class="mm-head">
        <TimelineLucideIcon name="mindmap" :stroke-width="1.8" />
        <h2>{{ note.headline || "未命名导图" }}</h2>
      </div>
      <span class="mm-status">{{ saving ? "保存中…" : "已保存" }}</span>
      <span class="spacer"></span>
      <button type="button" class="iconbtn lg" :title="fullscreen ? '退出全屏' : '全屏'" @click="toggleFullscreen">
        <TimelineLucideIcon :name="fullscreen ? 'minimize' : 'maximize'" :stroke-width="1.8" />
      </button>
    </header>
    <MindmapEditor :key="note.id" :note-id="note.id" :tree="note.bodyJson" :title="note.headline" @update="emit('save', $event)" />
  </section>
</template>
