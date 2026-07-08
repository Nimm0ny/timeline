<script setup>
import { nextTick, ref, watch } from "vue";
import BaseModal from "@/components/BaseModal.vue";
import HighlightedText from "@/components/timeline-notes/HighlightedText.vue";
import LucideIcon from "@/components/timeline-notes/LucideIcon.vue";
import { api } from "@/composables/useApi";

// W5 note-embed: search notes and pick one to drop onto the canvas as an embed card.
// Mirrors CommandPalette's search-field + result-list layout, keyboard model and kebab
// classes; it just talks straight to api.search and emits a lean { id, headline } for
// the page to turn into a buildEmbedCardNode. Presentation only — no canvas knowledge.
const props = defineProps({
  open: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["select", "close"]);

const inputRef = ref(null);
const query = ref("");
const results = ref([]);
const loading = ref(false);
const error = ref("");
const activeIndex = ref(0);

// Monotonic guard: an out-of-order slow response for a stale query is dropped.
let searchSeq = 0;
let debounceTimer = null;

function clearDebounce() {
  if (debounceTimer) {
    clearTimeout(debounceTimer);
    debounceTimer = null;
  }
}

function reset() {
  clearDebounce();
  query.value = "";
  results.value = [];
  error.value = "";
  loading.value = false;
  activeIndex.value = 0;
}

function close() {
  emit("close");
}

async function runSearch(term) {
  const trimmed = String(term || "").trim();
  const seq = (searchSeq += 1);
  if (!trimmed) {
    results.value = [];
    error.value = "";
    loading.value = false;
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    const rows = await api.search(trimmed, { limit: 20 });
    if (seq !== searchSeq) return;
    results.value = Array.isArray(rows) ? rows : [];
    activeIndex.value = 0;
  } catch (err) {
    if (seq !== searchSeq) return;
    results.value = [];
    error.value = err?.message || "搜索失败";
  } finally {
    if (seq === searchSeq) loading.value = false;
  }
}

function onInput(event) {
  query.value = event.target.value;
  clearDebounce();
  debounceTimer = setTimeout(() => runSearch(query.value), 180);
}

function moveActive(delta) {
  const count = results.value.length;
  if (!count) return;
  activeIndex.value = (activeIndex.value + delta + count) % count;
}

function pick(result = results.value[activeIndex.value]) {
  if (!result) return;
  emit("select", { id: result.id, headline: (result.headline || "").trim() });
}

function onKeydown(event) {
  if (event.key === "ArrowDown") {
    event.preventDefault();
    moveActive(1);
    return;
  }
  if (event.key === "ArrowUp") {
    event.preventDefault();
    moveActive(-1);
    return;
  }
  if (event.key === "Enter") {
    event.preventDefault();
    pick();
    return;
  }
  if (event.key === "Escape") {
    event.preventDefault();
    close();
  }
}

watch(
  () => props.open,
  (open) => {
    if (open) {
      reset();
      nextTick(() => inputRef.value?.focus());
    } else {
      // Invalidate any in-flight request so a late response can't repopulate a closed picker.
      searchSeq += 1;
      clearDebounce();
    }
  }
);
</script>

<template>
  <BaseModal
    :model-value="props.open"
    title="嵌入笔记"
    wide
    hide-header
    aria-label="嵌入笔记"
    card-class="command-palette-card"
    body-class="command-palette-body"
    @update:model-value="close"
  >
    <section class="command-palette embed-card-picker" @keydown="onKeydown">
      <label class="command-search-field">
        <LucideIcon name="search" :stroke-width="1.5" />
        <input
          ref="inputRef"
          :value="query"
          type="search"
          placeholder="搜索要嵌入的笔记"
          @input="onInput"
        />
        <span v-if="loading" class="command-search-state">搜索中</span>
      </label>

      <div class="command-results" role="listbox" aria-label="笔记搜索结果">
        <p v-if="error" class="command-message">{{ error }}</p>
        <p v-else-if="!query.trim()" class="command-message">输入关键词搜索要嵌入的笔记</p>
        <p v-else-if="!loading && !results.length" class="command-message">未找到匹配的笔记</p>

        <template v-if="results.length">
          <div class="command-section-label">笔记</div>
          <button
            v-for="(result, index) in results"
            :key="result.id"
            type="button"
            class="command-result-row"
            :class="{ active: index === activeIndex }"
            role="option"
            :aria-selected="index === activeIndex"
            @mouseenter="activeIndex = index"
            @click="pick(result)"
          >
            <span class="command-row-main">
              <span class="command-row-title"><HighlightedText :text="result.headline || '无标题'" :query="query" /></span>
              <span class="command-row-sub"><HighlightedText :text="result.snippet || '—'" :query="query" /></span>
            </span>
            <span class="command-row-meta">
              <span class="command-date">{{ result.isoDate || result.dateKey || "未定时间" }}</span>
            </span>
          </button>
        </template>
      </div>
    </section>
  </BaseModal>
</template>
