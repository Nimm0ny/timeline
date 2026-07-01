<script setup>
import { ref } from "vue";
import MindmapEditor from "@/components/timeline-notes/MindmapEditor.vue";
import TimelineLucideIcon from "@/components/timeline-notes/TimelineLucideIcon.vue";
import { pushToast } from "@/composables/useToast";
import { DEFAULT_EDGE_STYLE, MINDMAP_EDGE_STYLES } from "@/utils/mindmapX6.js";
import { DEFAULT_MINDMAP_LAYOUT, MINDMAP_LAYOUTS } from "@/utils/timelineNotes.js";

// Center-column host for a mindmap note (D-2: 中栏内嵌 + 可全屏). Owns the frame
// chrome (back / title / save status / fullscreen), the editing toolbar, and the
// canvas; the page owns persistence (@save) and which note is open (@back). The
// toolbar drives the canvas through the editor's exposed imperative controller.
const props = defineProps({
  note: { type: Object, required: true },
  saving: { type: Boolean, default: false },
});
const emit = defineEmits(["back", "save", "toggle-favorite", "move-to-trash", "restore", "permanent-delete"]);

const editor = ref(null);
const fullscreen = ref(false);
const openMenu = ref(""); // "" | "layout" | "edge" | "bg" | "color" | "bridge"
const activeCount = ref(0);
const currentLayout = ref(DEFAULT_MINDMAP_LAYOUT);
const currentBackground = ref("");
const currentEdgeStyle = ref(DEFAULT_EDGE_STYLE);
const markdownInputRef = ref(null);
const jsonInputRef = ref(null);

// Canvas backgrounds + node text colours are written into the persisted X6
// snapshot, so the editor stores raw hex instead of CSS variable references.
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
  currentEdgeStyle.value = payload?.edgeStyle || DEFAULT_EDGE_STYLE;
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

function currentEdgeStyleLabel() {
  return MINDMAP_EDGE_STYLES.find((item) => item.key === currentEdgeStyle.value)?.label || "连线样式";
}

function pickEdgeStyle(style) {
  editor.value?.setEdgeStyle(style);
  currentEdgeStyle.value = style;
  openMenu.value = "";
}

function requestTrash() {
  editor.value?.cancelPendingSave?.();
  emit("move-to-trash", props.note);
}

function requestPermanentDelete() {
  editor.value?.cancelPendingSave?.();
  emit("permanent-delete", props.note);
}

