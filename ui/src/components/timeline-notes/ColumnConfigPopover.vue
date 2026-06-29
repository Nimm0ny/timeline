<script setup>
import { onBeforeUnmount, reactive, watch } from "vue";
import TimelineLucideIcon from "@/components/timeline-notes/TimelineLucideIcon.vue";
import { PROPERTY_TYPE_ICONS as TYPE_ICON, serializeTopicColumnsDraft } from "@/utils/timelineNotes";

const props = defineProps({
  columns: {
    type: Array,
    default: () => [],
  },
  saving: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["save-columns"]);

const draft = reactive({
  columns: [],
});
let autosaveTimer = null;
let lastEmittedSignature = "[]";

// Only the date + headline columns are structural; every other column (type,
// tags, custom) is an ordinary, reorderable, deletable property.
const BUILTIN_LOCKED = [
  { key: "time", label: "时间", icon: "calendar" },
  { key: "title", label: "事件", icon: "alignLeft" },
];

function serializeColumns(source) {
  return serializeTopicColumnsDraft(source, props.columns);
}

function syncColumns(source) {
  draft.columns = (Array.isArray(source) ? source : []).map((column, index) => ({
    key: column?.key || "",
    label: column?.label || "",
    type: column?.type || "text",
    width: Number(column?.width || 96),
    order: Number(column?.order ?? index),
    visible: column?.visible !== false,
    persistedKey: column?.key || "",
    // Options are managed via the picker / left 属性 tab; carry them through
    // untouched so editing a column never wipes its options.
    options: Array.isArray(column?.options) ? column.options.map((option) => ({ ...option })) : [],
    expanded: false,
  }));
  lastEmittedSignature = JSON.stringify(serializeColumns(source));
}

watch(
  () => props.columns,
  (columns) => syncColumns(columns),
  { immediate: true, deep: true }
);

watch(
  () => draft.columns,
  () => {
    const signature = JSON.stringify(serializeColumns(draft.columns));
    if (signature === lastEmittedSignature) return;
    if (autosaveTimer) window.clearTimeout(autosaveTimer);
    autosaveTimer = window.setTimeout(() => {
      const latest = serializeColumns(draft.columns);
      const latestSignature = JSON.stringify(latest);
      if (latestSignature === lastEmittedSignature) return;
      lastEmittedSignature = latestSignature;
      emit("save-columns", latest);
    }, 180);
  },
  { deep: true }
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
    persistedKey: "",
    options: [],
    expanded: true,
  });
}

function removeColumn(index) {
  draft.columns.splice(index, 1);
}

function flushPendingSave() {
  if (autosaveTimer) window.clearTimeout(autosaveTimer);
  autosaveTimer = null;
  const latest = serializeColumns(draft.columns);
  const latestSignature = JSON.stringify(latest);
  if (latestSignature === lastEmittedSignature) return;
  lastEmittedSignature = latestSignature;
  emit("save-columns", latest);
}

function toggleColumnVisibility(column) {
  const nextVisible = column.visible === false;
  column.visible = nextVisible;
  flushPendingSave();
}

onBeforeUnmount(() => {
  flushPendingSave();
});
</script>

<template>
  <div class="pop-section">
    <div class="pop-title-row">
      <div class="pop-label">列设置</div>
    </div>

    <div v-for="item in BUILTIN_LOCKED" :key="item.key" class="pop-item col-row is-locked">
      <TimelineLucideIcon :name="item.icon" :stroke-width="1.8" class="pop-item-ic" />
      <span class="lbl">{{ item.label }}</span>
      <button type="button" class="col-eye" disabled title="必选列，始终显示">
        <TimelineLucideIcon name="eye" :stroke-width="1.8" />
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
          :disabled="props.saving"
          :title="column.visible !== false ? '隐藏此列' : '显示此列'"
          @click="toggleColumnVisibility(column)"
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
            <option value="text">文本</option>
            <option value="number">数字</option>
            <option value="date">日期</option>
            <option value="checkbox">复选</option>
            <option value="url">链接</option>
            <option value="email">邮箱</option>
            <option value="phone">电话</option>
            <option value="select">单选</option>
            <option value="multiselect">多选</option>
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
      <TimelineLucideIcon name="plusSign" :stroke-width="1.8" class="pop-item-ic" />
      <span class="lbl">新建列</span>
    </button>
  </div>

  <p class="pop-note">类型/标签与自定义列都是属性；键名须英文小写开头，可含数字和下划线。单选/多选的选项在右栏编辑或左栏「属性」中维护。眼睛切换、列字段编辑都会自动保存。</p>
</template>
