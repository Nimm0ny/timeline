<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import LucideIcon from "@/components/timeline-notes/LucideIcon.vue";
import { OPTION_PALETTE } from "@/constants/tags";
import { buildOptionId } from "@/utils/timelineNotes";

// Unified picker for select / multiselect properties. The value lives by option
// id; new options are created with a palette color and bubbled to the parent so
// it can persist them onto the topic property (see spec §5.1).
const props = defineProps({
  column: {
    type: Object,
    required: true,
  },
  modelValue: {
    type: [String, Array],
    default: "",
  },
  placeholder: {
    type: String,
    default: "选择…",
  },
});

const emit = defineEmits(["update:modelValue", "create-option"]);

const open = ref(false);
const query = ref("");
const rootRef = ref(null);
const inputRef = ref(null);

const multiple = computed(() => props.column?.type === "multiselect");
const options = computed(() => props.column?.options || []);
const selectedIds = computed(() => {
  if (multiple.value) return Array.isArray(props.modelValue) ? props.modelValue : [];
  return props.modelValue ? [props.modelValue] : [];
});
const selectedChips = computed(() =>
  selectedIds.value.map((id) => options.value.find((option) => option.id === id) || { id, label: id, color: "var(--accent)" })
);
const filtered = computed(() => {
  const keyword = query.value.trim().toLowerCase();
  if (!keyword) return options.value;
  return options.value.filter(
    (option) => option.label.toLowerCase().includes(keyword) || option.id.toLowerCase().includes(keyword)
  );
});
const canCreate = computed(() => {
  const keyword = query.value.trim();
  return Boolean(keyword) && !options.value.some((option) => option.label.toLowerCase() === keyword.toLowerCase());
});

function isSelected(id) {
  return selectedIds.value.includes(id);
}

function toggle(id) {
  if (multiple.value) {
    const next = isSelected(id) ? selectedIds.value.filter((value) => value !== id) : [...selectedIds.value, id];
    emit("update:modelValue", next);
  } else {
    emit("update:modelValue", isSelected(id) ? "" : id);
    closePanel();
  }
}

function removeChip(id) {
  if (multiple.value) {
    emit("update:modelValue", selectedIds.value.filter((value) => value !== id));
  } else {
    emit("update:modelValue", "");
  }
}

function createOption() {
  const label = query.value.trim();
  if (!label || !canCreate.value) return;
  const id = buildOptionId(label, options.value.map((option) => option.id));
  const color = OPTION_PALETTE[options.value.length % OPTION_PALETTE.length];
  emit("create-option", { key: props.column.key, option: { id, label, color } });
  if (multiple.value) {
    emit("update:modelValue", [...selectedIds.value.filter((value) => value !== id), id]);
  } else {
    emit("update:modelValue", id);
    closePanel();
  }
  query.value = "";
}

function openPanel() {
  open.value = true;
  nextTick(() => inputRef.value?.focus());
}

function closePanel() {
  open.value = false;
  query.value = "";
}

function togglePanel() {
  if (open.value) closePanel();
  else openPanel();
}

function onDocumentPointer(event) {
  if (open.value && rootRef.value && !rootRef.value.contains(event.target)) closePanel();
}

function onKeydown(event) {
  if (event.key === "Escape" && open.value) closePanel();
}

onMounted(() => {
  document.addEventListener("pointerdown", onDocumentPointer);
  document.addEventListener("keydown", onKeydown);
});

onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", onDocumentPointer);
  document.removeEventListener("keydown", onKeydown);
});
</script>

<template>
  <div ref="rootRef" class="optpick" :class="{ open }">
    <button type="button" class="optpick-control" @click.stop="togglePanel">
      <template v-if="selectedChips.length">
        <span v-for="chip in selectedChips" :key="chip.id" class="ptag" :style="{ '--dot': chip.color }">
          <i></i>{{ chip.label }}
          <span class="ptag-x" title="移除" @click.stop="removeChip(chip.id)">
            <LucideIcon name="close" :stroke-width="1.5" />
          </span>
        </span>
      </template>
      <span v-else class="optpick-ph">{{ props.placeholder }}</span>
    </button>

    <div v-if="open" class="popover optpick-pop" @click.stop>
      <input
        ref="inputRef"
        v-model="query"
        class="optpick-search"
        type="text"
        placeholder="搜索或新建…"
        @keydown.enter.prevent="createOption"
      />
      <div class="optpick-list scroll">
        <button
          v-for="option in filtered"
          :key="option.id"
          type="button"
          class="optpick-opt"
          :class="{ on: isSelected(option.id) }"
          @click="toggle(option.id)"
        >
          <span class="opt-dot" :style="{ '--dot': option.color || 'var(--accent)' }"></span>
          <span class="opt-label">{{ option.label }}</span>
          <span v-if="isSelected(option.id)" class="opt-check">
            <LucideIcon name="check" :stroke-width="1.5" />
          </span>
        </button>
        <button v-if="canCreate" type="button" class="optpick-create" @click="createOption">
          <LucideIcon name="plusSign" :stroke-width="1.5" />
          <span>新建「{{ query.trim() }}」</span>
        </button>
        <p v-if="!filtered.length && !canCreate" class="optpick-empty">暂无选项</p>
      </div>
    </div>
  </div>
</template>
