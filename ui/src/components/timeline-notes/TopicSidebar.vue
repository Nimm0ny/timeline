<script setup>
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from "vue";
import { CONTENT_LIMITS } from "@/constants/contentLimits";
import { OPTION_COLOR_HEX_MAP, OPTION_COLOR_PRESETS } from "@/constants/tags";
import TimelineLucideIcon from "@/components/timeline-notes/TimelineLucideIcon.vue";
import {
  buildPropertyUsage,
  buildOptionId,
  buildPropertyKey,
  buildPropertyRows,
  canChangePropertyType,
  compareTimelineEvents,
  editablePropertyTypeChoices,
  normalizeTopicColumns,
  PROPERTY_TYPE_LABELS,
  propertyTypeIcon,
} from "@/utils/timelineNotes";

const props = defineProps({
  brand: {
    type: String,
    default: "编年",
  },
  topics: {
    type: Array,
    default: () => [],
  },
  events: {
    type: Array,
    default: () => [],
  },
  allEvents: {
    type: Array,
    default: () => [],
  },
  activeTopicId: {
    type: Number,
    default: null,
  },
  activeFilter: {
    type: String,
    default: "all",
  },
  globalFavoriteCount: {
    type: Number,
    default: 0,
  },
  globalFavoritesActive: {
    type: Boolean,
    default: false,
  },
  columns: {
    type: Array,
    default: () => [],
  },
  propertyFilter: {
    type: Object,
    default: () => ({ key: "", value: "" }),
  },
  activeEra: {
    type: String,
    default: "",
  },
  loading: {
    type: Boolean,
    default: false,
  },
  error: {
    type: String,
    default: "",
  },
  columnSaving: {
    type: Boolean,
    default: false,
  },
  createTopicRequestKey: {
    type: Number,
    default: 0,
  },
});

const emit = defineEmits([
  "create-event",
  "create-event-in-topic",
  "create-topic",
  "rename-topic",
  "select-topic",
  "select-era",
  "update:filter",
  "update:property-filter",
  "delete-topic",
  "batch-delete-topics",
  "save-topic-columns",
  "focus-search",
  "open-global-favorites",
  "open-settings",
  "select-ribbon",
]);

const state = reactive({
  ribbon: "files",
  sections: {
    views: false,
    topics: false,
    properties: false,
    stats: false,
  },
  topicCollapsed: {},
  propertyTopicCollapsed: {},
});

const topicName = ref("");
const creatingTopic = ref(false);
const topicCreateRef = ref(null);
const topicInputRef = ref(null);

// Notion-style notebook creation: a clean inline row at the BOTTOM of the 笔记本
// list (where the new notebook — ordered by id asc — actually lands), opened from
// either the group-head + or the persistent "新增" row. No floating box, no ✓/✗
// buttons — a borderless field that commits on Enter/blur and cancels on Esc.
function startCreateTopic() {
  state.sections.topics = false;
  creatingTopic.value = true;
  nextTick(() => {
    topicInputRef.value?.focus();
    topicCreateRef.value?.scrollIntoView({ block: "nearest" });
  });
}

function cancelCreateTopic() {
  creatingTopic.value = false;
  topicName.value = "";
}

// Commit-on-blur (Notion): clicking away saves a named draft, discards an empty one.
function onCreateBlur() {
  if (topicName.value.trim()) {
    submitTopic();
  } else {
    cancelCreateTopic();
  }
}

// Notion-style row hover actions (§2.1 列表行悬停操作组): each notebook row reveals
// a right-edge cluster on hover/active/menu-open — ⊕ (new note here) + ⋯ (more menu:
// rename / delete). Resting count fades out beneath it; nothing reflows.
const topicMenu = ref(null); // { topic, x, y } | null
const renamingTopicId = ref(null);
const renameValue = ref("");
const renameInputRef = ref(null);

function openTopicMenu(topic, event) {
  // Anchor a fixed-position menu under the ⋯ button, clamped to the viewport so it
  // never overflows (the pane scroll-clips, so the menu lives at the overlay layer).
  const rect = event.currentTarget.getBoundingClientRect();
  const width = 152;
  const x = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));
  const y = Math.min(rect.bottom + 4, window.innerHeight - 96);
  topicMenu.value = { topic, x, y };
}

function closeTopicMenu() {
  topicMenu.value = null;
}

function onPaneScroll() {
  if (topicMenu.value) closeTopicMenu();
}

function createInTopic(topicId) {
  closeTopicMenu();
  emit("create-event-in-topic", topicId);
}

// Inline rename reuses the borderless create-row field (one list-edit grammar):
// commit on Enter/blur (when changed & non-empty), cancel on Esc.
function startRenameTopic(topic) {
  closeTopicMenu();
  renamingTopicId.value = topic.id;
  renameValue.value = topic.title || topic.name || "";
  nextTick(() => {
    renameInputRef.value?.focus();
    renameInputRef.value?.select?.();
  });
}

function cancelRenameTopic() {
  renamingTopicId.value = null;
  renameValue.value = "";
}

function submitRenameTopic() {
  const id = renamingTopicId.value;
  if (id == null) return;
  const next = renameValue.value.trim().slice(0, CONTENT_LIMITS.topicTitle);
  const topic = props.topics.find((item) => item.id === id);
  const current = (topic?.title || topic?.name || "").trim();
  renamingTopicId.value = null;
  renameValue.value = "";
  if (next && next !== current) emit("rename-topic", { id, title: next });
}

function onRenameBlur() {
  if (renamingTopicId.value != null) submitRenameTopic();
}

function deleteFromMenu(topic) {
  closeTopicMenu();
  emit("delete-topic", topic.id);
}

function onMenuKeydown(event) {
  if (event.key === "Escape") closeTopicMenu();
}

watch(topicMenu, (value) => {
  if (value) document.addEventListener("keydown", onMenuKeydown);
  else document.removeEventListener("keydown", onMenuKeydown);
});

