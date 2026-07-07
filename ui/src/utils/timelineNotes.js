import { CONTENT_LIMITS } from "../constants/contentLimits.js";
import { plainTextFromMarkdown } from "./markdownPreview.js";
import { x6SnapshotToTree } from "./mindmapX6.js";

// Unified property model: every column is a property. Only the two structural
// columns (date + headline) are reserved; type/tags are ordinary, deletable
// properties seeded by default. Option-typed properties (select/multiselect)
// carry their own options; their values live in event.extra by option id.
const RESERVED_COLUMN_KEYS = new Set(["title", "time"]);
const COLUMN_KEY_PATTERN = /^[a-z][a-z0-9_]*$/;
const COLUMN_TYPES = new Set(["text", "number", "date", "checkbox", "url", "email", "phone", "select", "multiselect"]);
const OPTION_COLUMN_TYPES = new Set(["select", "multiselect"]);
const LINK_COLUMN_TYPES = new Set(["url", "email", "phone"]);
const CHECKBOX_TRUE = new Set(["true", "1", "yes", "on"]);
const SAMPLE_TEXT_LIMIT = 18;
const EDITABLE_PROPERTY_TYPE_VALUES = ["text", "number", "date", "checkbox", "url", "select", "multiselect"];

export const PROPERTY_TYPE_LABELS = {
  text: "文本",
  number: "数字",
  date: "日期",
  checkbox: "复选",
  url: "链接",
  email: "邮箱",
  phone: "电话",
  select: "单选",
  multiselect: "多选",
};

export function editablePropertyTypeChoices(currentType = "") {
  const base = EDITABLE_PROPERTY_TYPE_VALUES.map((value) => ({ value, label: PROPERTY_TYPE_LABELS[value] || value }));
  const normalized = String(currentType || "").trim();
  if (!normalized || EDITABLE_PROPERTY_TYPE_VALUES.includes(normalized) || !PROPERTY_TYPE_LABELS[normalized]) {
    return base;
  }
  return [...base, { value: normalized, label: `${PROPERTY_TYPE_LABELS[normalized]}（旧）`, legacy: true }];
}

export function isOptionColumn(column) {
  return OPTION_COLUMN_TYPES.has(column?.type);
}

export function isCheckboxColumn(column) {
  return column?.type === "checkbox";
}

export function isLinkColumn(column) {
  return LINK_COLUMN_TYPES.has(column?.type);
}

function normalizeMachineToken(value, fallback) {
  const ascii = String(value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^\x00-\x7F]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  if (!ascii) return fallback;
  return /^[a-z]/.test(ascii) ? ascii : `${fallback}_${ascii}`;
}

function buildUniqueMachineToken(seed, existing, fallback) {
  const base = normalizeMachineToken(seed, fallback);
  let candidate = base;
  let suffix = 2;
  while (existing.has(candidate) || RESERVED_COLUMN_KEYS.has(candidate)) {
    candidate = `${base}_${suffix}`;
    suffix += 1;
  }
  return candidate;
}

export function buildPropertyKey(seed, existingKeys = []) {
  const existing = new Set((Array.isArray(existingKeys) ? existingKeys : []).map((value) => String(value || "").trim()).filter(Boolean));
  return buildUniqueMachineToken(seed, existing, "property");
}

export function buildOptionId(seed, existingIds = []) {
  const existing = new Set((Array.isArray(existingIds) ? existingIds : []).map((value) => String(value || "").trim()).filter(Boolean));
  return buildUniqueMachineToken(seed, existing, "option");
}

// Single source for property-type → glyph (Notion-style metadata icons), shared
// by the detail pane (propertyIcon) and the column-config popover so the two can
// never drift. Unknown/text falls back to alignLeft.
export const PROPERTY_TYPE_ICONS = {
  text: "alignLeft",
  number: "hash",
  date: "calendar",
  checkbox: "checkSquare",
  url: "link",
  email: "mail",
  phone: "phone",
  select: "type",
  multiselect: "list",
};

export function propertyTypeIcon(type) {
  return PROPERTY_TYPE_ICONS[type] || PROPERTY_TYPE_ICONS.text;
}

export function isCheckboxChecked(value) {
  return value === true || CHECKBOX_TRUE.has(String(value ?? "").trim().toLowerCase());
}

// Safe href for link-typed property values. url gets an https:// prefix when it
// lacks an http(s) scheme (which also neutralizes javascript:/data: payloads);
// email → mailto:, phone → tel:. Empty value yields "" (caller renders plain).
export function propertyHref(type, value) {
  const raw = String(value ?? "").trim();
  if (!raw) return "";
  if (type === "email") return `mailto:${raw}`;
  if (type === "phone") return `tel:${raw.replace(/[^\d+]/g, "")}`;
  if (type === "url") return /^https?:\/\//i.test(raw) ? raw : `https://${raw.replace(/^\/+/, "")}`;
  return "";
}

function extractYearLabel(isoDate) {
  const match = String(isoDate || "").match(/^-?\d+/);
  return match ? match[0] : "";
}

function padTwo(value) {
  return String(value || 0).padStart(2, "0");
}

function htmlToPlainText(source) {
  const raw = String(source || "");
  if (!raw) return "";
  if (typeof document === "undefined") {
    return raw
      .replace(/<[^>]*>/g, " ")
      .replace(/&nbsp;/gi, " ")
      .replace(/\s+/g, " ")
      .trim();
  }
  const el = document.createElement("div");
  el.innerHTML = raw;
  return (el.textContent || "").replace(/\s+/g, " ").trim();
}

