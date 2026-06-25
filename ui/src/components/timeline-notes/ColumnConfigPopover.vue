<script setup>
import { reactive, watch } from "vue";
import TimelineLucideIcon from "@/components/timeline-notes/TimelineLucideIcon.vue";

const props = defineProps({
  builtinState: {
    type: Object,
    default: () => ({ type: true, tags: true }),
  },
  columns: {
    type: Array,
    default: () => [],
  },
  saving: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["toggle-builtin", "save-columns"]);

const draft = reactive({
  columns: [],
});

const BUILTIN_LOCKED = [
  { key: "time", label: "时间", icon: "calendar" },
  { key: "title", label: "事件", icon: "alignLeft" },
];
const BUILTIN_TOGGLE = [
  { key: "type", label: "类型", icon: "list" },
  { key: "tags", label: "标签", icon: "hash" },
];

// Notion-style: each property carries a small type glyph.
const TYPE_ICON = {
  text: "alignLeft",
  number: "hash",
  date: "calendar",
  select: "list",
};

function syncColumns(source) {
  draft.columns = (Array.isArray(source) ? source : []).map((column, index) => ({
    key: column?.key || "",
    label: column?.label || "",
    type: column?.type || "text",
    width: Number(column?.width || 96),
    order: Number(column?.order ?? index),
    visible: column?.visible !== false,
    expanded: false,
  }));
}

watch(
  () => props.columns,
  (columns) => syncColumns(columns),
  { immediate: true, deep: true }
);

// New column starts as a blank, already-expanded row so its fields are ready to fill.
function addColumn() {
  draft.columns.push({
    key: "",
    label: "",
    type: "text",
    width: 96,
    order: draft.columns.length,
    visible: true,
    expanded: true,
  });
}

function removeColumn(index) {
  draft.columns.splice(index, 1);
}

function submitColumns() {
  emit(
    "save-columns",
    draft.columns
      .filter((column) => String(column.key || "").trim() && String(column.label || "").trim())
      .map((column, index) => ({
        key: String(column.key || "").trim(),
        label: String(column.label || "").trim(),
        type: String(column.type || "text"),
        width: Number(column.width || 96),
        order: Number(column.order ?? index),
        visible: column.visible !== false,
      }))
  );
}
</script>

<template>
  <div class="pop-section">
    <div class="pop-title-row">
      <div class="pop-label">列设置</div>
      <button type="button" class="iconbtn sm" :disabled="props.saving" title="保存列设置" @click="submitColumns">
        <TimelineLucideIcon name="check" :stroke-width="1.8" />
      </button>
    </div>

    <div v-for="item in BUILTIN_LOCKED" :key="item.key" class="pop-item col-row is-locked">
      <TimelineLucideIcon :name="item.icon" :stroke-width="1.8" class="pop-item-ic" />
      <span class="lbl">{{ item.label }}</span>
      <button type="button" class="col-eye" disabled title="必选列，始终显示">
        <TimelineLucideIcon name="eye" :stroke-width="1.8" />
      </button>
    </div>
    <div
      v-for="item in BUILTIN_TOGGLE"
      :key="item.key"
      class="pop-item col-row"
      :class="{ 'is-hidden': props.builtinState[item.key] === false }"
    >
      <TimelineLucideIcon :name="item.icon" :stroke-width="1.8" class="pop-item-ic" />
      <span class="lbl">{{ item.label }}</span>
      <button
        type="button"
        class="col-eye"
        :title="props.builtinState[item.key] !== false ? '隐藏此列' : '显示此列'"
        @click="emit('toggle-builtin', item.key)"
      >
        <TimelineLucideIcon :name="props.builtinState[item.key] !== false ? 'eye' : 'eyeOff'" :stroke-width="1.8" />
      </button>
    </div>

    <template v-for="(column, index) in draft.columns" :key="`${column.key || 'column'}-${index}`">
      <div class="pop-item col-row" :class="{ 'is-hidden': column.visible === false, editing: column.expanded }">
        <TimelineLucideIcon :name="TYPE_ICON[column.type] || TYPE_ICON.text" :stroke-width="1.8" class="pop-item-ic" />
        <span class="lbl">{{ column.label || "未命名列" }}</span>
        <span class="col-row-act">
          <button
            type="button"
            class="iconbtn sm"
            :class="{ on: column.expanded }"
            title="编辑列"
            @click="column.expanded = !column.expanded"
          >
            <TimelineLucideIcon name="edit" :stroke-width="1.8" />
          </button>
          <button type="button" class="iconbtn sm" title="删除列" @click="removeColumn(index)">
            <TimelineLucideIcon name="trash" :stroke-width="1.8" />
          </button>
        </span>
        <button
          type="button"
          class="col-eye"
          :title="column.visible !== false ? '隐藏此列' : '显示此列'"
          @click="column.visible = column.visible === false"
        >
          <TimelineLucideIcon :name="column.visible !== false ? 'eye' : 'eyeOff'" :stroke-width="1.8" />
        </button>
      </div>
      <div v-if="column.expanded" class="col-grid col-detail">
        <label class="col-detail-wide">
          <span>列名</span>
          <input v-model="column.label" type="text" maxlength="24" placeholder="列名" />
        </label>
        <label>
          <span>键名</span>
          <input v-model="column.key" type="text" maxlength="24" placeholder="source_name" />
        </label>
        <label>
          <span>类型</span>
          <select v-model="column.type">
            <option value="text">text</option>
            <option value="number">number</option>
            <option value="date">date</option>
            <option value="select">select</option>
          </select>
        </label>
        <label>
          <span>宽度</span>
          <input v-model="column.width" type="number" min="72" max="220" />
        </label>
        <label>
          <span>顺序</span>
          <input v-model="column.order" type="number" min="0" max="99" />
        </label>
      </div>
    </template>

    <button type="button" class="pop-item col-add" @click="addColumn">
      <TimelineLucideIcon name="plus" :stroke-width="1.8" class="pop-item-ic" />
      <span class="lbl">新建列</span>
    </button>
  </div>

  <p class="pop-note">键名须英文小写开头，可含数字和下划线；改完点右上角 ✓ 保存到当前专题。</p>
</template>
