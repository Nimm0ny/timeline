<script setup>
import { nextTick, reactive, ref } from "vue";
import MindmapEditor from "@/components/notes/MindmapEditor.vue";
import LucideIcon from "@/components/notes/LucideIcon.vue";
import { pushToast } from "@/composables/useToast";
import {
  DEFAULT_EDGE_STYLE,
  MINDMAP_EDGE_STYLES,
  MINDMAP_NODE_ICONS,
  normalizeTags,
  parseTagInput,
} from "@/utils/mindmapX6.js";
import { DEFAULT_MINDMAP_LAYOUT, MINDMAP_LAYOUTS } from "@/utils/noteUtils.js";

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
const openMenu = ref(""); // "" | "layout" | "edge" | "bg" | "color" | "bridge" | "meta"
const activeCount = ref(0);
// Node info panel form for the single selected node (populated on open from the
// editor's getActiveNodeMeta; edits write straight back through the editor).
const metaForm = reactive({ id: null, link: "", note: "", tags: [], icon: "" });
const tagDraft = ref("");
const metaLinkRef = ref(null);
const currentLayout = ref(DEFAULT_MINDMAP_LAYOUT);
const currentBackground = ref("");
const currentEdgeStyle = ref(DEFAULT_EDGE_STYLE);
const markdownInputRef = ref(null);
const jsonInputRef = ref(null);
const searchOpen = ref(false);
const searchQuery = ref("");
const searchInfo = ref({ count: 0, index: 0 });
const searchInputRef = ref(null);

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

// ---- Node info panel (hyperlink / note / tags / icon) ----
function openMeta() {
  const meta = editor.value?.getActiveNodeMeta?.();
  if (!meta) return;
  metaForm.id = meta.id;
  metaForm.link = meta.hyperlink;
  metaForm.note = meta.note;
  metaForm.tags = [...meta.tags];
  metaForm.icon = meta.icon;
  tagDraft.value = "";
  openMenu.value = "meta";
  nextTick(() => metaLinkRef.value?.focus());
}

function toggleMeta() {
  if (openMenu.value === "meta") openMenu.value = "";
  else openMeta();
}

function applyMetaLink() {
  editor.value?.setNodeHyperlink?.(metaForm.link);
}

function applyMetaNote() {
  editor.value?.setNodeNote?.(metaForm.note);
}

function commitTagDraft() {
  const parsed = parseTagInput(tagDraft.value);
  tagDraft.value = "";
  if (!parsed.length) return;
  metaForm.tags = normalizeTags([...metaForm.tags, ...parsed]);
  editor.value?.setNodeTags?.(metaForm.tags);
}

function removeTag(tag) {
  metaForm.tags = metaForm.tags.filter((item) => item !== tag);
  editor.value?.setNodeTags?.(metaForm.tags);
}

function onTagKeydown(event) {
  if (event.key === "Enter" || event.key === ",") {
    event.preventDefault();
    commitTagDraft();
  } else if (event.key === "Backspace" && !tagDraft.value && metaForm.tags.length) {
    removeTag(metaForm.tags[metaForm.tags.length - 1]);
  }
}

function pickIcon(key) {
  metaForm.icon = metaForm.icon === key ? "" : key;
  editor.value?.setNodeIcon?.(metaForm.icon);
}

