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
  next: {
    key: "",
    label: "",
    type: "text",
    width: 96,
    order: 0,
    visible: true,
  },
});

function syncColumns(source) {
  draft.columns = (Array.isArray(source) ? source : []).map((column, index) => ({
    key: column?.key || "",
    label: column?.label || "",
    type: column?.type || "text",
    width: Number(column?.width || 96),
    order: Number(column?.order ?? index),
    visible: column?.visible !== false,
  }));
  draft.next.order = draft.columns.length;
}

watch(
  () => props.columns,
  (columns) => syncColumns(columns),
  { immediate: true, deep: true }
);

function addColumn() {
  if (!String(draft.next.key || "").trim() || !String(draft.next.label || "").trim()) return;
  draft.columns.push({
    key: draft.next.key.trim(),
    label: draft.next.label.trim(),
    type: draft.next.type,
    width: Number(draft.next.width || 96),
    order: Number(draft.next.order || draft.columns.length),
    visible: draft.next.visible,
  });
  draft.next = {
    key: "",
    label: "",
    type: "text",
    width: 96,
    order: draft.columns.length,
    visible: true,
  };
}

function removeColumn(index) {
  draft.columns.splice(index, 1);
}

function submitColumns() {
  emit(
    "save-columns",
    draft.columns.map((column, index) => ({
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
  <div class="col-popover">
    <div class="col-pop-title-row">
      <div>
        <strong>列设置</strong>
        <span>内置列显隐 + 自定义列定义</span>
      </div>
      <button type="button" class="iconbtn sm primary" :disabled="props.saving" @click="submitColumns">
        <TimelineLucideIcon name="check" :stroke-width="1.8" />
      </button>
    </div>

    <div class="col-pop-section">
      <div class="col-pop-label">内置列</div>
      <div class="col-builtins">
        <div class="col-builtin lock">
          <span class="col-builtin-main">
            <b>时间</b>
            <small>必选</small>
          </span>
        </div>
        <div class="col-builtin lock">
          <span class="col-builtin-main">
            <b>事件</b>
            <small>必选</small>
          </span>
        </div>
        <button
          type="button"
          class="col-builtin"
          :class="{ on: props.builtinState.type !== false }"
          @click="emit('toggle-builtin', 'type')"
        >
          <span class="pop-check">
            <TimelineLucideIcon name="check" :stroke-width="1.8" />
          </span>
          <span class="col-builtin-main">
            <b>类型</b>
            <small>首个标签归类</small>
          </span>
        </button>
        <button
          type="button"
          class="col-builtin"
          :class="{ on: props.builtinState.tags !== false }"
          @click="emit('toggle-builtin', 'tags')"
        >
          <span class="pop-check">
            <TimelineLucideIcon name="check" :stroke-width="1.8" />
          </span>
          <span class="col-builtin-main">
            <b>标签</b>
            <small>显示前两项</small>
          </span>
        </button>
      </div>
    </div>

    <div class="col-pop-section">
      <div class="col-pop-label">自定义列</div>
      <div v-if="draft.columns.length" class="col-custom-list">
        <div v-for="(column, index) in draft.columns" :key="`${column.key || 'column'}-${index}`" class="col-item">
          <div class="col-item-head">
            <button
              type="button"
              class="iconbtn sm"
              :class="{ on: column.visible !== false }"
              @click="column.visible = column.visible === false"
            >
              <TimelineLucideIcon name="check" :stroke-width="1.8" />
            </button>
            <strong>{{ column.label || "未命名列" }}</strong>
            <button type="button" class="iconbtn sm" @click="removeColumn(index)">
              <TimelineLucideIcon name="trash" :stroke-width="1.8" />
            </button>
          </div>
          <div class="col-grid">
            <label>
              <span>标签</span>
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
        </div>
      </div>
      <p v-else class="col-pop-note">当前专题还没有自定义列。</p>
    </div>

    <div class="col-pop-section">
      <div class="col-pop-label">新建列</div>
      <div class="col-grid add">
        <label>
          <span>标签</span>
          <input v-model="draft.next.label" type="text" maxlength="24" placeholder="来源" />
        </label>
        <label>
          <span>键名</span>
          <input v-model="draft.next.key" type="text" maxlength="24" placeholder="source" />
        </label>
        <label>
          <span>类型</span>
          <select v-model="draft.next.type">
            <option value="text">text</option>
            <option value="number">number</option>
            <option value="date">date</option>
            <option value="select">select</option>
          </select>
        </label>
        <label>
          <span>宽度</span>
          <input v-model="draft.next.width" type="number" min="72" max="220" />
        </label>
        <label>
          <span>顺序</span>
          <input v-model="draft.next.order" type="number" min="0" max="99" />
        </label>
      </div>
      <button type="button" class="col-add-btn" @click="addColumn">
        <TimelineLucideIcon name="plus" :stroke-width="1.8" />
        <span>添加列定义</span>
      </button>
      <p class="col-pop-note">键名必须是英文小写开头，可含数字和下划线；保存后会写入当前专题 meta。</p>
    </div>
  </div>
</template>