function clampNumber(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function defaultBodyFromItems(items) {
  return (items || [])
    .map((item) => String(item?.text || "").trim())
    .filter(Boolean)
    .join("\n\n");
}

function buildMonthRangeLabel(items) {
  const months = [
    ...new Set(
      (items || [])
        .map((event) => event?.dateParts?.month)
        .filter((month) => typeof month === "number")
        .sort((left, right) => left - right)
    ),
  ];

  if (months.length === 0) return "";
  if (months.length === 1) return `${months[0]}月`;
  return `${months[0]}-${months[months.length - 1]}月`;
}

function normalizeColumnWidth(width, fallback = 96) {
  const next = Number.parseInt(width, 10);
  if (!Number.isFinite(next)) return fallback;
  return clampNumber(next, 72, 220);
}

export function clampTimelineColumnWidth(width, fallback = 96) {
  return normalizeColumnWidth(width, fallback);
}

function normalizeColumnOrder(order, fallbackIndex) {
  const next = Number.parseInt(order, 10);
  return Number.isFinite(next) ? next : fallbackIndex;
}

function normalizeColumnLabel(label) {
  return String(label || "").trim().slice(0, 24);
}

function normalizeColumnOptions(options, type) {
  if (!OPTION_COLUMN_TYPES.has(type) || !Array.isArray(options)) return [];
  const seen = new Set();
  const normalized = [];
  for (const option of options) {
    const id = String(option?.id || "").trim();
    if (!id || seen.has(id)) continue;
    seen.add(id);
    normalized.push({
      id: id.slice(0, 48),
      label: (String(option?.label || "").trim() || id).slice(0, 24),
      color: String(option?.color || "").trim().slice(0, 32),
    });
  }
  return normalized;
}

export function compareTimelineEvents(left, right) {
  const leftHasDate = eventHasDate(left);
  const rightHasDate = eventHasDate(right);
  if (leftHasDate !== rightHasDate) return leftHasDate ? -1 : 1;
  const leftKey = !leftHasDate
    ? Number.MAX_SAFE_INTEGER * 2
    : left?.era === "更早"
      ? Number.MAX_SAFE_INTEGER + (left?.dateKey || 0)
      : left?.dateKey || 0;
  const rightKey = !rightHasDate
    ? Number.MAX_SAFE_INTEGER * 2
    : right?.era === "更早"
      ? Number.MAX_SAFE_INTEGER + (right?.dateKey || 0)
      : right?.dateKey || 0;
  return leftKey - rightKey || (left?.id || 0) - (right?.id || 0);
}

export function buildTopicRange(topic) {
  const minYear = extractYearLabel(topic?.minDate);
  const maxYear = extractYearLabel(topic?.maxDate);
  if (!minYear || !maxYear) return "暂无时间范围";
  return `${minYear} - ${maxYear}`;
}

export function buildTopicMetaLine(topic) {
  return buildTopicRange(topic);
}

// Year label with BC support: negative years → "公元前N", positive → "N".
// Shared by the timeline (compact) and detail (CJK) date formatters.
function formatYearLabel(year) {
  const value = Number(year);
  if (!Number.isFinite(value)) return String(year ?? "");
  return value < 0 ? `公元前${-value}` : String(value);
}

// Timeline (compact) date. Year-only events — month 1 & day 1, which is also the
// migration default for year-precision data — collapse to just the year so the
// 编年 spine never shows fabricated "-01-01" day precision. Genuine 1st-of-month
// dates (e.g. 1927-08-01 南昌起义) keep their full date: month-precision data is
// stored the same way and can't be told apart, so we never coarsen a real day.
export function formatEventDate(event) {
  if (!eventHasDate(event)) return "";
  const parts = event?.dateParts;
  if (parts && parts.year != null) {
    if (parts.month === 1 && parts.day === 1) return formatYearLabel(parts.year);
    // BC dates have no clean compact ISO ("-551-09-28" reads as broken) — use the
    // CJK form, matching the detail pane. AD keeps the compact ISO below.
    if (parts.year < 0) return `${formatYearLabel(parts.year)}年${parts.month}月${parts.day}日`;
  }
  if (event?.isoDate) return event.isoDate;
  if (!parts) return "";
  return `${parts.year ?? ""}-${padTwo(parts.month)}-${padTwo(parts.day)}`;
}

// Detail-pane (CJK) date, precision-aware like formatEventDate: year-only →
// "1840年"; otherwise full "1921年7月23日". BC years render as "公元前N年".
export function formatEventDisplayDate(event) {
  if (!eventHasDate(event)) return event?.displayLabel || "未定时间";
  const parts = event?.dateParts;
  if (!parts || parts.year == null) return event?.displayLabel || "";
  const yearLabel = `${formatYearLabel(parts.year)}年`;
  if (parts.month === 1 && parts.day === 1) return yearLabel;
  return `${yearLabel}${parts.month}月${parts.day}日`;
}

const EVENT_PREVIEW_CACHE = new Map();
const EVENT_PREVIEW_CACHE_LIMIT = 2000;

function previewCacheKey(event, maxLength) {
  const id = event?.id;
  if (id == null) return "";
  const stamp = String(event?.updatedAt || event?.createdAt || "");
  const preview = String(event?.preview || "").trim();
  return preview ? `${id}|${stamp}|${maxLength}|${preview}` : `${id}|${stamp}|${maxLength}|fallback`;
}

export function buildEventPreview(event, maxLength = CONTENT_LIMITS.previewText) {
  const cacheKey = previewCacheKey(event, maxLength);
  if (cacheKey && EVENT_PREVIEW_CACHE.has(cacheKey)) return EVENT_PREVIEW_CACHE.get(cacheKey);
  const text =
    String(event?.preview || "").trim() ||
    mindmapPlainText(event?.bodyJson) ||
    plainTextFromMarkdown(event?.bodyMarkdown) ||
    (event?.items || [])
      .map((item) => String(item?.text || "").trim())
      .filter(Boolean)
      .join(" ");
  const result = text.length <= maxLength ? text : `${text.slice(0, maxLength).trim()}...`;
  if (cacheKey) {
    EVENT_PREVIEW_CACHE.set(cacheKey, result);
    if (EVENT_PREVIEW_CACHE.size > EVENT_PREVIEW_CACHE_LIMIT) {
      EVENT_PREVIEW_CACHE.delete(EVENT_PREVIEW_CACHE.keys().next().value);
    }
  }
  return result;
}

export function normalizeTopicColumns(columns) {
  const seen = new Set();
  return (Array.isArray(columns) ? columns : [])
    .map((column, index) => {
      const key = String(column?.key || "").trim();
      const type = String(column?.type || "text").trim();
      const normalizedType = COLUMN_TYPES.has(type) ? type : "text";
      const label = normalizeColumnLabel(column?.label);
      if (!COLUMN_KEY_PATTERN.test(key) || RESERVED_COLUMN_KEYS.has(key) || seen.has(key) || !label) {
        return null;
      }
      seen.add(key);
      return {
        key,
        label,
        type: normalizedType,
        width: normalizeColumnWidth(column?.width, 96),
        order: normalizeColumnOrder(column?.order, index),
        visible: column?.visible !== false,
        options: normalizeColumnOptions(column?.options, normalizedType),
      };
    })
    .filter(Boolean)
    .sort((left, right) => left.order - right.order || left.label.localeCompare(right.label));
}

// Serialize the column-config popover draft into a persistable payload. Rows with
// both key+label save as-is; completely blank rows are ignored; partially edited
// existing rows fall back to their last persisted key/label (via `persistedKey`)
// so a transient blank while renaming never deletes the column on autosave.
export function serializeTopicColumnsDraft(columns, persistedColumns = []) {
  const draftList = Array.isArray(columns) ? columns : [];
  const persistedByKey = new Map(normalizeTopicColumns(persistedColumns).map((column) => [column.key, column]));
  const keyCounts = draftList.reduce((counts, column) => {
    const key = String(column?.key || "").trim();
    if (!key) return counts;
    counts.set(key, (counts.get(key) || 0) + 1);
    return counts;
  }, new Map());
  return draftList
    .map((column, index) => {
      const key = String(column?.key || "").trim();
      const label = String(column?.label || "").trim();
      const persistedKey = String(column?.persistedKey || "").trim();
      const fallback = persistedByKey.get(persistedKey);
      if (!key && !label && !persistedKey) return null;
      const keyIsUnsafe = !COLUMN_KEY_PATTERN.test(key) || RESERVED_COLUMN_KEYS.has(key) || (keyCounts.get(key) || 0) > 1;
      if (key && label && !keyIsUnsafe) {
        return {
          key,
          label,
          type: String(column?.type || "text"),
          width: clampTimelineColumnWidth(column?.width, 96),
          order: Number(column?.order ?? index),
          visible: column?.visible !== false,
          options: Array.isArray(column?.options) ? column.options : [],
        };
      }
      if (!fallback) return null;
      return {
        key: fallback.key,
        label: fallback.label,
        type: String(column?.type || fallback.type || "text"),
        width: clampTimelineColumnWidth(column?.width, fallback.width || 96),
        order: Number(column?.order ?? fallback.order ?? index),
        visible: column?.visible !== false,
        options: Array.isArray(column?.options) ? column.options : fallback.options || [],
      };
    })
    .filter(Boolean);
}

// Time-column track width (px). Compact by default — AD dates render as short
// ISO/year ("1921-07-23" ≈ 65px). BC dates carrying a real month/day use the long
// CJK form ("公元前551年9月28日" ≈ 117px) and would overflow the compact track into
// the title, so a set holding one widens to the WIDE track. The `.c-time` clip +
// title tooltip still backstop the rare 4-digit-BC / test-data extremes (≥131px).
export const TIME_COLUMN_WIDTH = 96;
export const TIME_COLUMN_WIDTH_WIDE = 128;

export function timelineTimeColumnWidth(events) {
  const hasLongDate = (Array.isArray(events) ? events : []).some((event) => {
    const parts = event?.dateParts;
    return parts && parts.year != null && parts.year < 0 && !(parts.month === 1 && parts.day === 1);
  });
  return hasLongDate ? TIME_COLUMN_WIDTH_WIDE : TIME_COLUMN_WIDTH;
}

// `titleWidth` is null by default → the 事件 column stays the flex track that
// fills remaining space (today's look). Once the user drags it to a pixel width
// it becomes fixed and a trailing flex spacer (added in the grid template) takes
// over absorbing slack so the star stays pinned right.
export function buildVisibleTimelineColumns(columns, hiddenKeys = null, timeWidth = TIME_COLUMN_WIDTH, titleWidth = null) {
  const properties = normalizeTopicColumns(columns).filter((column) => column.visible);
  const hidden = hiddenKeys instanceof Set ? hiddenKeys : Array.isArray(hiddenKeys) ? new Set(hiddenKeys) : null;
  const shown = hidden ? properties.filter((column) => !hidden.has(column.key)) : properties;
  return [
    { key: "time", label: "时间", width: timeWidth, builtIn: true, type: "time" },
    { key: "title", label: "事件", width: titleWidth, builtIn: true, type: "title" },
    ...shown,
  ];
}

export function buildTimelineGridTemplate(columns, hiddenKeys = null, timeWidth = TIME_COLUMN_WIDTH, titleWidth = null) {
  const tracks = buildVisibleTimelineColumns(columns, hiddenKeys, timeWidth, titleWidth).map((column) =>
    column.width ? `${column.width}px` : "minmax(0,1fr)"
  );
  // Guarantee exactly one flexible track: when every real column is pixel-fixed
  // (the title was pinned), append a flex spacer before the trailing star slot.
  const middle = tracks.includes("minmax(0,1fr)") ? tracks : [...tracks, "minmax(0,1fr)"];
  return ["28px", ...middle, "30px"].join(" ");
}

// True when the grid template carries the extra trailing flex spacer (i.e. the
// title is pinned) — the feed renders one matching empty cell before the star.
export function timelineHasTrailingSpacer(columns, hiddenKeys = null, titleWidth = null) {
  return titleWidth != null && Number.isFinite(Number(titleWidth));
}

// Display views (axis 1) = different layouts of the SAME entry data. W2 shipped
// timeline/table/list; W3 adds board/gallery/outline. `requires` is the tooltip
// shown when a view is capability-gated off. The backend is the SSOT for which
// views are enabled (services/timeline.py `topic_capabilities` sends the live
// `capabilities` set in the topic meta) — these maps only add presentation
// metadata (icon/label) and the implemented-view gate, never re-derive capability
// from a per-event scan. See docs/note-types-and-views-design.md.
export const DEFAULT_DISPLAY_STYLE = "timeline";
export const DISPLAY_VIEW_META = {
  timeline: { label: "时间线", icon: "timeline", requires: "需要带日期的笔记" },
  table: { label: "表格", icon: "table", requires: "" },
  board: { label: "看板", icon: "board", requires: "需要一个单选或多选属性" },
  gallery: { label: "画廊", icon: "gallery", requires: "需要带配图的笔记" },
  list: { label: "列表", icon: "list", requires: "" },
  outline: { label: "大纲", icon: "outline", requires: "需要笔记内容" },
};
export const IMPLEMENTED_DISPLAY_STYLES = ["timeline", "table", "board", "gallery", "list", "outline"];

// Board (axis-1 kanban) groups entries by one option property. Auto-pick the
// first visible select column (single value → one card per column), else the
// first visible option column (a multiselect card can appear under each of its
// values). Null when the notebook has no option property — the backend gates the
// `board` capability on exactly this, so the view is unreachable in that case.
export function pickBoardColumn(columns) {
  const options = normalizeTopicColumns(columns).filter((column) => column.visible && isOptionColumn(column));
  return options.find((column) => column.type === "select") || options[0] || null;
}

// Sentinel bucket id for board cards whose grouping property is empty/cleared.
export const BOARD_UNASSIGNED_ID = "__unassigned__";

// Bucket events into board columns by `column`'s options, in option order. Bucket
// order (by option) never changes; only the within-bucket order follows `sort`
// ({ field, dir }, default chronological). A multiselect event joins every matching
// bucket; an event with no defined-option value falls into a trailing 未分类 bucket
// shown only when non-empty. Option buckets always render (stable board shape).
export function buildBoardGroups(events, column, sort = null) {
  if (!isOptionColumn(column)) return [];
  const list = Array.isArray(events) ? events : [];
  const buckets = new Map();
  for (const option of column.options || []) {
    buckets.set(option.id, { id: option.id, label: option.label, color: option.color || "var(--accent)", items: [] });
  }
  const unassigned = { id: BOARD_UNASSIGNED_ID, label: "未分类", color: "var(--border-strong)", items: [] };
  for (const event of list) {
    // Dedup membership: a malformed multiselect value (a repeated option id that
    // slipped past normalize_extra) must not push the same card into one bucket
    // twice — that would also collide the `${bucket.id}:${event.id}` v-for key.
    const seen = new Set();
    let matchedAny = false;
    for (const chip of resolvePropertyChips(event, column)) {
      if (!buckets.has(chip.value) || seen.has(chip.value)) continue;
      seen.add(chip.value);
      buckets.get(chip.value).items.push(event);
      matchedAny = true;
    }
    if (!matchedAny) unassigned.items.push(event);
  }
  const ordered = [...buckets.values()];
  if (unassigned.items.length) ordered.push(unassigned);
  const comparator = sort ? compareEventsBySort(sort) : compareTimelineEvents;
  for (const bucket of ordered) bucket.items.sort(comparator);
  return ordered;
}

// --- Mindmap (note_type=mindmap) ------------------------------------------
// body_json is backward-compatible across three shapes:
// 1. legacy bare tree ({ data, children })
// 2. simple-mind-map snapshot ({ root, layout, theme, view })
// 3. X6 snapshot ({ _fmt:"x6-mindmap-v1", cells, background, view, layout })
// Return a normalized root tree ({ data, children }) from any supported shape.
export function mindmapRootData(value) {
  if (!value || typeof value !== "object") return null;
  const x6Tree = x6SnapshotToTree(value);
  if (x6Tree) return x6Tree;
  const root = value.root && typeof value.root === "object" ? value.root : value;
  if (!root || typeof root !== "object" || !root.data || typeof root.data !== "object") return null;
  return root;
}

export function mindmapPlainText(value) {
  const root = mindmapRootData(value);
  if (!root) return "";
  const parts = [];
  const visit = (node) => {
    if (!node || typeof node !== "object") return;
    const data = node.data && typeof node.data === "object" ? node.data : {};
    const tags = Array.isArray(data.tag) ? data.tag.map((item) => String(item || "").trim()).filter(Boolean).join(" ") : "";
    [data.text, data.note, data.hyperlink, tags]
      .map((item) => htmlToPlainText(item))
      .filter(Boolean)
      .forEach((item) => parts.push(item));
    (Array.isArray(node.children) ? node.children : []).forEach(visit);
  };
  visit(root);
  return parts.join(" ").replace(/\s+/g, " ").trim();
}

export function eventHasDate(event) {
  if (event?.hasDate === false) return false;
  if (event?.dateKey != null) return true;
  return Number.isInteger(event?.dateParts?.year);
}

// Count nodes in a normalized mindmap tree (root + descendants).
export function countMindmapNodes(rootNode) {
  if (!rootNode || typeof rootNode !== "object") return 0;
  const children = Array.isArray(rootNode.children) ? rootNode.children : [];
  return children.reduce((sum, child) => sum + countMindmapNodes(child), 1);
}

// Layout presets surfaced in the X6 mindmap toolbar. "free" keeps manual
// coordinates untouched; the others reflow the existing tree into a preset.
export const DEFAULT_MINDMAP_LAYOUT = "free";
export const MINDMAP_LAYOUTS = [
  { key: "free", label: "自由布局" },
  { key: "logicalStructure", label: "逻辑结构（右）" },
  { key: "logicalStructureLeft", label: "逻辑结构（左）" },
  { key: "organizationStructure", label: "组织结构" },
];

// Container types (axis 0, "数字图书馆"): each presets an ORDERED view set (first =
// default) and a left-tree icon. Mirrors backend CONTAINER_TYPE_VIEWS
// (services/timeline.py); the FE keeps a copy for optimistic type switches.
export const CONTAINER_TYPES = [
  { key: "notebook", label: "笔记本", icon: "notebook" },
  { key: "book", label: "书籍", icon: "book" },
  { key: "album", label: "相册", icon: "image" },
];
const CONTAINER_TYPE_MAP = new Map(CONTAINER_TYPES.map((item) => [item.key, item]));
export const CONTAINER_TYPE_VIEWS = {
  notebook: ["timeline", "list", "outline", "table", "board"],
  book: ["outline", "table", "list", "timeline", "gallery"],
  album: ["gallery", "board"],
};

export function normalizeContainerType(type) {
  const key = String(type || "").trim();
  return CONTAINER_TYPE_MAP.has(key) ? key : "notebook";
}

export function containerTypeIcon(type) {
  return CONTAINER_TYPE_MAP.get(normalizeContainerType(type)).icon;
}

export function containerTypeViews(type) {
  return [...CONTAINER_TYPE_VIEWS[normalizeContainerType(type)]];
}

// Implemented views for the switcher, each flagged enabled per the backend
// capability set. Unknown/empty capabilities → all enabled (backward compatible
// with payloads predating the capability field).
export function availableDisplayViews(capabilities) {
  const known = Array.isArray(capabilities) && capabilities.length ? new Set(capabilities) : null;
  return IMPLEMENTED_DISPLAY_STYLES.map((key) => ({
    key,
    label: DISPLAY_VIEW_META[key].label,
    icon: DISPLAY_VIEW_META[key].icon,
    requires: DISPLAY_VIEW_META[key].requires,
    enabled: known ? known.has(key) : true,
  }));
}

// Effective view to render: the persisted style if it's implemented AND currently
// capable, else the first usable implemented view (table/list are always capable).
// Guards a persisted board/gallery/outline (set via API or a later wave) and a
// timeline notebook that has no dated events.
export function resolveDisplayStyle(style, capabilities) {
  const known = Array.isArray(capabilities) && capabilities.length ? new Set(capabilities) : null;
  const usable = (key) => IMPLEMENTED_DISPLAY_STYLES.includes(key) && (!known || known.has(key));
  if (style && usable(style)) return style;
  return IMPLEMENTED_DISPLAY_STYLES.find(usable) || DEFAULT_DISPLAY_STYLE;
}

// --- Center-column sort (docs/center-sort-design.md) -----------------------
// Sort is an ORDERED LIST of { field, dir } levels: the first is primary, the rest
// are tiebreakers (multi-level sort). Direction is universal, fields are clamped
// per view. Default = a single time-asc level = today's behavior (zero change).
export const DEFAULT_SORT = [{ field: "time", dir: 1 }];
export const SORT_FIELD_META = {
  time: { label: "时间", icon: "calendar" },
  title: { label: "标题", icon: "type" },
  created: { label: "创建时间", icon: "clock" },
  updated: { label: "更新时间", icon: "clock" },
  favorited: { label: "收藏时间", icon: "star" },
};
const BUILTIN_SORT_FIELDS = new Set(["time", "title", "created", "updated", "favorited"]);
const TIMESTAMP_SORT_KEYS = { created: "createdAt", updated: "updatedAt", favorited: "favoriteAt" };
const TITLE_SORT_COLUMN = { key: "title" };

function normalizeSortDir(dir) {
  return Number(dir) < 0 ? -1 : 1;
}

// Coerce any sort input (a single { field, dir }, a level array, or junk) into a
// clean ordered level list: each field appears once, dirs normalized, always ≥1
// level. Accepts the legacy single-object shape so old persisted sorts upgrade.
export function normalizeSortLevels(sort) {
  const raw = Array.isArray(sort) ? sort : sort ? [sort] : [];
  const seen = new Set();
  const levels = [];
  for (const level of raw) {
    const field = String(level?.field || "time");
    if (seen.has(field)) continue;
    seen.add(field);
    levels.push({ field, dir: normalizeSortDir(level?.dir) });
  }
  return levels.length ? levels : [{ field: "time", dir: 1 }];
}

export function isDefaultSort(sort) {
  const levels = normalizeSortLevels(sort);
  return levels.length === 1 && levels[0].field === "time" && levels[0].dir === 1;
}

// Move the sort level at index `from` to index `to`, returning a new normalized
// level list (the moved field keeps its direction). Order is priority, so
// promoting a level toward index 0 makes it the primary key. Non-finite or equal
// indices are a no-op; out-of-range indices clamp into range. Drives the
// drag-to-reorder handle in the multi-sort editor.
export function reorderSortLevels(sort, from, to) {
  const levels = normalizeSortLevels(sort);
  const src = Number(from);
  const dst = Number(to);
  if (!Number.isFinite(src) || !Number.isFinite(dst)) return levels;
  const max = levels.length - 1;
  const a = Math.max(0, Math.min(max, Math.trunc(src)));
  const b = Math.max(0, Math.min(max, Math.trunc(dst)));
  if (a === b) return levels;
  const next = levels.slice();
  const [moved] = next.splice(a, 1);
  next.splice(b, 0, moved);
  return next;
}

function sortTimestamp(event, field) {
  const raw = event?.[TIMESTAMP_SORT_KEYS[field]];
  const time = raw ? Date.parse(raw) : Number.NaN;
  return Number.isFinite(time) ? time : null;
}

// A builtin sort field "has a value" for the sink partition: title always does
// (fallback name); timestamps sink when absent so `time desc` / `created desc`
// never float a value-less row to the top.
function builtinFieldHasValue(event, field) {
  if (field === "title") return true;
  return sortTimestamp(event, field) != null;
}

// time rank: real-dated events sort by dateKey; the 「更早」 catch-all bucket and
// undated notes ALWAYS sink below them — in BOTH directions (never a naive * -1),
// so reversing the timeline reorders only the real-dated span.
function timeSortRank(event) {
  if (!eventHasDate(event)) return { sunk: true, key: Number.MAX_SAFE_INTEGER };
  if (event?.era === "更早") return { sunk: true, key: Number.MAX_SAFE_INTEGER - 1 };
  return { sunk: false, key: event?.dateKey || 0 };
}

// Per-LEVEL comparators return that field's order (sink-aware, direction-applied)
// and 0 when two events tie on the field — NO id tiebreak, so the next level can
// break the tie. compareEventsBySort chains them and applies one id tiebreak last.
function timeLevelCompare(dir) {
  return (a, b) => {
    const ra = timeSortRank(a);
    const rb = timeSortRank(b);
    if (ra.sunk !== rb.sunk) return ra.sunk ? 1 : -1;
    // Sunk events (「更早」 bucket, undated) never reverse — keep them chronological
    // by dateKey (legacy compareTimelineEvents order) so the default stays today's.
    if (ra.sunk) return ra.key - rb.key || (a?.dateKey || 0) - (b?.dateKey || 0);
    return (ra.key - rb.key) * dir;
  };
}

function builtinLevelCompare(field, dir) {
  return (a, b) => {
    const ha = builtinFieldHasValue(a, field);
    const hb = builtinFieldHasValue(b, field);
    if (ha !== hb) return ha ? -1 : 1;
    if (!ha) return 0;
    const primary =
      field === "title"
        ? String(eventColumnValue(a, TITLE_SORT_COLUMN)).localeCompare(String(eventColumnValue(b, TITLE_SORT_COLUMN)), "zh")
        : (sortTimestamp(a, field) || 0) - (sortTimestamp(b, field) || 0);
    return primary * dir;
  };
}

// Custom column level (unchanged table semantics): checkbox → checked-first,
// otherwise the localized rendered value; empties render "—" and sort as such.
function columnLevelCompare(column, dir) {
  return (a, b) => {
    if (column.type === "checkbox") {
      return ((isCheckboxChecked(b?.extra?.[column.key]) ? 1 : 0) - (isCheckboxChecked(a?.extra?.[column.key]) ? 1 : 0)) * dir;
    }
    return String(eventColumnValue(a, column)).localeCompare(String(eventColumnValue(b, column)), "zh") * dir;
  };
}

function levelComparator(level, columns) {
  const field = String(level?.field || "time");
  const dir = normalizeSortDir(level?.dir);
  if (field === "time") return timeLevelCompare(dir);
  if (BUILTIN_SORT_FIELDS.has(field)) return builtinLevelCompare(field, dir);
  const column = normalizeTopicColumns(columns).find((col) => col.key === field);
  // Deleted-column safety (clamp normally prevents this): fall back to time.
  return column ? columnLevelCompare(column, dir) : timeLevelCompare(dir);
}

// Build the active comparator from a sort level list: chain the per-level
// comparators (first non-zero wins), closed by a stable id tiebreak.
export function compareEventsBySort(sort, columns = []) {
  const comparators = normalizeSortLevels(sort).map((level) => levelComparator(level, columns));
  return (a, b) => {
    for (const compare of comparators) {
      const result = compare(a, b);
      if (result) return result;
    }
    return (a?.id || 0) - (b?.id || 0);
  };
}

function sortFieldEntry(field) {
  return { field, label: SORT_FIELD_META[field].label, icon: SORT_FIELD_META[field].icon };
}

// Which fields a view may sort by (docs §4). Each view only promises dimensions it
// can show: cross-notebook favorites (rendered flat) → time/title/收藏时间; grouped
// views (timeline/outline) → time only; table → time/title + every visible custom
// column (real headers, so a caret always exists); list/gallery/board → the four
// universal fields (no custom columns, which those cards don't surface).
export function sortFieldsForView(view, columns = [], favorites = false) {
  if (favorites) return ["time", "title", "favorited"].map(sortFieldEntry);
  if (view === "timeline" || view === "outline") return [sortFieldEntry("time")];
  if (view === "table") {
    const fields = [sortFieldEntry("time"), sortFieldEntry("title")];
    for (const column of normalizeTopicColumns(columns).filter((col) => col.visible)) {
      fields.push({ field: column.key, label: column.label, icon: propertyTypeIcon(column.type), custom: true });
    }
    return fields;
  }
  return ["time", "title", "created", "updated"].map(sortFieldEntry);
}

// Direction universal, fields clamped per view: keep each level's dir, drop levels
// whose field the view can't sort (collapsing them onto time, then deduping), so a
// table multi-sort degrades to a single time level on a grouped view. Always ≥1.
export function clampSortForView(sort, view, columns = [], favorites = false) {
  const allowed = new Set(sortFieldsForView(view, columns, favorites).map((entry) => entry.field));
  const seen = new Set();
  const levels = [];
  for (const level of normalizeSortLevels(sort)) {
    const field = allowed.has(level.field) ? level.field : "time";
    if (seen.has(field)) continue;
    seen.add(field);
    levels.push({ field, dir: level.dir });
  }
  return levels.length ? levels : [{ field: "time", dir: 1 }];
}

// A property column "has a value" for an event when the row renders something
// other than the "—" placeholder for it (option chip, checked box, or non-blank
// text/number/link). Mirrors the per-type rendering in `eventColumnValue` and
// the center-pane template so the two never disagree.
export function eventColumnHasValue(event, column) {
  if (!column || column.builtIn) return true;
  if (isOptionColumn(column)) return resolvePropertyChips(event, column).length > 0;
  if (column.type === "checkbox") return isCheckboxChecked(event?.extra?.[column.key]);
  return String(event?.extra?.[column.key] ?? "").trim() !== "";
}

// Keys of visible property columns that are empty across the WHOLE event set
// (no row renders a value). The center timeline auto-hides these so an unused
// column never shows as a full column of "—"; the column config still lists
// them, and a column reappears the moment any event gets a value. Computed over
// all topic events (not the filtered view) so it never flickers on filter/search.
export function emptyTimelineColumnKeys(columns, events) {
  const list = Array.isArray(events) ? events : [];
  return normalizeTopicColumns(columns)
    .filter((column) => column.visible && !list.some((event) => eventColumnHasValue(event, column)))
    .map((column) => column.key);
}

export function buildGlobalFavoriteEvents(events) {
  return [...(events || [])]
    .filter((event) => event?.favorite && !event?.deletedAt)
    .sort(compareTimelineEvents);
}

function favoriteRecencyTimestamp(event) {
  const raw = event?.favoriteAt || event?.updatedAt || event?.createdAt || "";
  const time = raw ? Date.parse(raw) : Number.NaN;
  return Number.isFinite(time) ? time : 0;
}

export function buildRecentFavoriteEvents(events, limit = 5) {
  return [...(events || [])]
    .sort((left, right) => favoriteRecencyTimestamp(right) - favoriteRecencyTimestamp(left) || compareTimelineEvents(left, right))
    .slice(0, Math.max(0, Number(limit) || 0));
}

function favoriteFacetColumns(topics) {
  return new Map(
    (Array.isArray(topics) ? topics : []).map((topic) => [
      Number(topic?.id),
      new Map(normalizeTopicColumns(topic?.columns).map((column) => [column.key, column])),
    ])
  );
}

function favoriteFacetEntries(event, facetKey, columnsByTopic) {
  const topicColumns = columnsByTopic.get(Number(event?.topicId)) || new Map();
  const column = topicColumns.get(facetKey);
  if (facetKey === "tags") {
    if (column && isOptionColumn(column)) return resolvePropertyChips(event, column);
    const raw = event?.extra?.tags;
    const values = Array.isArray(raw) ? raw : raw ? [raw] : [];
    return values
      .map((value) => String(value || "").trim())
      .filter(Boolean)
      .map((value) => ({ value, label: value, color: "var(--accent)" }));
  }
  if (facetKey === "type") {
    if (column && isOptionColumn(column)) return resolvePropertyChips(event, column);
    const value = String(event?.extra?.type ?? "").trim();
    return value ? [{ value, label: value, color: "var(--accent)" }] : [];
  }
  return [];
}

export function buildFavoriteFacetRows(events, topics, facetKey) {
  const counts = new Map();
  const columnsByTopic = favoriteFacetColumns(topics);
  const topicNames = new Map((Array.isArray(topics) ? topics : []).map((topic) => [Number(topic?.id), topic?.title || topic?.name || `笔记本 ${topic?.id}`]));
  for (const event of Array.isArray(events) ? events : []) {
    for (const entry of favoriteFacetEntries(event, facetKey, columnsByTopic)) {
      const topicId = Number(event?.topicId) || null;
      const scopedKey = `${topicId}:${entry.value}`;
      const existing = counts.get(scopedKey) || {
        key: scopedKey,
        topicId,
        value: entry.value,
        label: entry.label,
        color: entry.color || "var(--accent)",
        count: 0,
      };
      existing.count += 1;
      if (!existing.label && entry.label) existing.label = entry.label;
      if (existing.color === "var(--accent)" && entry.color) existing.color = entry.color;
      counts.set(scopedKey, existing);
    }
  }
  const rows = [...counts.values()];
  const duplicateCounts = rows.reduce((map, row) => {
    map.set(row.label, (map.get(row.label) || 0) + 1);
    return map;
  }, new Map());
  return rows
    .map((row) => ({
      ...row,
      displayLabel:
        (duplicateCounts.get(row.label) || 0) > 1 && row.topicId != null ? `${row.label} · ${topicNames.get(row.topicId) || row.topicId}` : row.label,
    }))
    .sort((left, right) => right.count - left.count || left.displayLabel.localeCompare(right.displayLabel, "zh-CN"));
}

export function filterFavoriteEventsByScope(events, scope = {}, topics = [], activeTopicId = null) {
  const list = Array.isArray(events) ? [...events] : [];
  const kind = String(scope?.kind || "all");
  if (kind === "current-topic") return list.filter((event) => Number(event?.topicId) === Number(activeTopicId));
  if (kind === "recent") return buildRecentFavoriteEvents(list, 5);
  if (kind === "topic") return list.filter((event) => Number(event?.topicId) === Number(scope?.topicId));
  if (kind === "type" || kind === "tag") {
    const facetKey = kind === "type" ? "type" : "tags";
    const target = String(scope?.value || "").trim();
    const targetTopicId = scope?.topicId == null ? null : Number(scope.topicId);
    if (!target) return list;
    const columnsByTopic = favoriteFacetColumns(topics);
    return list.filter((event) =>
      favoriteFacetEntries(event, facetKey, columnsByTopic).some(
        (entry) => String(entry.value) === target && (targetTopicId == null || Number(event?.topicId) === targetTopicId)
      )
    );
  }
  return list;
}

export function optionMeta(column, id) {
  const found = (column?.options || []).find((option) => option.id === id);
  return found || { id, label: id, color: "var(--accent)" };
}

// Resolve an event's value(s) for a select/multiselect property into renderable
// chips. Unknown ids fall back to showing the raw id (no fabricated label).
export function resolvePropertyChips(event, column) {
  if (!isOptionColumn(column)) return [];
  const raw = event?.extra?.[column.key];
  const ids = column.type === "multiselect" ? (Array.isArray(raw) ? raw : []) : raw ? [raw] : [];
  return ids
    .map((id) => String(id || "").trim())
    .filter(Boolean)
    .map((id) => {
      const meta = optionMeta(column, id);
      return { value: id, label: meta.label, color: meta.color || "var(--accent)" };
    });
}

// Flat list/gallery cards show one combined chip set (the timeline shows chips
// per column). Aggregate an event's chips across every visible option column, in
// column order (empty columns simply contribute no chips) — same source as the
// feed so a card never invents or hides tags. `hiddenKeys` drops the feed's
// auto-hidden empty columns up front.
export function aggregateOptionChips(event, columns, hiddenKeys = []) {
  const hidden = new Set(Array.isArray(hiddenKeys) ? hiddenKeys : []);
  return (Array.isArray(columns) ? columns : [])
    .filter((column) => column.visible !== false && isOptionColumn(column) && !hidden.has(column.key))
    .flatMap((column) => resolvePropertyChips(event, column));
}

// Tag chips for an event. With a column, labels/colors come from its options;
// without one (e.g. export layout that lacks column context) the option id is
// used as the label. Reads the unified `extra.tags` location.
export function collectEventTags(event, column = null) {
  if (column) return resolvePropertyChips(event, column);
  const raw = event?.extra?.tags;
  const ids = Array.isArray(raw) ? raw : raw ? [raw] : [];
  return ids
    .map((id) => String(id || "").trim())
    .filter(Boolean)
    .map((id) => ({ value: id, label: id, color: "var(--accent)" }));
}

function pushSampleValue(samples, value) {
  const text = String(value || "").trim();
  if (!text) return;
  if (samples.includes(text)) return;
  if (samples.length >= 2) return;
  samples.push(text.length > SAMPLE_TEXT_LIMIT ? `${text.slice(0, SAMPLE_TEXT_LIMIT).trim()}...` : text);
}

export function eventColumnValue(event, column) {
  if (!column) return "—";
  if (column.key === "time") return formatEventDate(event);
  if (column.key === "title") return event?.headline || event?.era || event?.displayLabel || "未命名事件";
  if (isOptionColumn(column)) {
    const chips = resolvePropertyChips(event, column);
    return chips.length ? chips.map((chip) => chip.label).join("、") : "—";
  }
  const value = event?.extra?.[column.key];
  // Trimmed-empty (incl. whitespace-only) renders as "—" so it agrees with
  // `eventColumnHasValue`/auto-hide and the detail pane's trim convention; a
  // real "0" stays visible (the old `value ? … : "—"` dropped numeric 0).
  return String(value ?? "").trim() !== "" ? String(value) : "—";
}

// Per-property option rows (with usage counts) for the left "属性" tab.
export function buildPropertyRows(columns, events) {
  const items = Array.isArray(events) ? events : [];
  return normalizeTopicColumns(columns).map((column) => {
    const counts = new Map();
    const sampleValues = [];
    let filledCount = 0;
    let checkedCount = 0;
    if (isOptionColumn(column)) {
      for (const event of items) {
        const chips = resolvePropertyChips(event, column);
        if (chips.length) filledCount += 1;
        for (const chip of chips) {
          counts.set(chip.value, (counts.get(chip.value) || 0) + 1);
        }
      }
    } else if (column.type === "checkbox") {
      for (const event of items) {
        const raw = event?.extra?.[column.key];
        if (raw !== undefined && raw !== null && String(raw).trim() !== "") filledCount += 1;
        if (isCheckboxChecked(raw)) checkedCount += 1;
      }
    } else {
      for (const event of items) {
        const value = String(event?.extra?.[column.key] ?? "").trim();
        if (!value) continue;
        filledCount += 1;
        pushSampleValue(sampleValues, value);
      }
    }
    const options = (column.options || []).map((option) => ({
      value: option.id,
      label: option.label,
      color: option.color || "var(--accent)",
      count: counts.get(option.id) || 0,
    }));
    return {
      key: column.key,
      label: column.label,
      type: column.type,
      isOption: isOptionColumn(column),
      options,
      optionCount: options.length,
      totalCount: items.length,
      filledCount,
      checkedCount,
      sampleValues,
    };
  });
}

export function buildPropertyUsage(columns, events) {
  const items = Array.isArray(events) ? events : [];
  const rows = buildPropertyRows(columns, items);
  const rowMap = new Map(rows.map((row) => [row.key, row]));
  const orphanKeys = new Set();
  const orphanOptionIds = new Map();
  const rawValueCounts = new Map();

  for (const event of items) {
    for (const [key, value] of Object.entries(event?.extra || {})) {
      orphanKeys.add(key);
      if (!orphanOptionIds.has(key)) orphanOptionIds.set(key, new Set());
      const optionBucket = orphanOptionIds.get(key);
      const list = Array.isArray(value) ? value : value ? [value] : [];
      if (list.some((item) => String(item || "").trim())) {
        rawValueCounts.set(key, (rawValueCounts.get(key) || 0) + 1);
      }
      for (const item of list) {
        const normalized = String(item || "").trim();
        if (normalized) optionBucket.add(normalized);
      }
    }
  }

  return { rows: rowMap, orphanKeys, orphanOptionIds, rawValueCounts };
}

export function canChangePropertyType(usage, key) {
  if (!key) return true;
  return !usage || (usage.rawValueCounts?.get(key) || 0) === 0;
}

export function normalizeEventExtra(extra, columns = []) {
  const byKey = new Map(normalizeTopicColumns(columns).map((column) => [column.key, column]));
  const source = extra && typeof extra === "object" ? extra : {};
  const normalized = {};
  for (const [key, value] of Object.entries(source)) {
    const column = byKey.get(key);
    if (!column) continue;
    if (column.type === "multiselect") {
      const valid = new Set((column.options || []).map((option) => option.id));
      const list = Array.isArray(value) ? value : value ? [value] : [];
      normalized[key] = [...new Set(list.map((item) => String(item)).filter((item) => valid.has(item)))];
    } else if (column.type === "select") {
      const valid = new Set((column.options || []).map((option) => option.id));
      const single = String(value ?? "");
      normalized[key] = valid.has(single) ? single : "";
    } else if (column.type === "checkbox") {
      normalized[key] = isCheckboxChecked(value) ? "true" : "false";
    } else {
      normalized[key] = value == null ? "" : String(value);
    }
  }
  return normalized;
}

function hasReadableAttachment(attachment = {}) {
  return Boolean(
    String(attachment.name || "").trim() ||
      String(attachment.filename || "").trim() ||
      String(attachment.url || "").trim() ||
      String(attachment.imageUrl || "").trim()
  );
}

function hasReadableRelatedEvent(event = {}) {
  return Boolean(
    event.id &&
      (String(event.headline || "").trim() ||
        String(event.displayLabel || "").trim() ||
        String(event.isoDate || "").trim())
  );
}

export function buildReadableDetailGroups(event) {
  return {
    attachments: (Array.isArray(event?.attachments) ? event.attachments : []).filter(hasReadableAttachment),
    relatedEvents: (Array.isArray(event?.relatedEvents) ? event.relatedEvents : []).filter(hasReadableRelatedEvent),
  };
}

export function matchesEventSearch(event, query, columns = []) {
  const normalized = String(query || "").trim().toLowerCase();
  if (!normalized) return true;
  const indexedText = String(event?.searchText || "").trim().toLowerCase();
  if (indexedText) return indexedText.includes(normalized);
  const propertyText = normalizeTopicColumns(columns)
    .flatMap((column) => {
      if (isOptionColumn(column)) {
        return resolvePropertyChips(event, column).flatMap((chip) => [chip.value, chip.label]);
      }
      const value = event?.extra?.[column.key];
      return value ? [String(value)] : [];
    })
    .join(" ");
  const attachmentText = (event?.attachments || [])
    .map((item) => `${item?.name || ""} ${item?.filename || ""}`)
    .join(" ");
  const haystack = [
    event?.headline,
    event?.displayLabel,
    event?.era,
    event?.legacyYear,
    mindmapPlainText(event?.bodyJson),
    event?.bodyMarkdown,
    event?.preview,
    event?.searchText,
    propertyText,
    attachmentText,
    ...(event?.items || []).map((item) => item?.text),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return haystack.includes(normalized);
}

// Split `text` into segments around case-insensitive occurrences of `query`,
// flagging which are matches. Mirrors matchesEventSearch's semantics (the whole
// trimmed query as one case-insensitive substring) so the feed highlights exactly
// what the filter matched. Output preserves the source's original case. An empty
// query (or no match) yields a single non-hit segment, so callers always v-for a
// uniform shape; an empty string yields no segments.
export function buildSearchHighlightSegments(text, query) {
  const source = String(text ?? "");
  if (!source) return [];
  const needle = String(query ?? "").trim().toLowerCase();
  if (!needle) return [{ text: source, hit: false }];
  const hay = source.toLowerCase();
  const segments = [];
  let from = 0;
  for (let at = hay.indexOf(needle, from); at !== -1; at = hay.indexOf(needle, from)) {
    if (at > from) segments.push({ text: source.slice(from, at), hit: false });
    segments.push({ text: source.slice(at, at + needle.length), hit: true });
    from = at + needle.length;
  }
  if (from < source.length) segments.push({ text: source.slice(from), hit: false });
  return segments;
}

// True when the event matches a property=value filter (`{ key, value }`).
export function matchesPropertyFilter(event, filter) {
  if (!filter || !filter.key) return true;
  const raw = event?.extra?.[filter.key];
  if (Array.isArray(raw)) return raw.map((item) => String(item)).includes(String(filter.value));
  return String(raw ?? "") === String(filter.value);
}

function buildEraSubtitle(items) {
  const years = (items || [])
    .map((event) => event?.dateParts?.year)
    .filter((year) => Number.isInteger(year));
  if (!years.length) return `${items.length} 条`;
  const minYear = Math.min(...years);
  const maxYear = Math.max(...years);
  // BC-aware (公元前N) so ancient-era ranges don't render as raw "-1700000".
  const range = minYear === maxYear ? formatYearLabel(minYear) : `${formatYearLabel(minYear)}–${formatYearLabel(maxYear)}`;
  return `${range} · ${items.length} 条`;
}

// `sort` ({ field, dir }) orders the flattened list before era bucketing, so a
// descending time sort reverses both the era group order (buckets follow first
// appearance) and the within-group order. Null → the default chronological order.
export function groupTimelineEvents(events, groupBy = "era", searchQuery = "", columns = [], sort = null) {
  const comparator = sort ? compareEventsBySort(sort, columns) : compareTimelineEvents;
  const filtered = [...(events || [])]
    .sort(comparator)
    .filter((event) => matchesEventSearch(event, searchQuery, columns));

  if (groupBy === "year" || groupBy === "month") {
    const buckets = new Map();
    for (const event of filtered) {
      const parts = event.dateParts || {};
      // Undated notes have no year/month, so they get their own trailing bucket
      // (the sort already sinks them last) instead of a fabricated "null年" group.
      const undated = !eventHasDate(event);
      const isEarlier = !undated && event?.era === "更早";
      const bucketKey = undated ? "undated" : isEarlier ? "earlier" : groupBy === "month" ? `${parts.year}-${padTwo(parts.month)}` : String(parts.year ?? "");
      const title = undated ? "未定时间" : isEarlier ? "更早" : groupBy === "month" ? `${parts.year}年${parts.month}月` : String(parts.year ?? "");

      if (!buckets.has(bucketKey)) {
        buckets.set(bucketKey, { key: bucketKey, title, subtitle: "", items: [] });
      }

      buckets.get(bucketKey).items.push(event);
    }

    return [...buckets.values()].map((group) => ({
      ...group,
      subtitle: groupBy === "year" ? buildMonthRangeLabel(group.items) : "",
    }));
  }

  const buckets = new Map();
  for (const event of filtered) {
    const key = String(event?.era || "未分组").trim() || "未分组";
    if (!buckets.has(key)) {
      buckets.set(key, {
        key,
        title: key,
        subtitle: "",
        items: [],
      });
    }
    buckets.get(key).items.push(event);
  }

  return [...buckets.values()].map((group) => ({
    ...group,
    subtitle: buildEraSubtitle(group.items),
  }));
}

export function buildEditorDraft(event, columns = []) {
  const cols = normalizeTopicColumns(columns);
  const today = new Date();
  const parts = event?.dateParts || {};
  const bodyMarkdown = event?.bodyMarkdown || defaultBodyFromItems(event?.items || []);

  // Seed a value slot for every property so inline editors bind cleanly.
  const existingExtra = normalizeEventExtra(event?.extra, cols);
  const extra = {};
  for (const column of cols) {
    if (column.type === "multiselect") {
      extra[column.key] = Array.isArray(existingExtra[column.key]) ? [...existingExtra[column.key]] : [];
    } else {
      extra[column.key] = existingExtra[column.key] ?? "";
    }
  }

  return {
    id: event?.id || null,
    dateYear: event?.id ? parts.year : today.getFullYear(),
    dateMonth: event?.id ? parts.month : today.getMonth() + 1,
    dateDay: event?.id ? parts.day : today.getDate(),
    headline: event?.headline || "",
    era: event?.era || "",
    bodyMarkdown,
    image: event?.image || "",
    imageUrl: event?.imageUrl || "",
    attachments: Array.isArray(event?.attachments) ? event.attachments.map((item) => ({ ...item })) : [],
    relatedEventIds: Array.isArray(event?.relatedEventIds) ? [...event.relatedEventIds] : [],
    relatedEvents: Array.isArray(event?.relatedEvents) ? event.relatedEvents.map((item) => ({ ...item })) : [],
    favorite: Boolean(event?.favorite),
    deletedAt: event?.deletedAt || null,
    items: (event?.items || [{ tag: "note", text: bodyMarkdown || "" }]).map((item) => ({
      tag: item.tag || "note",
      text: item.text || "",
    })),
    extra,
  };
}

// Classify the three raw date inputs of the note editor into the de-temporalized
// contract, mirroring the backend normalize_event_payload branches:
//   - all three parse to integers  → "dated"   (carries dateFields for the payload)
//   - all three blank              → "undated" (no date keys; note sinks to the tail)
//   - anything in between          → "partial" (a half-typed date; the editor rejects it)
// Range validity (month 1-12, day 1-31, real calendar dates) stays a backend guard —
// this only decides dated / undated / partial so the editor can shape the payload.
export function classifyEventDateInput(rawYear, rawMonth, rawDay) {
  const raws = [rawYear, rawMonth, rawDay].map((part) => String(part ?? "").trim());
  if (raws.every((part) => part === "")) return { status: "undated", dateFields: {} };
  const [year, month, day] = raws.map((part) => Number.parseInt(part, 10));
  if (![year, month, day].every((part) => Number.isInteger(part))) {
    return { status: "partial", dateFields: {} };
  }
  return { status: "dated", dateFields: { dateYear: year, dateMonth: month, dateDay: day } };
}

export function dateKeyFromLocator(value) {
  const raw = String(value || "").trim();
  if (!raw) return null;
  const match = raw.match(/^(-?\d{1,4})(?:-(\d{1,2})(?:-(\d{1,2}))?)?$/);
  if (!match) return null;
  const year = Number.parseInt(match[1], 10);
  const month = match[2] ? Number.parseInt(match[2], 10) : 1;
  const day = match[3] ? Number.parseInt(match[3], 10) : 1;
  if (Number.isNaN(year) || month < 1 || month > 12 || day < 1 || day > 31) return null;
  return year * 10000 + month * 100 + day;
}

export function normalizeTopicBookshelf(topic = {}) {
  const name = String(topic?.bookshelfName || "").trim() || "default";
  const title = String(topic?.bookshelfTitle || "").trim() || (name === "qstheory" ? "求是" : "编年");
  return {
    id: topic?.bookshelfId ?? null,
    name,
    title,
  };
}

export function findBookshelfByName(bookshelves, name, fallbackShelves = []) {
  const target = String(name || "").trim();
  if (!target) return null;
  const primary = (Array.isArray(bookshelves) ? bookshelves : []).find((shelf) => String(shelf?.name || "").trim() === target);
  if (primary) return primary;
  return (Array.isArray(fallbackShelves) ? fallbackShelves : []).find((shelf) => String(shelf?.name || "").trim() === target) || null;
}

export function resolveTopicCreateShelfName(shelfName = "", activeBookshelfName = "", bookshelfTree = []) {
  const normalizedShelfName = typeof shelfName === "string" ? shelfName : "";
  return (
    String(normalizedShelfName || "").trim() ||
    String(activeBookshelfName || "").trim() ||
    String(bookshelfTree?.[0]?.name || "").trim()
  );
}

export const SIDEBAR_SORT_MODES = ["default", "name", "count", "updated"];

// Compare two tree nodes (a shelf, or a notebook via entry.topic) for the sidebar
// sort. count/updated sort descending (most notes / most recent first); name and
// every tiebreak fall back to title ascending (zh-CN collation).
function compareSidebarNodes(a, b, mode) {
  if (mode === "count") {
    const delta = Number(b?.eventCount || 0) - Number(a?.eventCount || 0);
    if (delta) return delta;
  } else if (mode === "updated") {
    const av = a?.updatedAt ? Date.parse(a.updatedAt) : NaN;
    const bv = b?.updatedAt ? Date.parse(b.updatedAt) : NaN;
    const left = Number.isNaN(av) ? Number.NEGATIVE_INFINITY : av;
    const right = Number.isNaN(bv) ? Number.NEGATIVE_INFINITY : bv;
    if (right !== left) return right - left;
  }
  return String(a?.title || a?.name || "").localeCompare(String(b?.title || b?.name || ""), "zh-CN");
}

// Reorder the fetched bookshelf tree client-side so we never touch the backend's
// per-shelf GROUP BY count query: one global mode sorts the shelves AND the
// notebooks inside each shelf. "default" keeps the backend order (bookshelf id asc
// = creation order); era sub-lists stay time-sorted and are never reordered here.
// Non-mutating — returns fresh arrays / shelf objects, leaving the source untouched.
export function sortBookshelfTree(tree, mode = "default") {
  const shelves = Array.isArray(tree) ? tree : [];
  if (!SIDEBAR_SORT_MODES.includes(mode) || mode === "default") return shelves;
  const topicNode = (entry) => entry?.topic || entry || {};
  return shelves
    .map((shelf) => ({
      ...shelf,
      topics: [...(shelf?.topics || [])].sort((x, y) => compareSidebarNodes(topicNode(x), topicNode(y), mode)),
    }))
    .sort((x, y) => compareSidebarNodes(x, y, mode));
}

export function buildBookshelfTree(topics = [], bookshelves = [], allEvents = []) {
  const liveEventsByTopic = new Map();
  for (const event of Array.isArray(allEvents) ? allEvents : []) {
    if (!event || event.deletedAt) continue;
    const topicId = Number(event.topicId);
    if (!liveEventsByTopic.has(topicId)) liveEventsByTopic.set(topicId, []);
    liveEventsByTopic.get(topicId).push(event);
  }

  const shelves = [];
  const byShelf = new Map();
  for (const shelf of Array.isArray(bookshelves) ? bookshelves : []) {
    const normalizedName = String(shelf?.name || "").trim();
    if (!normalizedName || byShelf.has(normalizedName)) continue;
    const entry = {
      id: shelf?.id ?? null,
      name: normalizedName,
      title: String(shelf?.title || normalizedName).trim() || normalizedName,
      topicCount: 0,
      eventCount: 0,
      topics: [],
    };
    byShelf.set(normalizedName, entry);
    shelves.push(entry);
  }

  for (const topic of Array.isArray(topics) ? topics : []) {
    const bookshelf = normalizeTopicBookshelf(topic);
    let shelf = byShelf.get(bookshelf.name);
    if (!shelf) {
      shelf = {
        id: bookshelf.id,
        name: bookshelf.name,
        title: bookshelf.title,
        topicCount: 0,
        eventCount: 0,
        topics: [],
      };
      byShelf.set(bookshelf.name, shelf);
      shelves.push(shelf);
    }

    const eras = [];
    const eraMap = new Map();
    for (const event of (liveEventsByTopic.get(topic.id) || []).sort(compareTimelineEvents)) {
      const era = String(event?.era || "未分组").trim() || "未分组";
      if (!eraMap.has(era)) {
        eraMap.set(era, { era, count: 0 });
        eras.push(eraMap.get(era));
      }
      eraMap.get(era).count += 1;
    }

    shelf.topicCount += 1;
    shelf.eventCount += Number(topic.eventCount || 0);
    shelf.topics.push({ topic, eras });
  }

  return shelves;
}

export function shouldAutoLoadMoreForFilteredEvents({
  activeTopicId = null,
  globalFavoritesMode = false,
  hasMore = false,
  eventsLoading = false,
  loadingMore = false,
  visibleCount = 0,
} = {}) {
  return Boolean(
    activeTopicId &&
      !globalFavoritesMode &&
      hasMore &&
      !eventsLoading &&
      !loadingMore &&
      Number(visibleCount) === 0
  );
}

// --- Pagination core (pure helpers, unit-tested in ui/tests/timelineNotes.test.js) ---

// Merge a freshly-fetched page into a topic's already-loaded events. On append,
// de-dupes by id (a cursor page can re-include a boundary row) so paging never
// duplicates or drops events; a non-append load replaces outright.
export function mergeTopicEventPage(existing = [], incoming = [], { append = false } = {}) {
  const incomingList = Array.isArray(incoming) ? incoming : [];
  if (!append) return [...incomingList];
  const existingList = Array.isArray(existing) ? existing : [];
  const seen = new Set(existingList.map((event) => event.id));
  return [...existingList, ...incomingList.filter((event) => !seen.has(event.id))];
}

// Decide whether ensureTopicEvents should hit the network and which cursor to
// thread. Serves cache for an already-loaded topic (unless forced); on append,
// only fetches when there is another page (hasMore) AND a cursor to advance past,
// so it never silently refetches page 1.
export function planTopicPageFetch(
  { loaded = false, hasMore = false, nextCursor = null } = {},
  { append = false, cursor = null, force = false } = {}
) {
  if (!append && loaded && !force) return { shouldFetch: false, requestCursor: null };
  const requestCursor = cursor ?? (append ? nextCursor : null);
  if (append && (!hasMore || !requestCursor)) return { shouldFetch: false, requestCursor: null };
  return { shouldFetch: true, requestCursor };
}

// Whether a scroll position is close enough to the bottom to request the next
// page — with the same guards the feed applies (only while more pages exist and
// nothing else is loading/erroring).
export function shouldRequestMoreOnScroll({
  scrollHeight = 0,
  scrollTop = 0,
  clientHeight = 0,
  hasMore = false,
  loadingMore = false,
  globalFavoritesMode = false,
  loading = false,
  error = false,
  threshold = 320,
} = {}) {
  if (!hasMore || loadingMore || globalFavoritesMode || loading || error) return false;
  return scrollHeight - scrollTop - clientHeight <= threshold;
}

export function resolveCreateTopicRequest(input, activeBookshelfName = "", bookshelves = [], bookshelfTree = []) {
  const topicName = typeof input === "string" ? input : String(input?.name || "").trim();
  const shelfNameInput = typeof input === "string" ? activeBookshelfName : input?.bookshelfName;
  const bookshelfName = resolveTopicCreateShelfName(shelfNameInput, activeBookshelfName, bookshelfTree);
  const bookshelf = findBookshelfByName(bookshelves, bookshelfName, bookshelfTree);
  return {
    topicName,
    bookshelfName,
    bookshelfId: bookshelf?.id ?? null,
  };
}
