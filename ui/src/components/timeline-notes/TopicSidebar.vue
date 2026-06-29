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
  if (editing.value) closePropertyPopover();
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

onBeforeUnmount(() => {
  document.removeEventListener("keydown", onMenuKeydown);
  document.removeEventListener("pointerdown", onPropertyPointerDown, true);
  document.removeEventListener("keydown", onPropertyKeydown);
  flushPropertySave();
});

// Batch multi-select for notebooks: a pane-head toggle reveals row checkboxes;
// row clicks then toggle selection instead of navigating, and a batch bar offers
// a multi-delete (confirmed in-app by the page).
const selectMode = ref(false);
const selectedTopicIds = ref([]);
// Per-property inline editor: a single floating popover anchored to the clicked
// property row, editing exactly one property with debounced autosave — no
// save/cancel/discard ceremony (无感编辑). null when closed.
const editing = ref(null); // { topicId, column, anchor, optionCounts, isNew }
const propNameRef = ref(null);
const deleteArmed = ref(""); // `${topicId}:${key}` — two-step delete on read rows
let propertyAutosaveTimer = null;
let lastSavedSignature = "";
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

function togglePropertyTopic(topicId) {
  state.propertyTopicCollapsed[topicId] = !isPropertyTopicOpen(topicId);
}

function isPropertyTopicOpen(topicId) {
  if (state.propertyTopicCollapsed[topicId] != null) return state.propertyTopicCollapsed[topicId] !== true;
  return topicId === props.activeTopicId;
}

// Anchor a fixed popover beside the clicked property row, flipping to the row's
// left when it would overflow the right edge, clamped to the viewport (the pane
// scroll-clips, so the popover lives at the overlay layer like the ⋯ menu).
function anchorFor(event) {
  const rect = event.currentTarget.getBoundingClientRect();
  const width = 280;
  const gap = 8;
  let x = rect.right + gap;
  if (x + width > window.innerWidth - 8) x = rect.left - width - gap;
  x = Math.max(8, Math.min(x, window.innerWidth - width - 8));
  const y = Math.max(8, Math.min(rect.top, window.innerHeight - 360));
  return { x, y };
}

function baseSignature(topic) {
  return JSON.stringify(serializePropertyColumns(cloneTopicColumns(topic)));
}

// Re-fold the single edited property back into the notebook's full column set
// (matched by key, appended when new) so an autosave never drops siblings.
function buildMergedColumns(topic, edited) {
  const base = cloneTopicColumns(topic);
  const index = base.findIndex((column) => column.key === edited.key);
  if (index === -1) return [...base, edited];
  const next = base.slice();
  next[index] = edited;
  return next;
}

function flushPropertySave() {
  if (propertyAutosaveTimer) {
    window.clearTimeout(propertyAutosaveTimer);
    propertyAutosaveTimer = null;
  }
  const current = editing.value;
  if (!current) return;
  const topic = props.topics.find((item) => item.id === current.topicId);
  if (!topic) return;
  const serialized = serializePropertyColumns(buildMergedColumns(topic, current.column));
  const signature = JSON.stringify(serialized);
  if (signature === lastSavedSignature) return;
  lastSavedSignature = signature;
  emit("save-topic-columns", { topicId: current.topicId, columns: serialized });
}

function schedulePropertySave() {
  if (propertyAutosaveTimer) window.clearTimeout(propertyAutosaveTimer);
  propertyAutosaveTimer = window.setTimeout(flushPropertySave, 200);
}

function closePropertyPopover() {
  flushPropertySave();
  editing.value = null;
}

function openPropertyPopover(topic, property, event) {
  if (!topic?.id) return;
  flushPropertySave();
  const draft = cloneTopicColumns(topic).find((column) => column.key === property.key);
  if (!draft) return;
  const optionCounts = new Map((property.options || []).map((option) => [option.value, option.count]));
  lastSavedSignature = baseSignature(topic);
  editing.value = { topicId: topic.id, column: draft, anchor: anchorFor(event), optionCounts, isNew: false };
}

function addProperty(topic, event) {
  if (!topic?.id) return;
  flushPropertySave();
  state.propertyTopicCollapsed[topic.id] = false;
  const usage = topicPropertyUsage.value.get(topic.id);
  const existingKeys = [...new Set([...cloneTopicColumns(topic).map((column) => column.key), ...(usage?.orphanKeys || [])])];
  const draft = {
    key: buildPropertyKey("property", existingKeys),
    label: "",
    persistedLabel: "",
    type: "text",
    width: defaultPropertyWidth("text"),
    order: existingKeys.length,
    visible: true,
    options: [],
  };
  lastSavedSignature = baseSignature(topic);
  editing.value = { topicId: topic.id, column: draft, anchor: anchorFor(event), optionCounts: new Map(), isNew: true };
  nextTick(() => propNameRef.value?.focus());
}

