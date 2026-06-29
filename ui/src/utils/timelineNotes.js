import { CONTENT_LIMITS } from "../constants/contentLimits.js";
import { plainTextFromMarkdown } from "./markdownPreview.js";

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
  const leftKey = left?.era === "更早" ? Number.MAX_SAFE_INTEGER + (left?.dateKey || 0) : left?.dateKey || 0;
  const rightKey = right?.era === "更早" ? Number.MAX_SAFE_INTEGER + (right?.dateKey || 0) : right?.dateKey || 0;
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
  const parts = event?.dateParts;
  if (!parts || parts.year == null) return event?.displayLabel || "";
  const yearLabel = `${formatYearLabel(parts.year)}年`;
  if (parts.month === 1 && parts.day === 1) return yearLabel;
  return `${yearLabel}${parts.month}月${parts.day}日`;
}

export function buildEventPreview(event, maxLength = CONTENT_LIMITS.previewText) {
  const text =
    String(event?.preview || "").trim() ||
    plainTextFromMarkdown(event?.bodyMarkdown) ||
    (event?.items || [])
      .map((item) => String(item?.text || "").trim())
      .filter(Boolean)
      .join(" ");
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength).trim()}...`;
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
  if (column.key === "title") return event?.headline || event?.displayLabel || "未命名事件";
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

export function groupTimelineEvents(events, groupBy = "era", searchQuery = "", columns = []) {
  const filtered = [...(events || [])]
    .sort(compareTimelineEvents)
    .filter((event) => matchesEventSearch(event, searchQuery, columns));

  if (groupBy === "year" || groupBy === "month") {
    const buckets = new Map();
    for (const event of filtered) {
      const parts = event.dateParts || {};
      const isEarlier = event?.era === "更早";
      const bucketKey = isEarlier ? "earlier" : groupBy === "month" ? `${parts.year}-${padTwo(parts.month)}` : String(parts.year ?? "");

      if (!buckets.has(bucketKey)) {
        buckets.set(bucketKey, {
          key: bucketKey,
          title: isEarlier ? "更早" : groupBy === "month" ? `${parts.year}年${parts.month}月` : String(parts.year ?? ""),
          subtitle: "",
          items: [],
        });
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
    const key = String(event?.era || "未分期").trim() || "未分期";
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