onBeforeUnmount(() => document.removeEventListener("keydown", onMenuKeydown));

// Batch multi-select for notebooks: a pane-head toggle reveals row checkboxes;
// row clicks then toggle selection instead of navigating, and a batch bar offers
// a multi-delete (confirmed in-app by the page).
const selectMode = ref(false);
const selectedTopicIds = ref([]);
const propertyEditorTopicId = ref(null);
const propertyEditorColumns = ref([]);
const propertySavePending = ref(null);
const propertyDiscardArmed = ref(false);
const OPTION_PROPERTY_TYPES = new Set(["select", "multiselect"]);
const PROPERTY_TYPE_TONES = {
  text: "var(--text-faint)",
  number: "var(--t-economy)",
  date: "var(--accent)",
  checkbox: "var(--t-reform)",
  url: "var(--t-science)",
  email: "var(--t-culture)",
  phone: "var(--t-war)",
  select: "var(--t-politics)",
  multiselect: "var(--t-diplomacy)",
};

function isTopicSelected(topicId) {
  return selectedTopicIds.value.includes(topicId);
}

function toggleSelectMode() {
  selectMode.value = !selectMode.value;
  if (!selectMode.value) selectedTopicIds.value = [];
}

function toggleTopicSelection(topicId) {
  selectedTopicIds.value = isTopicSelected(topicId)
    ? selectedTopicIds.value.filter((id) => id !== topicId)
    : [...selectedTopicIds.value, topicId];
}

function submitBatchDelete() {
  if (selectedTopicIds.value.length) emit("batch-delete-topics", [...selectedTopicIds.value]);
}

// Each ribbon owns a distinct left-pane panel (Obsidian-style). The notebook
// tree, tags, and stats are no longer stacked together under one tab.
const RIBBON_PANELS = {
  files: { title: "笔记本", sections: ["views", "topics"], tree: true },
  search: { title: "搜索", sections: ["views", "topics"], tree: true },
  star: { title: "收藏", sections: ["globalFavorites"], tree: false },
  tags: { title: "属性", sections: ["properties"], tree: false },
  stats: { title: "统计", sections: ["stats"], tree: false },
};
const activePanel = computed(() => RIBBON_PANELS[state.ribbon] || RIBBON_PANELS.files);
const panelHas = (section) => activePanel.value.sections.includes(section);
const ribbonLocked = computed(() => Boolean(propertyEditorTopicId.value) && state.ribbon === "tags");

function isOptionProperty(type) {
  return OPTION_PROPERTY_TYPES.has(type);
}

function propTypeLabel(type) {
  return PROPERTY_TYPE_LABELS[type] || "文本";
}

function editablePropertyTypesFor(type) {
  return editablePropertyTypeChoices(type);
}

function propertyTone(type) {
  return PROPERTY_TYPE_TONES[type] || "var(--accent)";
}

function propertyIcon(type) {
  return propertyTypeIcon(type);
}

