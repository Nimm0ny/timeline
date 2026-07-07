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

const emit = defineEmits(["open-drawer", "update:searchQuery", "update:searchOpen", "create-event", "create-mindmap", "create-canvas"]);

const searchInputRef = ref(null);
const createMenuOpen = ref(false);

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

function toggleCreateMenu() {
  createMenuOpen.value = !createMenuOpen.value;
}

function pickNoteType(type) {
  createMenuOpen.value = false;
  emit(type === "mindmap" ? "create-mindmap" : type === "canvas" ? "create-canvas" : "create-event");
}

watch(
  () => props.searchOpen,
  (open) => {
    if (open) nextTick(() => searchInputRef.value?.focus());
    if (open) createMenuOpen.value = false;
  }
);
</script>

<template>
  <header class="mobile-topbar">
    <button type="button" class="iconbtn mobile-topbar-btn" title="打开导航" @click="emit('open-drawer')">
      <TimelineLucideIcon name="menu" :stroke-width="1.5" />
    </button>

    <label v-if="props.searchOpen" class="mobile-topbar-search">
      <TimelineLucideIcon name="search" :stroke-width="1.5" />
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
      <TimelineLucideIcon name="search" :stroke-width="1.5" />
    </button>
    <div class="mobile-topbar-create">
      <button type="button" class="iconbtn mobile-topbar-btn primary" :class="{ on: createMenuOpen }" title="新建笔记" @click="toggleCreateMenu">
        <TimelineLucideIcon name="plusCircle" :stroke-width="1.5" />
      </button>
      <div v-if="createMenuOpen" class="mobile-topbar-create-backdrop" @click="createMenuOpen = false"></div>
      <div v-if="createMenuOpen" class="popover tl-pop-newtype mobile-topbar-create-menu" @click.stop>
        <div class="pop-title">新建</div>
        <button type="button" class="pop-item" @click="pickNoteType('entry')">
          <TimelineLucideIcon class="pop-item-ic" name="note" :stroke-width="1.5" />
          <span class="pop-item-label">条目</span>
        </button>
        <button type="button" class="pop-item" @click="pickNoteType('mindmap')">
          <TimelineLucideIcon class="pop-item-ic" name="mindmap" :stroke-width="1.5" />
          <span class="pop-item-label">思维导图</span>
        </button>
        <button type="button" class="pop-item" @click="pickNoteType('canvas')">
          <TimelineLucideIcon class="pop-item-ic" name="canvas" :stroke-width="1.5" />
          <span class="pop-item-label">画布</span>
        </button>
      </div>
    </div>
  </header>
</template>
