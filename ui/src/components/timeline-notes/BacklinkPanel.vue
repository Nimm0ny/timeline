<script setup>
import { computed, ref, watch } from "vue";
import { api } from "@/composables/useApi";
import TimelineLucideIcon from "@/components/timeline-notes/TimelineLucideIcon.vue";

// W4 反向链接面板：列出指向当前笔记的 incoming [[wikilink]]。折叠区默认收起，
// 首次展开才拉取（api.getBacklinks，lazy）。悬停/点击本组件只 emit，不自持弹层——
// 由 EventDetailPane 转发到页面既有「关联预览」机制（定位 + 跨笔记本打开都归页面所有）。
const props = defineProps({
  eventId: {
    type: [Number, String],
    default: null,
  },
});

const emit = defineEmits(["open", "preview", "hide-preview"]);

const PAGE_SIZE = 50;

const expanded = ref(false);
const loading = ref(false);
const loaded = ref(false);
const errorText = ref("");
const items = ref([]);
const total = ref(0);

// Invalidate any in-flight request when the note changes so a slow response for
// the previous note can never overwrite the current list.
let requestSeq = 0;

const hasMore = computed(() => items.value.length < total.value);

async function fetchPage({ append = false } = {}) {
  if (!props.eventId) return;
  const seq = ++requestSeq;
  loading.value = true;
  if (!append) errorText.value = "";
  try {
    const offset = append ? items.value.length : 0;
    const result = await api.getBacklinks(props.eventId, { limit: PAGE_SIZE, offset });
    if (seq !== requestSeq) return;
    const rows = Array.isArray(result?.items) ? result.items : [];
    items.value = append ? [...items.value, ...rows] : rows;
    total.value = Number(result?.total) || 0;
    loaded.value = true;
  } catch (error) {
    if (seq !== requestSeq) return;
    errorText.value = `反向链接加载失败：${error.message || "未知错误"}`;
  } finally {
    if (seq === requestSeq) loading.value = false;
  }
}

function toggle() {
  expanded.value = !expanded.value;
  if (expanded.value && !loaded.value && !loading.value) {
    fetchPage({ append: false });
  }
}

function loadMore() {
  if (loading.value || !hasMore.value) return;
  fetchPage({ append: true });
}

function reset() {
  requestSeq += 1;
  expanded.value = false;
  loading.value = false;
  loaded.value = false;
  errorText.value = "";
  items.value = [];
  total.value = 0;
}

// Anchor rect mirrors EventDetailPane.relatedAnchorPayload so the forwarded preview
// pins next to the hovered row exactly like a 关联事件 row does.
function anchorFromEvent(event) {
  const rect = event?.currentTarget?.getBoundingClientRect?.();
  if (!rect) return null;
  return {
    top: rect.top,
    right: rect.right,
    bottom: rect.bottom,
    left: rect.left,
    width: rect.width,
    height: rect.height,
  };
}

function onRowEnter(item, event) {
  emit("preview", { sourceId: item.sourceId, anchor: anchorFromEvent(event) });
}

function onRowLeave(item) {
  emit("hide-preview", item.sourceId);
}

function onRowClick(item, event) {
  emit("open", { sourceId: item.sourceId, topicId: item.topicId, anchor: anchorFromEvent(event) });
}

watch(() => props.eventId, reset);
</script>

<template>
  <div class="pane-sec backlink-sec">
    <button
      type="button"
      class="pane-sec-head backlink-head"
      :aria-expanded="expanded"
      @click="toggle"
    >
      <span class="backlink-chev">
        <TimelineLucideIcon :name="expanded ? 'chevronDown' : 'chevronRight'" :stroke-width="1.5" />
      </span>
      <h3>反向链接</h3>
      <span v-if="loaded" class="backlink-count">{{ total }}</span>
    </button>

    <div v-if="expanded" class="backlink-body">
      <div v-if="loading && !items.length" class="backlink-state">正在加载反向链接…</div>
      <div v-else-if="errorText" class="backlink-state">{{ errorText }}</div>
      <div v-else-if="!items.length" class="backlink-state">暂无反向链接</div>
      <template v-else>
        <div class="row-list">
          <button
            v-for="item in items"
            :key="item.sourceId"
            type="button"
            class="lrow backlink-row"
            @mouseenter="onRowEnter(item, $event)"
            @mouseleave="onRowLeave(item)"
            @focus="onRowEnter(item, $event)"
            @blur="onRowLeave(item)"
            @click="onRowClick(item, $event)"
          >
            <span class="lrow-ic"><TimelineLucideIcon name="link" :stroke-width="1.5" /></span>
            <div class="lrow-main">
              <b>{{ item.headline || "未命名事件" }}</b>
              <span v-if="item.contextText" class="backlink-snippet">{{ item.contextText }}</span>
            </div>
            <span v-if="item.container" class="backlink-chip">{{ item.container }}</span>
          </button>
        </div>
        <button
          v-if="hasMore"
          type="button"
          class="backlink-more"
          :disabled="loading"
          @click="loadMore"
        >
          {{ loading ? "加载中…" : "加载更多" }}
        </button>
      </template>
    </div>
  </div>
</template>
