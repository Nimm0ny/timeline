<script setup>
import { ref } from "vue";
import MindmapEditor from "@/components/timeline-notes/MindmapEditor.vue";
import TimelineLucideIcon from "@/components/timeline-notes/TimelineLucideIcon.vue";
import { MINDMAP_LAYOUTS } from "@/utils/timelineNotes.js";

// Center-column host for a mindmap note (D-2: 中栏内嵌 + 可全屏). Owns the frame
// chrome (back / title / save status / fullscreen), the editing toolbar, and the
// canvas; the page owns persistence (@save) and which note is open (@back). The
// toolbar drives the canvas through the editor's exposed imperative controller.
const props = defineProps({
  note: { type: Object, required: true },
  saving: { type: Boolean, default: false },
});
const emit = defineEmits(["back", "save"]);

const editor = ref(null);
const fullscreen = ref(false);
const openMenu = ref(""); // "" | "layout" | "bg" | "color"
const activeCount = ref(0);
const currentLayout = ref("logicalStructure");
const currentBackground = ref("");

// Canvas backgrounds + node text colours. Raw hex on purpose: these are written into
// simple-mind-map's own snapshot (body_json), not app CSS, so the library needs
// concrete colours — it can't resolve var(--token). "跟随主题" (value "") keeps the
// canvas transparent so the map tracks the app's light/dark theme.
const BACKGROUNDS = [
  { value: "", label: "跟随主题" },
  { value: "#faf8f4", label: "纸白" },
  { value: "#ffffff", label: "纯白" },
  { value: "#f4f1ea", label: "米色" },
  { value: "#eef2f3", label: "冷灰" },
  { value: "#2a2722", label: "深色" },
];
const TEXT_COLORS = ["#2a2722", "#b5654d", "#3b7a57", "#2f6f9f", "#8a6d3b", "#ffffff"];

function toggleFullscreen() {
  fullscreen.value = !fullscreen.value;
}
function toggleMenu(name) {
  openMenu.value = openMenu.value === name ? "" : name;
}
function onReady(payload) {
  currentLayout.value = payload?.layout || currentLayout.value;
  // A transparent canvas (follow-theme) normalises to "" so the 跟随主题 swatch lights up.
  const bg = payload?.background;
  currentBackground.value = bg && bg !== "transparent" ? bg : "";
}
function pickLayout(key) {
  editor.value?.setLayout(key);
  currentLayout.value = key;
  openMenu.value = "";
}
function pickBackground(value) {
  editor.value?.setBackground(value);
  currentBackground.value = value;
  openMenu.value = "";
}
function pickTextColor(color) {
  editor.value?.setTextColor(color);
  openMenu.value = "";
}
function currentLayoutLabel() {
  return MINDMAP_LAYOUTS.find((item) => item.key === currentLayout.value)?.label || "布局";
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

    <div class="mm-tools">
      <button type="button" class="iconbtn sm" title="撤销" @click="editor?.undo()">
        <TimelineLucideIcon name="undo" :stroke-width="1.8" />
      </button>
      <button type="button" class="iconbtn sm" title="重做" @click="editor?.redo()">
        <TimelineLucideIcon name="redo" :stroke-width="1.8" />
      </button>

      <span class="mm-sep"></span>

      <div class="mm-ctl">
        <button type="button" class="iconbtn sm wide" :class="{ on: openMenu === 'layout' }" title="布局方向" @click.stop="toggleMenu('layout')">
          <TimelineLucideIcon name="layout" :stroke-width="1.8" />
          <span class="mm-ctl-label">{{ currentLayoutLabel() }}</span>
          <TimelineLucideIcon name="chevronDown" :stroke-width="1.8" />
        </button>
        <div v-if="openMenu === 'layout'" class="mm-menu">
          <button
            v-for="item in MINDMAP_LAYOUTS"
            :key="item.key"
            type="button"
            class="mm-menu-item"
            :class="{ on: item.key === currentLayout }"
            @click="pickLayout(item.key)"
          >
            <span>{{ item.label }}</span>
            <TimelineLucideIcon v-if="item.key === currentLayout" name="check" :stroke-width="2" />
          </button>
        </div>
      </div>

      <div class="mm-ctl">
        <button type="button" class="iconbtn sm" :class="{ on: openMenu === 'bg' }" title="画布背景" @click.stop="toggleMenu('bg')">
          <TimelineLucideIcon name="paint" :stroke-width="1.8" />
        </button>
        <div v-if="openMenu === 'bg'" class="mm-menu mm-swatches">
          <button
            v-for="bg in BACKGROUNDS"
            :key="bg.value || 'follow'"
            type="button"
            class="mm-swatch"
            :class="{ on: bg.value === currentBackground, 'is-follow': bg.value === '' }"
            :style="{ background: bg.value || 'var(--bg-surface)' }"
            :title="bg.label"
            @click="pickBackground(bg.value)"
          ></button>
        </div>
      </div>

      <span class="mm-sep"></span>

      <button type="button" class="iconbtn sm" :disabled="!activeCount" title="缩小字号（先选中节点）" @click="editor?.nudgeFontSize(-2)">
        <TimelineLucideIcon name="fontDown" :stroke-width="1.8" />
      </button>
      <button type="button" class="iconbtn sm" :disabled="!activeCount" title="放大字号（先选中节点）" @click="editor?.nudgeFontSize(2)">
        <TimelineLucideIcon name="fontUp" :stroke-width="1.8" />
      </button>
      <button type="button" class="iconbtn sm" :disabled="!activeCount" title="加粗（先选中节点）" @click="editor?.toggleBold()">
        <TimelineLucideIcon name="bold" :stroke-width="1.8" />
      </button>
      <div class="mm-ctl">
        <button type="button" class="iconbtn sm" :class="{ on: openMenu === 'color' }" :disabled="!activeCount" title="文字颜色（先选中节点）" @click.stop="toggleMenu('color')">
          <TimelineLucideIcon name="palette" :stroke-width="1.8" />
        </button>
        <div v-if="openMenu === 'color'" class="mm-menu mm-swatches">
          <button
            v-for="color in TEXT_COLORS"
            :key="color"
            type="button"
            class="mm-swatch"
            :style="{ background: color }"
            @click="pickTextColor(color)"
          ></button>
        </div>
      </div>

      <span v-if="!activeCount" class="mm-hint">选中节点后可调字号与颜色</span>
    </div>

    <div v-if="openMenu" class="mm-scrim" @click="openMenu = ''"></div>

    <MindmapEditor
      ref="editor"
      :key="note.id"
      :note-id="note.id"
      :tree="note.bodyJson"
      :title="note.headline"
      @ready="onReady"
      @active="activeCount = $event"
      @update="emit('save', $event)"
    />
  </section>
</template>
