<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import LucideIcon from "@/components/notes/LucideIcon.vue";
import { OPTION_PALETTE } from "@/constants/tags";
import { buildOptionId } from "@/utils/noteUtils";

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
// Fixed-position anchor (viewport coords). The property pane scroll-clips its
// children, so like the sidebar ⋯ menus the panel lives at the overlay layer
// and is measured from the control on open.
const popStyle = ref(null);

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
// Color the create-row chip preview with the palette slot the new option WILL
// get, so what you see in the preview is exactly what lands after Enter.
const nextColor = computed(() => OPTION_PALETTE[options.value.length % OPTION_PALETTE.length]);

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
  const color = nextColor.value;
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
  const rect = rootRef.value?.getBoundingClientRect();
  if (rect) {
    // Same-width as the control, clamped so the panel (search 36 + hint 22 +
    // list ≤240 + padding ≈ 310px) never leaves the viewport.
    const width = Math.max(rect.width, 220);
    const left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));
    const top = Math.max(8, Math.min(rect.bottom + 6, window.innerHeight - 330));
    popStyle.value = { left: `${left}px`, top: `${top}px`, width: `${width}px` };
  }
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

// The fixed panel can't follow its anchor, so any outside scroll dismisses it
// (option-list scrolling stays inside rootRef and is ignored).
function onAnyScroll(event) {
  if (open.value && rootRef.value && !rootRef.value.contains(event.target)) closePanel();
}

onMounted(() => {
  document.addEventListener("pointerdown", onDocumentPointer);
  document.addEventListener("keydown", onKeydown);
  window.addEventListener("scroll", onAnyScroll, true);
});

onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", onDocumentPointer);
  document.removeEventListener("keydown", onKeydown);
  window.removeEventListener("scroll", onAnyScroll, true);
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

    <div v-if="open" class="popover optpick-pop" :style="popStyle" @click.stop>
      <input
        ref="inputRef"
        v-model="query"
        class="optpick-search"
        type="text"
        placeholder="搜索选项…"
        @keydown.enter.prevent="createOption"
      />
      <p class="optpick-hint">{{ multiple ? "选择或新建选项" : "选择一个选项" }}</p>
      <div class="optpick-list scroll">
        <button
          v-for="option in filtered"
          :key="option.id"
          type="button"
          class="optpick-opt"
          :class="{ on: isSelected(option.id) }"
          @click="toggle(option.id)"
        >
          <span class="ptag" :style="{ '--dot': option.color || 'var(--accent)' }">
            <i></i>{{ option.label }}
          </span>
          <span v-if="isSelected(option.id)" class="opt-check">
            <LucideIcon name="check" :stroke-width="1.75" />
          </span>
        </button>
        <button v-if="canCreate" type="button" class="optpick-create" @click="createOption">
          <span class="optpick-create-word">新建</span>
          <span class="ptag" :style="{ '--dot': nextColor }">
            <i></i>{{ query.trim() }}
          </span>
        </button>
        <p v-if="!filtered.length && !canCreate" class="optpick-empty">暂无选项</p>
      </div>
    </div>
  </div>
</template>
