<script setup>
import { ref } from "vue";
import CanvasEditor from "@/components/timeline-notes/CanvasEditor.vue";
import EmbedCardPicker from "@/components/timeline-notes/EmbedCardPicker.vue";
import TimelineLucideIcon from "@/components/timeline-notes/TimelineLucideIcon.vue";

// Center-column host for a canvas note (mirrors MindmapSurface): owns the frame chrome
// (back / title / save status / fullscreen / trash) and a lean toolbar; the page owns
// persistence (@save) and which note is open (@back). The toolbar drives the board
// through the editor's exposed imperative controller. Reuses the mm-* frame styles.
const props = defineProps({
  note: { type: Object, required: true },
  saving: { type: Boolean, default: false },
  // Passed straight through to CanvasEditor for the T2 full-text tier (§7.4); see its prop doc.
  resolveDetail: { type: Function, default: null },
});
const emit = defineEmits(["back", "save", "toggle-favorite", "move-to-trash", "restore", "permanent-delete", "open-embed"]);

const editor = ref(null);
const fullscreen = ref(false);
const openMenu = ref(""); // "" | "bg" | "color"
const activeCount = ref(0);
const currentBackground = ref("");
const pickerOpen = ref(false);

// Backgrounds + text colours are written into the persisted snapshot as raw hex, so
// the editor stores concrete values instead of CSS variable references.
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
  const bg = payload?.background;
  currentBackground.value = bg && bg !== "transparent" ? bg : "";
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
function onPickEmbed({ id, headline } = {}) {
  if (id != null) editor.value?.addEmbedCard?.({ noteId: id, headline });
  pickerOpen.value = false;
}
function requestTrash() {
  editor.value?.cancelPendingSave?.();
  emit("move-to-trash", props.note);
}
function requestPermanentDelete() {
  editor.value?.cancelPendingSave?.();
  emit("permanent-delete", props.note);
}

function pauseAutosave() {
  editor.value?.cancelPendingSave?.();
}
function resumeAutosave() {
  editor.value?.resumeSaves?.();
}
function flushAutosave() {
  editor.value?.flushPendingSave?.();
}
defineExpose({ pauseAutosave, resumeAutosave, flushAutosave });
</script>

<template>
  <section class="col mm-surface" :class="{ 'is-fullscreen': fullscreen }">
    <header class="mm-bar">
      <button type="button" class="iconbtn lg" title="返回列表" @click="emit('back')">
        <TimelineLucideIcon name="arrowLeft" :stroke-width="1.5" />
      </button>
      <div class="mm-head">
        <TimelineLucideIcon name="canvas" :stroke-width="1.5" />
        <h2>{{ note.headline || "未命名画布" }}</h2>
      </div>
      <button
        v-if="!note.deletedAt"
        type="button"
        class="iconbtn lg"
        :class="{ on: note.favorite }"
        :title="note.favorite ? '取消收藏' : '收藏'"
        @click="emit('toggle-favorite', note)"
      >
        <TimelineLucideIcon name="star" :stroke-width="1.5" />
      </button>
      <button v-if="!note.deletedAt" type="button" class="iconbtn lg" title="移入回收站" @click="requestTrash">
        <TimelineLucideIcon name="trash" :stroke-width="1.5" />
      </button>
      <button v-else type="button" class="iconbtn lg" title="恢复" @click="emit('restore', note)">
        <TimelineLucideIcon name="restore" :stroke-width="1.5" />
      </button>
      <button v-if="note.deletedAt" type="button" class="iconbtn lg" title="永久删除" @click="requestPermanentDelete">
        <TimelineLucideIcon name="trash" :stroke-width="1.5" />
      </button>
      <span class="mm-status">{{ note.deletedAt ? "回收站 · 只读" : saving ? "保存中…" : "已保存" }}</span>
      <span class="spacer"></span>
      <button type="button" class="iconbtn lg" :title="fullscreen ? '退出全屏' : '全屏'" @click="toggleFullscreen">
        <TimelineLucideIcon :name="fullscreen ? 'minimize' : 'maximize'" :stroke-width="1.5" />
      </button>
    </header>

    <div class="mm-tools">
      <button type="button" class="iconbtn sm" :disabled="note.deletedAt" title="撤销" @click="editor?.undo()">
        <TimelineLucideIcon name="undo" :stroke-width="1.5" />
      </button>
      <button type="button" class="iconbtn sm" :disabled="note.deletedAt" title="重做" @click="editor?.redo()">
        <TimelineLucideIcon name="redo" :stroke-width="1.5" />
      </button>
      <button type="button" class="iconbtn sm primary" :disabled="note.deletedAt" title="新增卡片" @click="editor?.addCard()">
        <TimelineLucideIcon name="plusSign" :stroke-width="1.5" />
      </button>
      <button type="button" class="iconbtn sm" :disabled="note.deletedAt" title="嵌入笔记" @click="pickerOpen = true">
        <TimelineLucideIcon name="link" :stroke-width="1.5" />
      </button>

      <span class="mm-sep"></span>

      <div class="mm-ctl">
        <button type="button" class="iconbtn sm" :class="{ on: openMenu === 'bg' }" :disabled="note.deletedAt" title="画布背景" @click.stop="toggleMenu('bg')">
          <TimelineLucideIcon name="paint" :stroke-width="1.5" />
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

      <div class="mm-ctl">
        <button
          type="button"
          class="iconbtn sm"
          :class="{ on: openMenu === 'color' }"
          :disabled="note.deletedAt || !activeCount"
          title="文字颜色（先选中卡片）"
          @click.stop="toggleMenu('color')"
        >
          <TimelineLucideIcon name="palette" :stroke-width="1.5" />
        </button>
        <div v-if="openMenu === 'color'" class="mm-menu mm-swatches">
          <button v-for="color in TEXT_COLORS" :key="color" type="button" class="mm-swatch" :style="{ background: color }" @click="pickTextColor(color)"></button>
        </div>
      </div>

      <button type="button" class="iconbtn sm" :disabled="note.deletedAt || !activeCount" title="删除所选（Delete）" @click="editor?.deleteSelected()">
        <TimelineLucideIcon name="trash" :stroke-width="1.5" />
      </button>

      <span v-if="note.deletedAt" class="mm-hint">回收站中的画布为只读，可恢复或永久删除</span>
      <span v-else class="mm-hint">双击空白加卡片 · 双击卡片改文字 · 拖卡片四周圆点连线</span>
    </div>

    <div v-if="openMenu" class="mm-scrim" @click="openMenu = ''"></div>

    <CanvasEditor
      ref="editor"
      :key="note.id"
      :note-id="note.id"
      :tree="note.bodyJson"
      :title="note.headline"
      :read-only="Boolean(note.deletedAt)"
      :resolve-detail="resolveDetail"
      @ready="onReady"
      @active="activeCount = $event"
      @update="emit('save', $event)"
      @open-embed="emit('open-embed', $event)"
    />

    <EmbedCardPicker :open="pickerOpen" @select="onPickEmbed" @close="pickerOpen = false" />
  </section>
</template>