function fileBaseName() {
  return (String(props.note?.headline || "思维导图").trim() || "思维导图").replace(/[<>:\"/\\\\|?*]+/g, "-");
}

async function exportFile(type) {
  openMenu.value = "";
  try {
    await editor.value?.exportFile(type, fileBaseName());
  } catch (error) {
    pushToast(`导出失败：${error.message || error}`, "error");
  }
}

function triggerImport(kind) {
  openMenu.value = "";
  if (kind === "json") jsonInputRef.value?.click();
  else markdownInputRef.value?.click();
}

async function onJsonImport(event) {
  const file = event.target.files?.[0];
  event.target.value = "";
  if (!file) return;
  try {
    await editor.value?.importSnapshot(await file.text());
    pushToast("X6 JSON 已导入");
  } catch (error) {
    pushToast(`X6 JSON 导入失败：${error.message || error}`, "error");
  }
}

async function onMarkdownImport(event) {
  const file = event.target.files?.[0];
  event.target.value = "";
  if (!file) return;
  try {
    await editor.value?.importMarkdown(await file.text());
    pushToast("Markdown 已导入");
  } catch (error) {
    pushToast(`Markdown 导入失败：${error.message || error}`, "error");
  }
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
        <TimelineLucideIcon name="arrowLeft" :stroke-width="1.8" />
      </button>
      <div class="mm-head">
        <TimelineLucideIcon name="mindmap" :stroke-width="1.8" />
        <h2>{{ note.headline || "未命名导图" }}</h2>
      </div>
      <button
        v-if="!note.deletedAt"
        type="button"
        class="iconbtn lg"
        :class="{ on: note.favorite }"
        :title="note.favorite ? '取消收藏' : '收藏'"
        @click="emit('toggle-favorite', note)"
      >
        <TimelineLucideIcon name="star" :stroke-width="1.8" />
      </button>
      <button v-if="!note.deletedAt" type="button" class="iconbtn lg" title="移入回收站" @click="requestTrash">
        <TimelineLucideIcon name="trash" :stroke-width="1.8" />
      </button>
      <button v-else type="button" class="iconbtn lg" title="恢复" @click="emit('restore', note)">
        <TimelineLucideIcon name="restore" :stroke-width="1.8" />
      </button>
      <button v-if="note.deletedAt" type="button" class="iconbtn lg" title="永久删除" @click="requestPermanentDelete">
        <TimelineLucideIcon name="trash" :stroke-width="1.8" />
      </button>
      <span class="mm-status">{{ note.deletedAt ? "回收站 · 只读" : saving ? "保存中…" : "已保存" }}</span>
      <span class="spacer"></span>
      <button type="button" class="iconbtn lg" :title="fullscreen ? '退出全屏' : '全屏'" @click="toggleFullscreen">
        <TimelineLucideIcon :name="fullscreen ? 'minimize' : 'maximize'" :stroke-width="1.8" />
      </button>
    </header>

    <div class="mm-tools">
      <button type="button" class="iconbtn sm" :disabled="note.deletedAt" title="撤销" @click="editor?.undo()">
        <TimelineLucideIcon name="undo" :stroke-width="1.8" />
      </button>
      <button type="button" class="iconbtn sm" :disabled="note.deletedAt" title="重做" @click="editor?.redo()">
        <TimelineLucideIcon name="redo" :stroke-width="1.8" />
      </button>
      <button
        type="button"
        class="iconbtn sm primary"
        :disabled="note.deletedAt || !activeCount"
        title="新增子节点（先选中节点）"
        @click="editor?.addChild()"
      >
        <TimelineLucideIcon name="plusSign" :stroke-width="1.8" />
      </button>

      <span class="mm-sep"></span>

      <div class="mm-ctl">
        <button
          type="button"
          class="iconbtn sm mm-layout-btn"
          :class="{ on: openMenu === 'layout' }"
          :disabled="note.deletedAt"
          :title="`布局：${currentLayoutLabel()}`"
          @click.stop="toggleMenu('layout')"
        >
          <TimelineLucideIcon name="layout" :stroke-width="1.8" />
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
        <button
          type="button"
          class="iconbtn sm mm-layout-btn"
          :class="{ on: openMenu === 'edge' }"
          :disabled="note.deletedAt"
          :title="`连线样式：${currentEdgeStyleLabel()}`"
          @click.stop="toggleMenu('edge')"
        >
          <TimelineLucideIcon name="timeline" :stroke-width="1.8" />
          <TimelineLucideIcon name="chevronDown" :stroke-width="1.8" />
        </button>
        <div v-if="openMenu === 'edge'" class="mm-menu">
          <button
            v-for="item in MINDMAP_EDGE_STYLES"
            :key="item.key"
            type="button"
            class="mm-menu-item"
            :class="{ on: item.key === currentEdgeStyle }"
            @click="pickEdgeStyle(item.key)"
          >
            <span>{{ item.label }}</span>
            <TimelineLucideIcon v-if="item.key === currentEdgeStyle" name="check" :stroke-width="2" />
          </button>
        </div>
      </div>

      <div class="mm-ctl">
        <button type="button" class="iconbtn sm" :class="{ on: openMenu === 'bg' }" :disabled="note.deletedAt" title="画布背景" @click.stop="toggleMenu('bg')">
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

      <div class="mm-ctl">
        <button type="button" class="iconbtn sm" :class="{ on: openMenu === 'bridge' }" title="导入 / 导出" @click.stop="toggleMenu('bridge')">
          <TimelineLucideIcon name="file" :stroke-width="1.8" />
        </button>
        <div v-if="openMenu === 'bridge'" class="mm-menu">
          <button type="button" class="mm-menu-item" @click="exportFile('json')">
            <span>导出 X6 JSON</span>
            <TimelineLucideIcon name="download" :stroke-width="1.8" />
          </button>
          <button type="button" class="mm-menu-item" @click="exportFile('md')">
            <span>导出 Markdown</span>
            <TimelineLucideIcon name="download" :stroke-width="1.8" />
          </button>
          <button v-if="!note.deletedAt" type="button" class="mm-menu-item" @click="triggerImport('json')">
            <span>导入 X6 JSON</span>
            <TimelineLucideIcon name="file" :stroke-width="1.8" />
          </button>
          <button v-if="!note.deletedAt" type="button" class="mm-menu-item" @click="triggerImport('markdown')">
            <span>导入 Markdown</span>
            <TimelineLucideIcon name="note" :stroke-width="1.8" />
          </button>
        </div>
      </div>

      <span class="mm-sep"></span>

      <button type="button" class="iconbtn sm" :disabled="note.deletedAt || !activeCount" title="缩小字号（先选中节点）" @click="editor?.nudgeFontSize(-2)">
        <TimelineLucideIcon name="fontDown" :stroke-width="1.8" />
      </button>
      <button type="button" class="iconbtn sm" :disabled="note.deletedAt || !activeCount" title="放大字号（先选中节点）" @click="editor?.nudgeFontSize(2)">
        <TimelineLucideIcon name="fontUp" :stroke-width="1.8" />
      </button>
      <button type="button" class="iconbtn sm" :disabled="note.deletedAt || !activeCount" title="加粗（先选中节点）" @click="editor?.toggleBold()">
        <TimelineLucideIcon name="bold" :stroke-width="1.8" />
      </button>
      <div class="mm-ctl">
        <button
          type="button"
          class="iconbtn sm"
          :class="{ on: openMenu === 'color' }"
          :disabled="note.deletedAt || !activeCount"
          title="文字颜色（先选中节点）"
          @click.stop="toggleMenu('color')"
        >
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

      <span v-if="note.deletedAt" class="mm-hint">回收站中的导图为只读，可恢复或永久删除</span>
      <span v-else-if="!activeCount" class="mm-hint">选中节点后可调字号与颜色</span>
    </div>

    <div v-if="openMenu" class="mm-scrim" @click="openMenu = ''"></div>

    <input ref="jsonInputRef" type="file" accept=".json,application/json,text/json" hidden @change="onJsonImport" />
    <input ref="markdownInputRef" type="file" accept=".md,.markdown,.txt,text/markdown,text/plain" hidden @change="onMarkdownImport" />

    <MindmapEditor
      ref="editor"
      :key="note.id"
      :note-id="note.id"
      :tree="note.bodyJson"
      :title="note.headline"
      :read-only="Boolean(note.deletedAt)"
      @ready="onReady"
      @active="activeCount = $event"
      @update="emit('save', $event)"
    />
  </section>
</template>