// Keep the node info panel bound to the node it opened for: the editor reports the
// single-node selection (or null) on every selection change, and we close the panel
// the moment that target differs from the one we opened for. Combined with the setters
// targeting the live single selection, an edit can never land on a different node.
function onMeta(meta) {
  if (openMenu.value !== "meta") return;
  if (!meta || meta.id !== metaForm.id) openMenu.value = "";
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

function toggleSearch() {
  openMenu.value = "";
  searchOpen.value = !searchOpen.value;
  if (searchOpen.value) {
    nextTick(() => searchInputRef.value?.focus());
  } else {
    closeSearch();
  }
}

function runSearch() {
  searchInfo.value = editor.value?.searchNodes?.(searchQuery.value) || { count: 0, index: 0 };
}

function stepSearch(direction) {
  if (!searchInfo.value.count) {
    runSearch();
    return;
  }
  searchInfo.value = editor.value?.stepMatch?.(direction) || searchInfo.value;
}

function closeSearch() {
  searchOpen.value = false;
  searchQuery.value = "";
  searchInfo.value = { count: 0, index: 0 };
  editor.value?.clearSearch?.();
}

defineExpose({ pauseAutosave, resumeAutosave, flushAutosave });
</script>

<template>
  <section class="col mm-surface" :class="{ 'is-fullscreen': fullscreen }">
    <header class="mm-bar">
      <button type="button" class="iconbtn lg" title="返回列表" @click="emit('back')">
        <LucideIcon name="arrowLeft" :stroke-width="1.5" />
      </button>
      <div class="mm-head">
        <LucideIcon name="mindmap" :stroke-width="1.5" />
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
        <LucideIcon name="star" :stroke-width="1.5" />
      </button>
      <button v-if="!note.deletedAt" type="button" class="iconbtn lg" title="移入回收站" @click="requestTrash">
        <LucideIcon name="trash" :stroke-width="1.5" />
      </button>
      <button v-else type="button" class="iconbtn lg" title="恢复" @click="emit('restore', note)">
        <LucideIcon name="restore" :stroke-width="1.5" />
      </button>
      <button v-if="note.deletedAt" type="button" class="iconbtn lg" title="永久删除" @click="requestPermanentDelete">
        <LucideIcon name="trash" :stroke-width="1.5" />
      </button>
      <span class="mm-status">{{ note.deletedAt ? "回收站 · 只读" : saving ? "保存中…" : "已保存" }}</span>
      <span class="spacer"></span>
      <button type="button" class="iconbtn lg" :title="fullscreen ? '退出全屏' : '全屏'" @click="toggleFullscreen">
        <LucideIcon :name="fullscreen ? 'minimize' : 'maximize'" :stroke-width="1.5" />
      </button>
    </header>

    <div class="mm-tools">
      <button type="button" class="iconbtn sm" :disabled="note.deletedAt" title="撤销" @click="editor?.undo()">
        <LucideIcon name="undo" :stroke-width="1.5" />
      </button>
      <button type="button" class="iconbtn sm" :disabled="note.deletedAt" title="重做" @click="editor?.redo()">
        <LucideIcon name="redo" :stroke-width="1.5" />
      </button>
      <button
        type="button"
        class="iconbtn sm primary"
        :disabled="note.deletedAt || !activeCount"
        title="新增子节点（先选中节点）"
        @click="editor?.addChild()"
      >
        <LucideIcon name="plusSign" :stroke-width="1.5" />
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
          <LucideIcon name="layout" :stroke-width="1.5" />
          <LucideIcon name="chevronDown" :stroke-width="1.5" />
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
            <LucideIcon v-if="item.key === currentLayout" name="check" :stroke-width="2" />
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
          <LucideIcon name="timeline" :stroke-width="1.5" />
          <LucideIcon name="chevronDown" :stroke-width="1.5" />
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
            <LucideIcon v-if="item.key === currentEdgeStyle" name="check" :stroke-width="2" />
          </button>
        </div>
      </div>

      <div class="mm-ctl">
        <button type="button" class="iconbtn sm" :class="{ on: openMenu === 'bg' }" :disabled="note.deletedAt" title="画布背景" @click.stop="toggleMenu('bg')">
          <LucideIcon name="paint" :stroke-width="1.5" />
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
          <LucideIcon name="file" :stroke-width="1.5" />
        </button>
        <div v-if="openMenu === 'bridge'" class="mm-menu">
          <button type="button" class="mm-menu-item" @click="exportFile('json')">
            <span>导出 X6 JSON</span>
            <LucideIcon name="download" :stroke-width="1.5" />
          </button>
          <button type="button" class="mm-menu-item" @click="exportFile('md')">
            <span>导出 Markdown</span>
            <LucideIcon name="download" :stroke-width="1.5" />
          </button>
          <button v-if="!note.deletedAt" type="button" class="mm-menu-item" @click="triggerImport('json')">
            <span>导入 X6 JSON</span>
            <LucideIcon name="file" :stroke-width="1.5" />
          </button>
          <button v-if="!note.deletedAt" type="button" class="mm-menu-item" @click="triggerImport('markdown')">
            <span>导入 Markdown</span>
            <LucideIcon name="note" :stroke-width="1.5" />
          </button>
        </div>
      </div>

      <span class="mm-sep"></span>

      <button type="button" class="iconbtn sm" :disabled="note.deletedAt || !activeCount" title="缩小字号（先选中节点）" @click="editor?.nudgeFontSize(-2)">
        <LucideIcon name="fontDown" :stroke-width="1.5" />
      </button>
      <button type="button" class="iconbtn sm" :disabled="note.deletedAt || !activeCount" title="放大字号（先选中节点）" @click="editor?.nudgeFontSize(2)">
        <LucideIcon name="fontUp" :stroke-width="1.5" />
      </button>
      <button type="button" class="iconbtn sm" :disabled="note.deletedAt || !activeCount" title="加粗（先选中节点）" @click="editor?.toggleBold()">
        <LucideIcon name="bold" :stroke-width="1.5" />
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
          <LucideIcon name="palette" :stroke-width="1.5" />
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

      <div class="mm-ctl">
        <button
          type="button"
          class="iconbtn sm"
          :class="{ on: openMenu === 'meta' }"
          :disabled="note.deletedAt || activeCount !== 1"
          title="节点信息：超链接 / 备注 / 标签 / 图标（先选中单个节点）"
          @click.stop="toggleMeta"
        >
          <LucideIcon name="info" :stroke-width="1.5" />
        </button>
        <div v-if="openMenu === 'meta'" class="mm-menu mm-meta-panel" @click.stop @keydown.esc.prevent="openMenu = ''">
          <label class="mm-meta-field">
            <span class="mm-meta-label"><LucideIcon name="link" :stroke-width="1.5" />超链接</span>
            <input
              ref="metaLinkRef"
              v-model="metaForm.link"
              class="mm-meta-input"
              type="text"
              placeholder="https://…"
              @change="applyMetaLink"
              @keydown.enter.prevent="applyMetaLink"
            />
          </label>
          <label class="mm-meta-field">
            <span class="mm-meta-label"><LucideIcon name="note" :stroke-width="1.5" />备注</span>
            <textarea
              v-model="metaForm.note"
              class="mm-meta-input mm-meta-textarea"
              rows="3"
              placeholder="给这个节点写点备注…"
              @input="applyMetaNote"
            ></textarea>
          </label>
          <div class="mm-meta-field">
            <span class="mm-meta-label"><LucideIcon name="tag" :stroke-width="1.5" />标签</span>
            <div class="mm-meta-tags">
              <span v-for="tag in metaForm.tags" :key="tag" class="mm-meta-chip">
                #{{ tag }}
                <button type="button" class="mm-meta-chip-x" title="移除标签" @click="removeTag(tag)">
                  <LucideIcon name="close" :stroke-width="1.5" />
                </button>
              </span>
              <input
                v-model="tagDraft"
                class="mm-meta-taginput"
                type="text"
                :placeholder="metaForm.tags.length ? '' : '回车或逗号添加'"
                @keydown="onTagKeydown"
                @blur="commitTagDraft"
              />
            </div>
          </div>
          <div class="mm-meta-field">
            <span class="mm-meta-label"><LucideIcon name="star" :stroke-width="1.5" />图标</span>
            <div class="mm-meta-icons">
              <button
                v-for="item in MINDMAP_NODE_ICONS"
                :key="item.key"
                type="button"
                class="mm-meta-icon"
                :class="{ on: metaForm.icon === item.key }"
                :title="item.label"
                @click="pickIcon(item.key)"
              >
                <LucideIcon :name="item.key" :stroke-width="1.5" />
              </button>
            </div>
          </div>
        </div>
      </div>

      <span v-if="note.deletedAt" class="mm-hint">回收站中的导图为只读，可恢复或永久删除</span>
      <span v-else-if="!activeCount" class="mm-hint">选中节点后可编辑样式与信息</span>

      <div class="mm-ctl mm-find">
        <button
          type="button"
          class="iconbtn sm"
          :class="{ on: searchOpen }"
          :disabled="note.deletedAt"
          title="搜索节点"
          @click.stop="toggleSearch"
        >
          <LucideIcon name="search" :stroke-width="1.5" />
        </button>
        <div v-if="searchOpen" class="mm-find-bar" @click.stop>
          <input
            ref="searchInputRef"
            v-model="searchQuery"
            class="mm-find-input"
            type="text"
            placeholder="搜索节点…"
            @input="runSearch"
            @keydown.enter.prevent="stepSearch(1)"
            @keydown.esc.prevent="closeSearch"
          />
          <span class="mm-find-count">{{ searchInfo.count ? `${searchInfo.index}/${searchInfo.count}` : (searchQuery ? "无匹配" : "") }}</span>
          <button type="button" class="iconbtn sm" title="上一个" :disabled="!searchInfo.count" @click="stepSearch(-1)">
            <LucideIcon name="chevronUp" :stroke-width="1.5" />
          </button>
          <button type="button" class="iconbtn sm" title="下一个" :disabled="!searchInfo.count" @click="stepSearch(1)">
            <LucideIcon name="chevronDown" :stroke-width="1.5" />
          </button>
          <button type="button" class="iconbtn sm" title="关闭搜索" @click="closeSearch">
            <LucideIcon name="close" :stroke-width="1.5" />
          </button>
        </div>
      </div>
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
      @search="searchInfo = $event"
      @meta="onMeta"
      @edit-meta="openMeta"
      @update="emit('save', $event)"
    />
  </section>
</template>