function optionUsageCount(option) {
  return editing.value?.optionCounts?.get(option?.id) || 0;
}

function isDeleteArmed(topicId, key) {
  return deleteArmed.value === `${topicId}:${key}`;
}

function disarmDelete() {
  deleteArmed.value = "";
}

// Two-step delete (right-pane trash idiom): first click arms (turns red), second
// removes the whole property column. Re-serializes the notebook without that key.
function armOrDeleteProperty(topic, key, event) {
  event?.stopPropagation?.();
  const token = `${topic.id}:${key}`;
  if (deleteArmed.value !== token) {
    deleteArmed.value = token;
    return;
  }
  deleteArmed.value = "";
  const remaining = serializePropertyColumns(cloneTopicColumns(topic).filter((column) => column.key !== key));
  if (editing.value?.topicId === topic.id && editing.value?.column?.key === key) editing.value = null;
  lastSavedSignature = JSON.stringify(remaining);
  emit("save-topic-columns", { topicId: topic.id, columns: remaining });
}

function onPropertyPointerDown(event) {
  const target = event.target;
  if (!(target instanceof Element)) return;
  if (target.closest(".prop-pop")) return;
  if (target.closest(".prop-row") || target.closest(".prop-add-row")) return;
  closePropertyPopover();
}

function onPropertyKeydown(event) {
  if (event.key === "Escape") closePropertyPopover();
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

function addDraftOption(column) {
  const usage = topicPropertyUsage.value.get(editing.value?.topicId);
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
    return {
      topic,
      active: topic.id === props.activeTopicId,
      properties: buildPropertyRows(topic.columns, topicEvents),
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
  if (editing.value) closePropertyPopover();
  state.ribbon = ribbon;
  emit("select-ribbon", ribbon);
}

function focusSearch() {
  selectRibbon("search");
  emit("focus-search");
}

function openGlobalFavorites() {
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
    if (editing.value && !ids.has(editing.value.topicId)) editing.value = null;
  },
  { deep: true }
);

// Leaving the notebook tree (switching ribbons) exits multi-select so a hidden
// selection never lingers across panels, and closes any open property popover.
watch(
  () => state.ribbon,
  () => {
    if (editing.value) closePropertyPopover();
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

// Debounced autosave: any keystroke / option edit in the open popover folds back
// into the notebook's columns and persists, with no save/cancel ceremony.
watch(
  editing,
  () => {
    if (editing.value) schedulePropertySave();
  },
  { deep: true }
);

// Outside-click + Esc dismissal live only while the popover is open (capture phase
// so a click on another property row switches rather than just closing).
watch(editing, (value) => {
  if (value) {
    document.addEventListener("pointerdown", onPropertyPointerDown, true);
    document.addEventListener("keydown", onPropertyKeydown);
  } else {
    document.removeEventListener("pointerdown", onPropertyPointerDown, true);
    document.removeEventListener("keydown", onPropertyKeydown);
  }
});
</script>

<template>
  <aside class="col sidebar">
    <div class="ribbon">
      <button class="rb brand" :title="props.brand">
        <TimelineLucideIcon name="book" :stroke-width="1.8" />
      </button>
      <button class="rb" :class="{ active: state.ribbon === 'files' }" title="笔记本" @click="selectRibbon('files')">
        <TimelineLucideIcon name="folder" :stroke-width="1.8" />
      </button>
      <button class="rb" :class="{ active: state.ribbon === 'search' }" title="搜索" @click="focusSearch">
        <TimelineLucideIcon name="search" :stroke-width="1.8" />
      </button>
      <button class="rb" :class="{ active: state.ribbon === 'star' }" title="收藏" @click="openGlobalFavorites">
        <TimelineLucideIcon name="star" :stroke-width="1.8" />
      </button>
      <button class="rb" :class="{ active: state.ribbon === 'tags' }" title="属性" @click="selectRibbon('tags')">
        <TimelineLucideIcon name="sliders" :stroke-width="1.8" />
      </button>
      <button class="rb" :class="{ active: state.ribbon === 'stats' }" title="统计" @click="selectRibbon('stats')">
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
              :class="{ active: entry.active }"
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
              </div>

              <div v-if="isPropertyTopicOpen(entry.topic.id)" class="prop-topic-body">
                <div
                  v-for="property in entry.properties"
                  :key="property.key"
                  class="prop-item"
                  :style="{ '--prop-tone': propertyTone(property.type) }"
                >
                  <div
                    class="prop-row"
                    role="button"
                    tabindex="0"
                    :class="{ active: editing && editing.topicId === entry.topic.id && editing.column.key === property.key }"
                    @click="openPropertyPopover(entry.topic, property, $event)"
                    @keydown.enter.prevent="openPropertyPopover(entry.topic, property, $event)"
                    @mouseleave="disarmDelete"
                  >
                    <span class="prop-row-ic"><TimelineLucideIcon :name="propertyIcon(property.type)" :stroke-width="1.8" /></span>
                    <span class="prop-row-name">{{ property.label }}</span>
                    <span class="prop-row-type">{{ propTypeLabel(property.type) }}</span>
                    <span class="prop-row-stat">
                      <span class="prop-row-cnt">{{ property.isOption ? `${property.optionCount} 项` : `${property.filledCount}/${property.totalCount}` }}</span>
                      <button
                        type="button"
                        class="prop-row-del"
                        :class="{ armed: isDeleteArmed(entry.topic.id, property.key) }"
                        :title="isDeleteArmed(entry.topic.id, property.key) ? '再次点击删除属性' : '删除属性'"
                        @click.stop="armOrDeleteProperty(entry.topic, property.key, $event)"
                      >
                        <TimelineLucideIcon name="trash" :stroke-width="1.8" />
                      </button>
                    </span>
                  </div>
                  <div v-if="property.isOption && property.options.length" class="prop-chips">
                    <button
                      v-for="option in property.options"
                      :key="option.value"
                      type="button"
                      class="prop-chip"
                      :class="{
                        active: entry.active && isOptionActive(property.key, option.value),
                        inactive: !entry.active,
                      }"
                      :disabled="!entry.active"
                      @click="filterPropertyOption(entry.topic.id, property.key, option.value)"
                    >
                      <span class="prop-chip-dot" :style="{ '--dot': option.color }"></span>
                      <span class="prop-chip-label">{{ option.label }}</span>
                    </button>
                  </div>
                </div>
                <button type="button" class="prop-add-row" @click="addProperty(entry.topic, $event)">
                  <span class="prop-add-ic"><TimelineLucideIcon name="plusSign" :stroke-width="1.8" /></span>
                  <span>添加属性</span>
                </button>
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

    <div
      v-if="editing"
      class="popover prop-pop"
      :style="{ left: editing.anchor.x + 'px', top: editing.anchor.y + 'px' }"
      @click.stop
    >
      <div class="prop-pop-head">
        <span class="prop-row-ic" :style="{ '--prop-tone': propertyTone(editing.column.type) }">
          <TimelineLucideIcon :name="propertyIcon(editing.column.type)" :stroke-width="1.8" />
        </span>
        <input
          ref="propNameRef"
          v-model="editing.column.label"
          class="prop-pop-name"
          type="text"
          maxlength="24"
          placeholder="属性名称"
        />
        <select
          v-if="canEditPropertyType(editing.topicId, editing.column)"
          class="prop-pop-type"
          :value="editing.column.type"
          title="属性类型"
          @change="updateDraftPropertyType(editing.column, $event.target.value)"
        >
          <option
            v-for="type in editablePropertyTypesFor(editing.column.type)"
            :key="type.value"
            :value="type.value"
            :disabled="type.legacy === true"
          >{{ type.label }}</option>
        </select>
        <span v-else class="prop-pop-type prop-pop-type-locked" title="已使用，类型锁定">{{ propTypeLabel(editing.column.type) }}</span>
      </div>

      <div v-if="isOptionProperty(editing.column.type)" class="prop-pop-opts">
        <div class="prop-pop-seclbl">选项</div>
        <div
          v-for="(option, optionIndex) in editing.column.options"
          :key="`${option.id || 'option'}-${optionIndex}`"
          class="prop-opt"
        >
          <label class="prop-opt-color" :title="`设置${option.label || '选项'}颜色`">
            <span class="prop-opt-dot" :style="{ '--dot': option.colorValue || option.pickerValue || optionColorValue('', optionIndex) }"></span>
            <input
              type="color"
              :value="option.pickerValue || optionColorValue(option.colorValue, optionIndex)"
              @input="updateDraftOptionColor(option, $event, optionIndex)"
            />
          </label>
          <input v-model="option.label" class="prop-opt-name" type="text" maxlength="24" placeholder="选项名称" />
          <span class="prop-opt-stat">
            <span class="prop-opt-cnt">{{ optionUsageCount(option) }}</span>
            <button type="button" class="prop-opt-del" title="删除选项" @click="removeDraftOption(editing.column, optionIndex)">
              <TimelineLucideIcon name="trash" :stroke-width="1.8" />
            </button>
          </span>
        </div>
        <button type="button" class="prop-opt-add" @click="addDraftOption(editing.column)">
          <TimelineLucideIcon name="plusSign" :stroke-width="1.8" />
          <span>添加</span>
        </button>
      </div>
    </div>
  </aside>
</template>
