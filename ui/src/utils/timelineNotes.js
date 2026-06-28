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

export function isOptionColumn(column) {
  return OPTION_COLUMN_TYPES.has(column?.type);
}

export function isCheckboxColumn(column) {
  return column?.type === "checkbox";
}

export function isLinkColumn(column) {
  return LINK_COLUMN_TYPES.has(column?.type);
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

export function buildVisibleTimelineColumns(columns, hiddenKeys = null) {
  const properties = normalizeTopicColumns(columns).filter((column) => column.visible);
  const hidden = hiddenKeys instanceof Set ? hiddenKeys : Array.isArray(hiddenKeys) ? new Set(hiddenKeys) : null;
  const shown = hidden ? properties.filter((column) => !hidden.has(column.key)) : properties;
  return [
    { key: "time", label: "时间", width: 96, builtIn: true, locked: true, type: "time" },
    { key: "title", label: "事件", width: null, builtIn: true, locked: true, type: "title" },
    ...shown,
  ];
}

export function buildTimelineGridTemplate(columns, hiddenKeys = null) {
  return [
    "28px",
    ...buildVisibleTimelineColumns(columns, hiddenKeys).map((column) => (column.width ? `${column.width}px` : "minmax(0,1fr)")),
    "30px",
  ].join(" ");
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
  return normalizeTopicColumns(columns).map((column) => {
    const counts = new Map();
    if (isOptionColumn(column)) {
      for (const event of events || []) {
        for (const chip of resolvePropertyChips(event, column)) {
          counts.set(chip.value, (counts.get(chip.value) || 0) + 1);
        }
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
    };
  });
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