function expandHexColor(color) {
  if (!/^#[\da-f]{3}$/i.test(color)) return color.toLowerCase();
  return `#${color.slice(1).split("").map((part) => part + part).join("")}`.toLowerCase();
}

function fallbackOptionHex(index = 0) {
  return OPTION_COLOR_PRESETS[index % OPTION_COLOR_PRESETS.length]?.hex || "#7b68d9";
}

function optionColorValue(color, index = 0) {
  const raw = String(color || "").trim();
  if (/^#[\da-f]{6}$/i.test(raw)) return raw.toLowerCase();
  if (/^#[\da-f]{3}$/i.test(raw)) return expandHexColor(raw);
  return OPTION_COLOR_HEX_MAP[raw] || fallbackOptionHex(index);
}

function defaultPropertyWidth(type = "text") {
  if (type === "multiselect") return 150;
  if (type === "select") return 120;
  if (type === "checkbox") return 72;
  if (type === "date") return 108;
  if (type === "number") return 96;
  return 112;
}

function cloneTopicColumns(topic) {
  return normalizeTopicColumns(topic?.columns).map((column, index) => ({
    key: column.key,
    label: column.label,
    persistedLabel: column.label,
    type: column.type,
    width: Number(column.width || defaultPropertyWidth(column.type)),
    order: Number(column.order ?? index),
    visible: column.visible !== false,
    options: (column.options || []).map((option, optionIndex) => ({
      id: option.id || buildOptionId(option.label, (column.options || []).map((item) => item.id)),
      label: option.label || option.id || "",
      persistedLabel: option.label || option.id || "",
      colorValue: String(option.color || "").trim(),
      pickerValue: optionColorValue(option.color, optionIndex),
    })),
  }));
}

function serializePropertyColumns(columns) {
  const seenKeys = new Set();
  return (Array.isArray(columns) ? columns : [])
    .map((column, index) => {
      const label = (String(column?.label || "").trim() || String(column?.persistedLabel || "").trim()).slice(0, 24);
      if (!label) return null;
      const existingKey = String(column?.key || "").trim();
      const key =
        existingKey && !seenKeys.has(existingKey)
          ? existingKey
          : buildPropertyKey(label, [...seenKeys]);
      seenKeys.add(key);
      const type = String(column?.type || "text").trim() || "text";
      const normalizedType = PROPERTY_TYPE_LABELS[type] ? type : "text";
      const options = isOptionProperty(normalizedType)
        ? ((Array.isArray(column?.options) ? column.options : [])
            .map((option, optionIndex) => {
              const optionLabel = (String(option?.label || "").trim() || String(option?.persistedLabel || "").trim()).slice(0, 24);
              if (!optionLabel) return null;
              return {
                id: String(option?.id || "").trim() || buildOptionId(optionLabel, []),
                label: optionLabel,
                color: String(option?.colorValue || "").trim() || String(option?.pickerValue || "").trim() || fallbackOptionHex(optionIndex),
              };
            })
            .filter(Boolean))
        : [];
      const seenOptionIds = new Set();
      const seenOptionLabels = new Set();
      const dedupedOptions = options.filter((option) => {
        const normalizedLabel = option.label.toLowerCase();
        if (seenOptionIds.has(option.id) || seenOptionLabels.has(normalizedLabel)) return false;
        seenOptionIds.add(option.id);
        seenOptionLabels.add(normalizedLabel);
        return true;
      });
      return {
        key,
        label,
        type: normalizedType,
        width: Number(column?.width || defaultPropertyWidth(normalizedType)),
        order: index,
        visible: column?.visible !== false,
        options: dedupedOptions,
      };
    })
    .filter(Boolean);
}

const propertyEditorTopic = computed(() => props.topics.find((topic) => topic.id === propertyEditorTopicId.value) || null);
const propertyEditorDirty = computed(() => {
  if (!propertyEditorTopic.value) return false;
  return JSON.stringify(serializePropertyColumns(propertyEditorColumns.value)) !== JSON.stringify(serializePropertyColumns(cloneTopicColumns(propertyEditorTopic.value)));
});

function isEditingPropertyTopic(topicId) {
  return propertyEditorTopicId.value === topicId;
}

function propertyEditorLocked(topicId) {
  return propertyEditorTopicId.value != null && propertyEditorTopicId.value !== topicId;
}

function clearPropertyEditor() {
  propertyEditorTopicId.value = null;
  propertyEditorColumns.value = [];
  propertySavePending.value = null;
  propertyDiscardArmed.value = false;
}

function openPropertyEditor(topic) {
  if (!topic?.id) return;
  propertyEditorTopicId.value = topic.id;
  propertyEditorColumns.value = cloneTopicColumns(topic);
  propertySavePending.value = null;
  propertyDiscardArmed.value = false;
  state.propertyTopicCollapsed[topic.id] = false;
}

function cancelPropertyEditor() {
  if (props.columnSaving) return;
  if (!propertyEditorDirty.value || propertyDiscardArmed.value) {
    clearPropertyEditor();
    return;
  }
  propertyDiscardArmed.value = true;
}

function savePropertyEditor(topicId) {
  if (!topicId || props.columnSaving) return;
  propertySavePending.value = {
    topicId,
    signature: JSON.stringify(serializePropertyColumns(propertyEditorColumns.value)),
  };
  propertyDiscardArmed.value = false;
  emit("save-topic-columns", { topicId, columns: serializePropertyColumns(propertyEditorColumns.value) });
}

function togglePropertyTopic(topicId) {
  if (isEditingPropertyTopic(topicId)) return;
  state.propertyTopicCollapsed[topicId] = !isPropertyTopicOpen(topicId);
}

function isPropertyTopicOpen(topicId) {
  if (isEditingPropertyTopic(topicId)) return true;
  if (state.propertyTopicCollapsed[topicId] != null) return state.propertyTopicCollapsed[topicId] !== true;
  return topicId === props.activeTopicId;
}

const topicPropertyUsage = computed(() => {
  const usage = new Map();
  for (const topic of props.topics || []) {
    const topicEvents = liveEventsByTopic.value.get(topic.id) || [];
    usage.set(topic.id, buildPropertyUsage(topic.columns, topicEvents));
  }
  return usage;
});

function canEditPropertyType(topicId, column) {
  return canChangePropertyType(topicPropertyUsage.value.get(topicId), column?.key);
}

function addDraftProperty(topicId) {
  if (!isEditingPropertyTopic(topicId)) {
    const topic = props.topics.find((item) => item.id === topicId);
    if (!topic) return;
    openPropertyEditor(topic);
  }
  const usage = topicPropertyUsage.value.get(topicId);
  const existingKeys = [...new Set([...propertyEditorColumns.value.map((column) => column.key), ...(usage?.orphanKeys || [])])];
  propertyEditorColumns.value.push({
    key: buildPropertyKey("property", existingKeys),
    label: "",
    type: "text",
    width: defaultPropertyWidth("text"),
    order: propertyEditorColumns.value.length,
    visible: true,
    options: [],
  });
}

function removeDraftProperty(index) {
  propertyEditorColumns.value.splice(index, 1);
}

function addDraftOption(column) {
  const usage = topicPropertyUsage.value.get(propertyEditorTopicId.value);
  const orphanIds = usage?.orphanOptionIds?.get(column.key) || new Set();
  const existingIds = [...new Set([...(column.options || []).map((option) => option.id), ...orphanIds])];
  column.options = [
    ...(column.options || []),
    {
      id: buildOptionId("option", existingIds),
      label: "",
      persistedLabel: "",
      colorValue: fallbackOptionHex(existingIds.length),
      pickerValue: fallbackOptionHex(existingIds.length),
    },
  ];
}

function removeDraftOption(column, optionIndex) {
  column.options.splice(optionIndex, 1);
}

function updateDraftPropertyType(column, nextType) {
  column.type = nextType;
  if (!isOptionProperty(nextType)) {
    column.options = [];
    return;
  }
  if (!Array.isArray(column.options) || !column.options.length) {
    column.options = [];
    addDraftOption(column);
  }
}

function updateDraftOptionColor(option, event, index) {
  const next = event?.target?.value || fallbackOptionHex(index);
  option.colorValue = next;
  option.pickerValue = next;
}

function notebookPropertySummary(properties) {
  const total = properties.length;
  if (!total) return "暂无属性";
  const optionCount = properties.filter((property) => property.isOption).length;
  return optionCount ? `${total} 个属性 · ${optionCount} 个选项类` : `${total} 个属性`;
}

function propertyMetaLine(property) {
  if (property.isOption) return `${property.optionCount} 个选项`;
  if (property.type === "checkbox") return property.totalCount ? `已勾选 ${property.checkedCount} / ${property.totalCount} 条` : "布尔开关";
  if (property.filledCount) {
    const samples = property.sampleValues.length ? ` · ${property.sampleValues.join(" · ")}` : "";
    return `已填写 ${property.filledCount} / ${property.totalCount} 条${samples}`;
  }
  const hints = {
    text: "自由文本",
    number: "数字字段",
    date: "日期字段",
    url: "网址链接",
    email: "邮箱链接",
    phone: "电话链接",
  };
  return hints[property.type] || "自由值";
}

function eventCreatedDate(event) {
  const raw = event?.createdAt || event?.updatedAt;
  const date = raw ? new Date(raw) : null;
  return date && !Number.isNaN(date.getTime()) ? date : null;
}

function isToday(event) {
  const date = eventCreatedDate(event);
  if (!date) return false;
  const now = new Date();
  return date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth() && date.getDate() === now.getDate();
}

function isThisWeek(event) {
  const date = eventCreatedDate(event);
  if (!date) return false;
  const now = new Date();
  const start = new Date(now);
  const day = (now.getDay() + 6) % 7;
  start.setDate(now.getDate() - day);
  start.setHours(0, 0, 0, 0);
  const end = new Date(start);
  end.setDate(start.getDate() + 7);
  return date >= start && date < end;
}

const liveEvents = computed(() => props.events.filter((event) => !event.deletedAt));
const deletedEvents = computed(() => props.events.filter((event) => event.deletedAt));

function countForFilter(filter) {
  if (filter === "today") return liveEvents.value.filter(isToday).length;
  if (filter === "week") return liveEvents.value.filter(isThisWeek).length;
  if (filter === "favorite") return liveEvents.value.filter((event) => event.favorite).length;
  if (filter === "trash") return deletedEvents.value.length;
  return liveEvents.value.length;
}

const quickFilters = computed(() => [
  { id: "all", label: "全部笔记", count: countForFilter("all"), icon: "library" },
  { id: "today", label: "今天", count: countForFilter("today"), icon: "calendar" },
  { id: "week", label: "本周", count: countForFilter("week"), icon: "clock" },
  { id: "favorite", label: "收藏", count: countForFilter("favorite"), icon: "star" },
  { id: "trash", label: "回收站", count: countForFilter("trash"), icon: "archive" },
]);

// Era (time-period) rows for the active notebook, ordered chronologically to
// mirror the center timeline's era grouping: both bucket events in
// `compareTimelineEvents` order (earliest dateKey first, "更早" last) and keep
// first-appearance order, so left-pane nav and center groups never disagree —
// fitting a 编年/by-year product. Counts still run over all live events so the
// list never blanks out under an active view filter.
const eraRows = computed(() => {
  const order = [];
  const byEra = new Map();
  for (const event of [...liveEvents.value].sort(compareTimelineEvents)) {
    const key = String(event?.era || "未分期").trim() || "未分期";
    if (!byEra.has(key)) {
      byEra.set(key, { era: key, count: 0 });
      order.push(key);
    }
    byEra.get(key).count += 1;
  }
  return order.map((key) => byEra.get(key));
});

const liveEventsByTopic = computed(() => {
  const grouped = new Map();
  for (const event of props.allEvents || []) {
    if (!event || event.deletedAt) continue;
    const topicId = Number(event.topicId);
    if (!grouped.has(topicId)) grouped.set(topicId, []);
    grouped.get(topicId).push(event);
  }
  return grouped;
});

const propertyTopics = computed(() =>
  props.topics.map((topic) => {
    const topicEvents = liveEventsByTopic.value.get(topic.id) || [];
    const sourceColumns = isEditingPropertyTopic(topic.id) ? propertyEditorColumns.value : topic.columns;
    return {
      topic,
      active: topic.id === props.activeTopicId,
      editing: isEditingPropertyTopic(topic.id),
      properties: buildPropertyRows(sourceColumns, topicEvents),
    };
  })
);

function isOptionActive(key, value) {
  return props.propertyFilter?.key === key && props.propertyFilter?.value === value;
}

function togglePropertyFilter(key, value) {
  emit("update:property-filter", isOptionActive(key, value) ? { key: "", value: "" } : { key, value });
}

function filterPropertyOption(topicId, key, value) {
  if (propertyEditorTopicId.value != null) return;
  if (topicId !== props.activeTopicId) return;
  togglePropertyFilter(key, value);
}

const stats = computed(() => ({
  notes: liveEvents.value.length,
  week: liveEvents.value.filter(isThisWeek).length,
  favorite: liveEvents.value.filter((event) => event.favorite).length,
}));
const globalFavoritesCopy = computed(() => (props.globalFavoriteCount ? `共 ${props.globalFavoriteCount} 条收藏。` : "暂无收藏。"));

// Lightweight "new notes per week" trend (last 8 weeks) as CSS bars — no deps,
// no chart library; oldest week left, current week right.
const weeklyTrend = computed(() => {
  const weeks = 8;
  const buckets = Array.from({ length: weeks }, () => 0);
  const startOfWeek = (date) => {
    const value = new Date(date);
    const day = (value.getDay() + 6) % 7;
    value.setDate(value.getDate() - day);
    value.setHours(0, 0, 0, 0);
    return value;
  };
  const currentStart = startOfWeek(new Date());
  const weekMs = 7 * 24 * 3600 * 1000;
  for (const event of liveEvents.value) {
    const date = eventCreatedDate(event);
    if (!date) continue;
    const diff = Math.round((currentStart - startOfWeek(date)) / weekMs);
    if (diff >= 0 && diff < weeks) buckets[weeks - 1 - diff] += 1;
  }
  const max = Math.max(1, ...buckets);
  return buckets.map((count) => ({ count, pct: count ? Math.max(8, Math.round((count / max) * 100)) : 0 }));
});

function toggleSection(key) {
  state.sections[key] = !state.sections[key];
}

function isTopicExpanded(topicId) {
  return !selectMode.value && topicId === props.activeTopicId && state.topicCollapsed[topicId] !== true;
}

function toggleTopic(topicId) {
  if (selectMode.value) {
    toggleTopicSelection(topicId);
    return;
  }
  if (topicId === props.activeTopicId) {
    state.topicCollapsed[topicId] = isTopicExpanded(topicId);
  } else {
    state.topicCollapsed[topicId] = false;
    allCollapsed.value = false;
  }
  emit("select-topic", topicId);
}

function selectRibbon(ribbon) {
  if (ribbon !== state.ribbon && ribbonLocked.value) return;
  state.ribbon = ribbon;
  emit("select-ribbon", ribbon);
}

function focusSearch() {
  if (ribbonLocked.value) return;
  selectRibbon("search");
  emit("focus-search");
}

function openGlobalFavorites() {
  if (ribbonLocked.value) return;
  emit("open-global-favorites");
}

function submitTopic() {
  const nextName = topicName.value
    .trim()
    .slice(0, CONTENT_LIMITS.topicTitle)
    .replace(/[^\w\-\u4e00-\u9fff]/g, "");
  if (!nextName) return;
  emit("create-topic", nextName);
  topicName.value = "";
  creatingTopic.value = false;
}

const allCollapsed = ref(false);

// One button toggles the whole active panel between fully collapsed and fully
// expanded (sections + notebook nodes), with the icon/label following suit.
function toggleCollapseAll() {
  const collapse = !allCollapsed.value;
  for (const key of activePanel.value.sections) {
    state.sections[key] = collapse;
  }
  for (const topic of props.topics) {
    state.topicCollapsed[topic.id] = collapse;
  }
  allCollapsed.value = collapse;
}

// Drop any selected ids whose notebook no longer exists (e.g. after a batch
// delete reloads the list), keeping the selection consistent.
watch(
  () => props.topics,
  (topics) => {
    const ids = new Set((topics || []).map((topic) => topic.id));
    selectedTopicIds.value = selectedTopicIds.value.filter((id) => ids.has(id));
    if (propertyEditorTopicId.value && !ids.has(propertyEditorTopicId.value)) {
      cancelPropertyEditor();
    }
  },
  { deep: true }
);

// Leaving the notebook tree (switching ribbons) exits multi-select so a hidden
// selection never lingers across panels.
watch(
  () => state.ribbon,
  () => {
    if (selectMode.value) {
      selectMode.value = false;
      selectedTopicIds.value = [];
    }
  }
);

watch(
  () => props.globalFavoritesActive,
  (active) => {
    if (active) state.ribbon = "star";
    else if (state.ribbon === "star") state.ribbon = "files";
  }
);

watch(
  () => props.createTopicRequestKey,
  (key, previous) => {
    if (!key || key === previous) return;
    if (ribbonLocked.value) return;
    state.ribbon = "files";
    startCreateTopic();
  }
);

watch(
  () => props.activeTopicId,
  (topicId, previous) => {
    if (topicId && topicId !== previous) {
      state.topicCollapsed[topicId] = false;
      state.propertyTopicCollapsed[topicId] = false;
      allCollapsed.value = false;
    }
  }
);

watch(
  () => propertyEditorColumns.value,
  () => {
    if (propertyDiscardArmed.value) propertyDiscardArmed.value = false;
  },
  { deep: true }
);

watch(
  () => props.columnSaving,
  (saving, previous) => {
    if (!propertySavePending.value || saving || !previous) return;
    const topic = props.topics.find((item) => item.id === propertySavePending.value.topicId);
    const nextSignature = JSON.stringify(serializePropertyColumns(cloneTopicColumns(topic)));
    if (nextSignature === propertySavePending.value.signature) {
      clearPropertyEditor();
      return;
    }
    propertySavePending.value = null;
  }
);
</script>

<template>
  <aside class="col sidebar">
    <div class="ribbon">
      <button class="rb brand" :title="props.brand">
        <TimelineLucideIcon name="book" :stroke-width="1.8" />
      </button>
      <button class="rb" :class="{ active: state.ribbon === 'files' }" title="笔记本" :disabled="ribbonLocked" @click="selectRibbon('files')">
        <TimelineLucideIcon name="folder" :stroke-width="1.8" />
      </button>
      <button class="rb" :class="{ active: state.ribbon === 'search' }" title="搜索" :disabled="ribbonLocked" @click="focusSearch">
        <TimelineLucideIcon name="search" :stroke-width="1.8" />
      </button>
      <button class="rb" :class="{ active: state.ribbon === 'star' }" title="收藏" :disabled="ribbonLocked" @click="openGlobalFavorites">
        <TimelineLucideIcon name="star" :stroke-width="1.8" />
      </button>
      <button class="rb" :class="{ active: state.ribbon === 'tags' }" title="属性" @click="selectRibbon('tags')">
        <TimelineLucideIcon name="sliders" :stroke-width="1.8" />
      </button>
      <button class="rb" :class="{ active: state.ribbon === 'stats' }" title="统计" :disabled="ribbonLocked" @click="selectRibbon('stats')">
        <TimelineLucideIcon name="bar" :stroke-width="1.8" />
      </button>
    </div>

    <div class="pane">
      <div class="pane-head">
        <span class="ph-title">{{ activePanel.title }}</span>
        <template v-if="activePanel.tree">
          <button v-if="!selectMode" type="button" class="iconbtn" :title="allCollapsed ? '全部展开' : '全部折叠'" @click="toggleCollapseAll">
            <TimelineLucideIcon :name="allCollapsed ? 'unfold' : 'fold'" :stroke-width="1.8" />
          </button>
          <button type="button" class="iconbtn" :class="{ on: selectMode }" :title="selectMode ? '退出多选' : '多选'" @click="toggleSelectMode">
            <TimelineLucideIcon name="listChecks" :stroke-width="1.8" />
          </button>
        </template>
      </div>

      <div v-if="selectMode && activePanel.tree" class="batch-bar">
        <span class="batch-cnt">已选 {{ selectedTopicIds.length }} 个笔记本</span>
        <button
          type="button"
          class="iconbtn sm"
          :disabled="!selectedTopicIds.length"
          title="删除所选笔记本"
          @click="submitBatchDelete"
        >
          <TimelineLucideIcon name="trash" :stroke-width="1.8" />
        </button>
        <button type="button" class="iconbtn sm" title="退出多选" @click="toggleSelectMode">
          <TimelineLucideIcon name="close" :stroke-width="1.8" />
        </button>
      </div>

      <div class="pane-scroll scroll" @scroll="onPaneScroll">
        <div v-if="panelHas('globalFavorites')" class="tg">
          <div class="tg-body">
            <p class="sidebar-copy">{{ globalFavoritesCopy }}</p>
          </div>
        </div>

        <div v-if="panelHas('views')" class="tg" :class="{ collapsed: state.sections.views }">
          <div class="tg-head" @click="toggleSection('views')">
            <span class="tg-chev"><TimelineLucideIcon name="chevronDown" :stroke-width="1.8" /></span>
            <span class="tg-name">视图</span>
          </div>
          <div class="tg-body">
            <button
              v-for="filter in quickFilters"
              :key="filter.id"
              type="button"
              class="ti leaf"
              :class="{ active: filter.id === props.activeFilter }"
              @click="emit('update:filter', filter.id)"
            >
              <span class="ti-chev"></span>
              <span class="ti-ic"><TimelineLucideIcon :name="filter.icon" :stroke-width="1.8" /></span>
              <span class="ti-name">{{ filter.label }}</span>
              <span class="ti-cnt">{{ filter.count }}</span>
            </button>
          </div>
        </div>

        <div v-if="panelHas('topics')" class="tg" :class="{ collapsed: state.sections.topics }">
          <div class="tg-head" @click="toggleSection('topics')">
            <span class="tg-chev"><TimelineLucideIcon name="chevronDown" :stroke-width="1.8" /></span>
            <span class="tg-name">笔记本</span>
            <button type="button" class="iconbtn sm" :class="{ on: creatingTopic }" title="新建笔记本" @click.stop="startCreateTopic">
              <TimelineLucideIcon name="plusSign" :stroke-width="1.8" />
            </button>
          </div>
          <div class="tg-body">
            <p v-if="props.loading" class="sidebar-copy">正在加载笔记本...</p>
            <p v-else-if="props.error" class="sidebar-copy">{{ props.error }}</p>
            <template v-else>
              <div v-for="topic in props.topics" :key="topic.id">
                <div v-if="renamingTopicId === topic.id" class="ti folder ti-create">
                  <span class="ti-chev"></span>
                  <span class="ti-ic"><TimelineLucideIcon name="folder" :stroke-width="1.8" /></span>
                  <input
                    :ref="(el) => (renameInputRef.value = el)"
                    v-model="renameValue"
                    class="ti-create-input"
                    type="text"
                    :maxlength="CONTENT_LIMITS.topicTitle"
                    @keyup.enter="submitRenameTopic"
                    @keyup.esc="cancelRenameTopic"
                    @blur="onRenameBlur"
                  />
                </div>
                <button
                  v-else
                  type="button"
                  class="ti folder"
                  :class="{
                    active: !selectMode && topic.id === props.activeTopicId,
                    selected: selectMode && isTopicSelected(topic.id),
                    collapsed: !isTopicExpanded(topic.id),
                    'menu-open': topicMenu && topicMenu.topic.id === topic.id,
                  }"
                  @click="toggleTopic(topic.id)"
                >
                  <span v-if="selectMode" class="tcheck" :class="{ on: isTopicSelected(topic.id) }">
                    <TimelineLucideIcon v-if="isTopicSelected(topic.id)" name="check" :stroke-width="2.4" />
                  </span>
                  <span v-else class="ti-chev"><TimelineLucideIcon name="chevronDown" :stroke-width="1.8" /></span>
                  <span class="ti-ic"><TimelineLucideIcon name="folder" :stroke-width="1.8" /></span>
                  <span class="ti-name">{{ topic.title || topic.name }}</span>
                  <span class="ti-cnt">{{ topic.eventCount || 0 }}</span>
                  <span v-if="!selectMode" class="ti-acts">
                    <span class="ti-act" title="更多操作" @click.stop="openTopicMenu(topic, $event)">
                      <TimelineLucideIcon name="more" :stroke-width="1.8" />
                    </span>
                    <span class="ti-act" title="在此笔记本新建笔记" @click.stop="createInTopic(topic.id)">
                      <TimelineLucideIcon name="plusSign" :stroke-width="1.8" />
                    </span>
                  </span>
                </button>
                <Transition name="topic-kids-stack">
                  <div v-if="isTopicExpanded(topic.id)" class="ti-kids-shell">
                    <div class="ti-kids" :style="{ '--pdepth': 0 }">
                      <button
                        v-for="(era, index) in eraRows"
                        :key="era.era"
                        type="button"
                        class="ti leaf"
                        :class="{ active: era.era === props.activeEra }"
                        :style="{ '--depth': 1, '--stack-index': index }"
                        @click="emit('select-era', era.era === props.activeEra ? '' : era.era)"
                      >
                        <span class="ti-chev"></span>
                        <span class="ti-ic"><TimelineLucideIcon name="notebook" :stroke-width="1.8" /></span>
                        <span class="ti-name">{{ era.era }}</span>
                        <span class="ti-cnt">{{ era.count }}</span>
                      </button>
                    </div>
                  </div>
                </Transition>
              </div>
            </template>

            <div v-if="creatingTopic" ref="topicCreateRef" class="ti folder ti-create">
              <span class="ti-chev"></span>
              <span class="ti-ic"><TimelineLucideIcon name="folder" :stroke-width="1.8" /></span>
              <input
                ref="topicInputRef"
                v-model="topicName"
                class="ti-create-input"
                type="text"
                :maxlength="CONTENT_LIMITS.topicTitle"
                placeholder="新笔记本名称"
                @keyup.enter="submitTopic"
                @keyup.esc="cancelCreateTopic"
                @blur="onCreateBlur"
              />
            </div>

            <button
              v-if="!props.loading"
              type="button"
              class="ti leaf ti-add"
              title="新建笔记本"
              @click="startCreateTopic"
            >
              <span class="ti-chev"></span>
              <span class="ti-ic"><TimelineLucideIcon name="plusSign" :stroke-width="1.8" /></span>
              <span class="ti-name">新增</span>
            </button>
          </div>
        </div>

        <div v-if="panelHas('properties')" class="prop-panel">
          <p v-if="!props.topics.length" class="sidebar-copy">暂无笔记本。</p>
          <template v-else>
            <section
              v-for="entry in propertyTopics"
              :key="entry.topic.id"
              class="prop-topic"
              :class="{ active: entry.active, editing: entry.editing }"
            >
                <div
                  class="prop-topic-head"
                  role="button"
                  tabindex="0"
                  :aria-expanded="String(isPropertyTopicOpen(entry.topic.id))"
                  @click="togglePropertyTopic(entry.topic.id)"
                  @keydown.enter.prevent="togglePropertyTopic(entry.topic.id)"
                  @keydown.space.prevent="togglePropertyTopic(entry.topic.id)"
                >
                  <span class="tg-chev" :class="{ collapsed: !isPropertyTopicOpen(entry.topic.id) }">
                    <TimelineLucideIcon name="chevronDown" :stroke-width="1.8" />
                  </span>
                  <div class="prop-topic-main">
                    <div class="prop-topic-title-row">
                      <span class="prop-topic-title">
                        <TimelineLucideIcon name="folder" :stroke-width="1.8" />
                        <span>{{ entry.topic.title || entry.topic.name }}</span>
                      </span>
                      <span v-if="entry.active" class="prop-topic-badge">当前</span>
                    </div>
                    <p class="prop-topic-meta">{{ notebookPropertySummary(entry.properties) }}</p>
                  </div>
                  <div class="prop-topic-actions">
                    <template v-if="entry.editing">
                      <button type="button" class="iconbtn sm" :disabled="props.columnSaving" title="新增属性" @click.stop="addDraftProperty(entry.topic.id)">
                        <TimelineLucideIcon name="plusSign" :stroke-width="1.8" />
                      </button>
                      <button
                        type="button"
                        class="iconbtn sm"
                        :disabled="props.columnSaving || !propertyEditorDirty"
                        title="保存属性"
                        @click.stop="savePropertyEditor(entry.topic.id)"
                      >
                        <TimelineLucideIcon name="save" :stroke-width="1.8" />
                      </button>
                      <button
                        type="button"
                        class="iconbtn sm"
                        :class="{ on: propertyDiscardArmed }"
                        :disabled="props.columnSaving"
                        :title="propertyDiscardArmed ? '再次点击放弃属性草稿' : '取消编辑'"
                        @click.stop="cancelPropertyEditor"
                      >
                        <TimelineLucideIcon name="close" :stroke-width="1.8" />
                      </button>
                    </template>
                    <button
                      v-else
                      v-show="isPropertyTopicOpen(entry.topic.id)"
                      type="button"
                      class="iconbtn sm"
                      :disabled="propertyEditorLocked(entry.topic.id)"
                      title="管理此笔记本属性"
                      @click.stop="openPropertyEditor(entry.topic)"
                    >
                      <TimelineLucideIcon name="squarePen" :stroke-width="1.8" />
                    </button>
                  </div>
                </div>

                <div v-if="isPropertyTopicOpen(entry.topic.id)" class="prop-topic-body">
                  <template v-if="entry.editing">
                    <div
                      v-for="(column, index) in propertyEditorColumns"
                      :key="`${column.key || 'property'}-${index}`"
                      class="prop-card prop-card-manage"
                      :class="{ 'type-locked': !canEditPropertyType(entry.topic.id, column), saving: props.columnSaving }"
                      :style="{ '--prop-tone': propertyTone(column.type) }"
                    >
                      <div class="prop-card-head">
                        <div class="prop-card-main">
                          <span class="prop-card-ic">
                            <TimelineLucideIcon :name="propertyIcon(column.type)" :stroke-width="1.8" />
                          </span>
                          <div class="prop-card-copy">
                            <span class="prop-card-name">{{ column.label || "未命名属性" }}</span>
                            <span class="prop-card-type">{{ propTypeLabel(column.type) }}</span>
                          </div>
                        </div>
                        <button type="button" class="iconbtn sm" :disabled="props.columnSaving" title="删除属性" @click.stop="removeDraftProperty(index)">
                          <TimelineLucideIcon name="trash" :stroke-width="1.8" />
                        </button>
                      </div>
                      <div class="prop-manage-grid">
                        <label class="prop-manage-field prop-manage-field-wide">
                          <span>名称</span>
                          <input v-model="column.label" :disabled="props.columnSaving" type="text" maxlength="24" placeholder="属性名称" />
                        </label>
                        <label class="prop-manage-field">
                          <span>类型</span>
                          <select
                            :value="column.type"
                            :disabled="props.columnSaving || !canEditPropertyType(entry.topic.id, column)"
                            @change="updateDraftPropertyType(column, $event.target.value)"
                          >
                            <option
                              v-for="type in editablePropertyTypesFor(column.type)"
                              :key="type.value"
                              :value="type.value"
                              :disabled="type.legacy === true"
                            >{{ type.label }}</option>
                          </select>
                        </label>
                      </div>
                      <div v-if="isOptionProperty(column.type)" class="prop-option-manage-list">
                        <div
                          v-for="(option, optionIndex) in column.options"
                          :key="`${option.id || 'option'}-${optionIndex}`"
                          class="prop-option-manage"
                        >
                          <label class="prop-option-color" :title="`设置${option.label || '选项'}颜色`">
                            <span class="prop-option-dot is-large" :style="{ '--dot': option.colorValue || option.pickerValue || optionColorValue('', optionIndex) }"></span>
                            <input
                              type="color"
                              :value="option.pickerValue || optionColorValue(option.colorValue, optionIndex)"
                              :disabled="props.columnSaving"
                              @input="updateDraftOptionColor(option, $event, optionIndex)"
                            />
                          </label>
                          <input v-model="option.label" class="prop-option-input" :disabled="props.columnSaving" type="text" maxlength="24" placeholder="选项名称" />
                          <button type="button" class="iconbtn sm" :disabled="props.columnSaving" title="删除选项" @click.stop="removeDraftOption(column, optionIndex)">
                            <TimelineLucideIcon name="trash" :stroke-width="1.8" />
                          </button>
                        </div>
                        <div class="prop-option-manage-foot">
                          <button type="button" class="iconbtn sm" :disabled="props.columnSaving" title="新增选项" @click.stop="addDraftOption(column)">
                            <TimelineLucideIcon name="plusSign" :stroke-width="1.8" />
                          </button>
                          <span class="prop-option-manage-copy">单选 / 多选可在这里维护名称和颜色。</span>
                        </div>
                      </div>
                      <p v-if="!canEditPropertyType(entry.topic.id, column)" class="prop-card-note">已有笔记使用此属性；为避免值被重新规整，当前不允许直接改类型。</p>
                      <p v-else-if="propertyDiscardArmed" class="prop-card-note">再次点击取消可放弃当前属性草稿。</p>
                      <p v-else class="prop-card-note">{{ propertyMetaLine({ ...column, isOption: false, filledCount: 0, totalCount: 0, checkedCount: 0, sampleValues: [] }) }}</p>
                    </div>
                    <p v-if="!propertyEditorColumns.length" class="prop-empty">点击右上角新增属性。</p>
                  </template>

                  <template v-else>
                    <div
                      v-for="property in entry.properties"
                      :key="property.key"
                      class="prop-card"
                      :style="{ '--prop-tone': propertyTone(property.type) }"
                    >
                      <div class="prop-card-head">
                        <div class="prop-card-main">
                          <span class="prop-card-ic">
                            <TimelineLucideIcon :name="propertyIcon(property.type)" :stroke-width="1.8" />
                          </span>
                          <div class="prop-card-copy">
                            <span class="prop-card-name">{{ property.label }}</span>
                            <span class="prop-card-type">{{ propTypeLabel(property.type) }}</span>
                          </div>
                        </div>
                        <span class="prop-card-stat">{{ property.isOption ? `${property.optionCount} 项` : `${property.filledCount}/${property.totalCount}` }}</span>
                      </div>

                      <div v-if="property.isOption" class="prop-card-options">
                        <button
                          v-for="option in property.options"
                          :key="option.value"
                          type="button"
                          class="prop-option-filter"
                          :class="{
                            active: entry.active && isOptionActive(property.key, option.value),
                            inactive: !entry.active,
                          }"
                          :disabled="!entry.active"
                          @click="filterPropertyOption(entry.topic.id, property.key, option.value)"
                        >
                          <span class="prop-option-dot" :style="{ '--dot': option.color }"></span>
                          <span class="prop-option-label">{{ option.label }}</span>
                          <span class="prop-option-count">{{ option.count }}</span>
                        </button>
                        <p v-if="!property.options.length" class="prop-empty">暂无选项</p>
                      </div>
                      <p v-else class="prop-card-note">{{ propertyMetaLine(property) }}</p>
                    </div>
                    <p v-if="!entry.properties.length" class="prop-empty">暂无属性。</p>
                  </template>
                </div>
              </section>
            </template>
        </div>

        <div v-if="panelHas('stats')" class="tg" :class="{ collapsed: state.sections.stats }">
          <div class="tg-head" @click="toggleSection('stats')">
            <span class="tg-chev"><TimelineLucideIcon name="chevronDown" :stroke-width="1.8" /></span>
            <span class="tg-name">统计</span>
          </div>
          <div class="tg-body">
            <div class="mini-stats">
              <div class="ms-cell">
                <div class="ms-num">{{ stats.notes }}</div>
                <div class="ms-cap">笔记</div>
              </div>
              <div class="ms-cell">
                <div class="ms-num accent">{{ stats.week }}</div>
                <div class="ms-cap">本周新增</div>
              </div>
              <div class="ms-cell">
                <div class="ms-num">{{ stats.favorite }}</div>
                <div class="ms-cap">收藏</div>
              </div>
            </div>
            <div class="stat-trend">
              <div class="stat-trend-cap">近 8 周新增</div>
              <div class="spark">
                <span
                  v-for="(bar, index) in weeklyTrend"
                  :key="index"
                  class="spark-bar"
                  :class="{ on: bar.count }"
                  :style="{ height: bar.pct + '%' }"
                  :title="`${bar.count} 条`"
                ></span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="pane-foot">
        <button type="button" class="vault-switch">
          <TimelineLucideIcon name="chevronsUpDown" :stroke-width="1.8" />
          <b>{{ props.brand }}</b>
        </button>
        <button type="button" class="iconbtn" title="帮助">
          <TimelineLucideIcon name="help" :stroke-width="1.8" />
        </button>
        <button type="button" class="iconbtn" title="设置" @click="emit('open-settings')">
          <TimelineLucideIcon name="settings" :stroke-width="1.8" />
        </button>
      </div>
    </div>

    <div v-if="topicMenu" class="ti-menu-backdrop" @click="closeTopicMenu" @contextmenu.prevent="closeTopicMenu">
      <div class="popover ti-menu" :style="{ left: topicMenu.x + 'px', top: topicMenu.y + 'px' }" @click.stop>
        <button type="button" class="pop-item" @click="startRenameTopic(topicMenu.topic)">
          <TimelineLucideIcon name="squarePen" :stroke-width="1.8" class="pop-item-ic" />
          <span class="lbl">重命名</span>
        </button>
        <button type="button" class="pop-item danger" @click="deleteFromMenu(topicMenu.topic)">
          <TimelineLucideIcon name="trash" :stroke-width="1.8" class="pop-item-ic" />
          <span class="lbl">删除</span>
        </button>
      </div>
    </div>
  </aside>
</template>
