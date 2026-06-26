<script setup>
import { nextTick, ref, watch } from "vue";
import TimelineLucideIcon from "@/components/timeline-notes/TimelineLucideIcon.vue";

const props = defineProps({
  title: {
    type: String,
    default: "编年",
  },
  count: {
    type: Number,
    default: 0,
  },
  searchQuery: {
    type: String,
    default: "",
  },
  searchOpen: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["open-drawer", "update:searchQuery", "update:searchOpen", "create-event"]);

const searchInputRef = ref(null);

function toggleSearch() {
  const next = !props.searchOpen;
  emit("update:searchOpen", next);
  if (next) {
    nextTick(() => searchInputRef.value?.focus());
  }
}

function closeSearchIfEmpty() {
  if (!String(props.searchQuery || "").trim()) {
    emit("update:searchOpen", false);
  }
}

watch(
  () => props.searchOpen,
  (open) => {
    if (open) nextTick(() => searchInputRef.value?.focus());
  }
);
</script>

<template>
  <header class="mobile-topbar">
    <button type="button" class="iconbtn mobile-topbar-btn" title="打开导航" @click="emit('open-drawer')">
      <TimelineLucideIcon name="menu" :stroke-width="1.8" />
    </button>

    <label v-if="props.searchOpen" class="mobile-topbar-search">
      <TimelineLucideIcon name="search" :stroke-width="1.8" />
      <input
        ref="searchInputRef"
        :value="props.searchQuery"
        type="search"
        placeholder="搜索当前时间线"
        @input="emit('update:searchQuery', $event.target.value)"
        @blur="closeSearchIfEmpty"
      />
    </label>
    <div v-else class="mobile-topbar-title">
      <b>{{ props.title }}</b>
      <span>· 共 {{ props.count }} 条</span>
    </div>

    <button type="button" class="iconbtn mobile-topbar-btn" :class="{ on: props.searchOpen }" title="搜索" @click="toggleSearch">
      <TimelineLucideIcon name="search" :stroke-width="1.8" />
    </button>
    <button type="button" class="iconbtn mobile-topbar-btn primary" title="新建时间点" @click="emit('create-event')">
      <TimelineLucideIcon name="plusCircle" :stroke-width="1.8" />
    </button>
  </header>
</template>
