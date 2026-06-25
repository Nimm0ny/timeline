<script setup>
import { computed, ref } from "vue";
import ColorField from "@/components/settings/ColorField.vue";
import { pushToast } from "@/composables/useToast";
import {
  applyPreset,
  exportThemeJson,
  getCustomMarkdown,
  importThemeJson,
  setCustomMarkdown,
  updateThemeConfig,
  useThemeStore,
} from "@/composables/useTheme";
import { FONT_OPTIONS, MARKDOWN_OPTIONS, PRESETS } from "@/constants/theme";

const store = useThemeStore();

function knob(key) {
  return computed({
    get: () => store.config[key],
    set: (value) => updateThemeConfig({ [key]: value }),
  });
}

const accent = knob("accent");
const background = knob("background");
const foreground = knob("foreground");
const contrast = knob("contrast");
const uiFont = knob("uiFont");
const markdown = knob("markdown");

const customCss = ref(getCustomMarkdown());
const themeJson = ref("");

function selectPreset(mode) {
  applyPreset(mode);
}

function applyCustomMarkdown() {
  setCustomMarkdown(customCss.value);
  pushToast("已应用自定义 Markdown 样式");
}

function doExport() {
  themeJson.value = exportThemeJson();
  pushToast("主题已导出到下方文本框");
}

function doImport() {
  try {
    importThemeJson(themeJson.value);
    pushToast("主题已导入");
  } catch (error) {
    pushToast(error.message, "error");
  }
}
</script>

<template>
  <div class="appearance">
    <div class="settings-section">
      <h4 class="settings-h">预设</h4>
      <div class="preset-cards">
        <button
          v-for="preset in PRESETS"
          :key="preset.id"
          type="button"
          class="preset-card"
          :class="{ active: store.config.mode === preset.id }"
          @click="selectPreset(preset.id)"
        >
          <span class="preset-swatch" :data-mode="preset.id"></span>
          <span class="preset-name">{{ preset.label }}</span>
          <span class="preset-hint">{{ preset.hint }}</span>
        </button>
      </div>
    </div>

    <div class="settings-section">
      <h4 class="settings-h">主题编辑</h4>
      <ColorField label="强调色" v-model="accent" />
      <ColorField label="背景" v-model="background" />
      <ColorField label="前景文字" v-model="foreground" />
      <label class="settings-row">
        <span class="settings-row-label">对比度</span>
        <span class="settings-row-control range">
          <input type="range" min="40" max="100" step="1" :value="contrast" @input="contrast = Number($event.target.value)" />
          <span class="range-val">{{ contrast }}</span>
        </span>
      </label>
      <label class="settings-row">
        <span class="settings-row-label">界面字体</span>
        <span class="settings-row-control">
          <select :value="uiFont" @change="uiFont = $event.target.value">
            <option v-for="font in FONT_OPTIONS" :key="font.value" :value="font.value">{{ font.label }}</option>
          </select>
        </span>
      </label>
    </div>

    <div class="settings-section">
      <h4 class="settings-h">Markdown 样式</h4>
      <label class="settings-row">
        <span class="settings-row-label">渲染样式</span>
        <span class="settings-row-control">
          <select :value="markdown" @change="markdown = $event.target.value">
            <option v-for="option in MARKDOWN_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
          </select>
        </span>
      </label>
      <div v-if="markdown === 'custom'" class="settings-stack">
        <textarea
          v-model="customCss"
          class="settings-textarea"
          rows="6"
          spellcheck="false"
          placeholder="粘贴针对 .markdown-body 或 Typora #write 的 CSS"
        ></textarea>
        <div class="settings-actions">
          <button type="button" class="settings-btn primary" @click="applyCustomMarkdown">应用样式</button>
        </div>
      </div>
    </div>

    <div class="settings-section">
      <h4 class="settings-h">导入 / 导出主题</h4>
      <textarea v-model="themeJson" class="settings-textarea" rows="5" spellcheck="false" placeholder='主题 JSON，例如 {"mode":"dark","accent":"#8c7ae6"}'></textarea>
      <div class="settings-actions">
        <button type="button" class="settings-btn" @click="doExport">导出当前</button>
        <button type="button" class="settings-btn primary" @click="doImport">导入</button>
      </div>
    </div>
  </div>
</template>
