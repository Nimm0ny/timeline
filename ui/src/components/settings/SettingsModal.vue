<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue";
import AppearanceSettings from "@/components/settings/AppearanceSettings.vue";
import TimelineLucideIcon from "@/components/timeline-notes/TimelineLucideIcon.vue";

const props = defineProps({
  open: { type: Boolean, default: false },
  brandName: { type: String, default: "编年" },
  activeTopicTitle: { type: String, default: "" },
  hasTopic: { type: Boolean, default: false },
});

const emit = defineEmits(["close", "export-data"]);

const section = ref("appearance");

const NAV = [
  { id: "general", label: "常规", icon: "settings" },
  { id: "appearance", label: "外观", icon: "sliders" },
  { id: "data", label: "数据", icon: "download" },
  { id: "about", label: "关于", icon: "help" },
];

function onKeydown(event) {
  if (event.key === "Escape" && props.open) emit("close");
}

onMounted(() => document.addEventListener("keydown", onKeydown));
onBeforeUnmount(() => document.removeEventListener("keydown", onKeydown));
</script>

<template>
  <div v-if="props.open" class="settings-shell" role="dialog" aria-modal="true" aria-label="设置">
    <div class="settings-nav">
      <div class="settings-nav-head">
        <span class="settings-nav-title">设置</span>
        <button type="button" class="iconbtn" title="关闭设置" @click="emit('close')">
          <TimelineLucideIcon name="close" :stroke-width="1.8" />
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
        <TimelineLucideIcon :name="item.icon" :stroke-width="1.8" />
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
        <AppearanceSettings />
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
</template>
