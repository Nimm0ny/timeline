<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import AppearanceSettings from "@/components/settings/AppearanceSettings.vue";
import TimelineLucideIcon from "@/components/timeline-notes/TimelineLucideIcon.vue";

const props = defineProps({
  open: { type: Boolean, default: false },
  brandName: { type: String, default: "编年" },
  mediaConfig: { type: Object, default: () => ({}) },
  navPosition: { type: String, default: "left" },
  activeTopicTitle: { type: String, default: "" },
  hasTopic: { type: Boolean, default: false },
});

const emit = defineEmits(["close", "export-data", "update-media", "update-nav-position"]);

const section = ref("appearance");

const NAV = [
  { id: "general", label: "常规", icon: "settings" },
  { id: "appearance", label: "外观", icon: "sliders" },
  { id: "media", label: "媒体", icon: "image" },
  { id: "data", label: "数据", icon: "download" },
  { id: "about", label: "关于", icon: "help" },
];

const media = computed(() => ({
  compress: props.mediaConfig?.compress !== false,
  keepOriginal: props.mediaConfig?.keepOriginal === true,
  quality: Math.min(100, Math.max(1, Number.parseInt(props.mediaConfig?.quality, 10) || 80)),
  maxEdge: Math.min(8192, Math.max(320, Number.parseInt(props.mediaConfig?.maxEdge, 10) || 1920)),
  thumbEdge: Math.min(2048, Math.max(96, Number.parseInt(props.mediaConfig?.thumbEdge, 10) || 400)),
}));

function updateMedia(patch) {
  emit("update-media", { ...media.value, ...patch });
}

function onKeydown(event) {
  if (event.key === "Escape" && props.open) emit("close");
}

onMounted(() => {
  document.addEventListener("keydown", onKeydown);
});

onBeforeUnmount(() => {
  document.removeEventListener("keydown", onKeydown);
});
</script>

<template>
  <div v-if="props.open" class="settings-shell" @click="emit('close')">
    <div class="settings-panel" role="dialog" aria-modal="true" aria-label="设置" @click.stop>
      <div class="settings-nav">
      <div class="settings-nav-head">
        <span class="settings-nav-title">设置</span>
        <button type="button" class="iconbtn" title="关闭设置" @click="emit('close')">
          <TimelineLucideIcon name="close" :stroke-width="1.5" />
        </button>
      </div>
      <button
        v-for="item in NAV"
        :key="item.id"
        type="button"
        class="settings-nav-item"
        :class="{ active: section === item.id }"
        @click="section = item.id"
      >
        <TimelineLucideIcon :name="item.icon" :stroke-width="1.5" />
        <span>{{ item.label }}</span>
      </button>
      </div>

      <div class="settings-content scroll">
      <section v-if="section === 'general'" class="settings-pane">
        <h3 class="settings-title">常规</h3>
        <div class="settings-row">
          <span class="settings-row-label">品牌名</span>
          <span class="settings-row-control"><strong>{{ props.brandName }}</strong></span>
        </div>
        <div class="settings-row">
          <span class="settings-row-label">当前笔记本</span>
          <span class="settings-row-control"><strong>{{ props.activeTopicTitle || "—" }}</strong></span>
        </div>
        <p class="settings-note">本地优先 / 开源：无需登录，所有改动即时生效。</p>
      </section>

      <section v-else-if="section === 'appearance'" class="settings-pane">
        <h3 class="settings-title">外观</h3>
        <div class="settings-section">
          <h4 class="settings-h">布局</h4>
          <div class="settings-row">
            <span class="settings-row-label">功能栏位置</span>
            <span class="settings-row-control">
              <span class="settings-seg" role="group" aria-label="功能栏位置">
                <button
                  type="button"
                  class="settings-seg-btn"
                  :class="{ active: props.navPosition !== 'right' }"
                  @click="emit('update-nav-position', 'left')"
                >
                  靠左
                </button>
                <button
                  type="button"
                  class="settings-seg-btn"
                  :class="{ active: props.navPosition === 'right' }"
                  @click="emit('update-nav-position', 'right')"
                >
                  靠右
                </button>
              </span>
            </span>
          </div>
          <p class="settings-note">功能栏贴左或贴右外缘；列表居中，详情在对侧弹出。仅桌面端。</p>
        </div>
        <AppearanceSettings />
      </section>

      <section v-else-if="section === 'media'" class="settings-pane">
        <h3 class="settings-title">媒体 / 存储</h3>
        <div class="settings-section">
          <h4 class="settings-h">上传处理</h4>
          <div class="settings-row">
            <span class="settings-row-label">压缩图片</span>
            <span class="settings-row-control">
              <input
                type="checkbox"
                :checked="media.compress"
                @change="updateMedia({ compress: $event.target.checked })"
              />
            </span>
          </div>
          <div class="settings-row">
            <span class="settings-row-label">保留原图</span>
            <span class="settings-row-control">
              <input
                type="checkbox"
                :checked="media.keepOriginal"
                @change="updateMedia({ keepOriginal: $event.target.checked })"
              />
            </span>
          </div>
          <div class="settings-row">
            <span class="settings-row-label">WebP 质量</span>
            <span class="settings-row-control range">
              <input
                type="range"
                min="1"
                max="100"
                :value="media.quality"
                @change="updateMedia({ quality: Number.parseInt($event.target.value, 10) })"
              />
              <span class="range-val">{{ media.quality }}</span>
            </span>
          </div>
          <p class="settings-note">默认压缩为 WebP 并生成缩略图；GIF 与 SVG 保留原文件。</p>
        </div>
      </section>

      <section v-else-if="section === 'data'" class="settings-pane">
        <h3 class="settings-title">数据</h3>
        <div class="settings-section">
          <h4 class="settings-h">导出</h4>
          <div class="settings-actions">
            <button type="button" class="settings-btn primary" :disabled="!props.hasTopic" @click="emit('export-data')">
              导出当前笔记本
            </button>
          </div>
          <p class="settings-note">导出为 schemaVersion 2 结构化 JSON（含属性与选项）。</p>
        </div>
      </section>

      <section v-else class="settings-pane">
        <h3 class="settings-title">关于</h3>
        <div class="settings-row">
          <span class="settings-row-label">产品</span>
          <span class="settings-row-control"><strong>编年 Chronicle</strong></span>
        </div>
        <p class="settings-note">以时间线为核心的极简笔记。Vue 3 + FastAPI + SQLite。</p>
      </section>
      </div>
    </div>
  </div>
</template>
