import { getTagColor, getTagLabel } from "../constants/tags.js";
import { CONTENT_LIMITS } from "../constants/contentLimits.js";
import { plainTextFromMarkdown } from "./markdownPreview.js";

const BUILTIN_COLUMN_DEFAULTS = {
  type: true,
  tags: true,
};

const RESERVED_COLUMN_KEYS = new Set(["title", "time", "type", "tags"]);
const COLUMN_KEY_PATTERN = /^[a-z][a-z0-9_]*$/;
const COLUMN_TYPES = new Set(["text", "number", "date", "select"]);

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

export function formatEventDate(event) {
  if (event?.isoDate) return event.isoDate;
  if (!event?.dateParts) return "";
  const year = event.dateParts.year ?? "";
  const month = padTwo(event.dateParts.month);
  const day = padTwo(event.dateParts.day);
  return `${year}-${month}-${day}`;
}

export function formatEventDisplayDate(event) {
  if (!event?.dateParts) return event?.displayLabel || "";
  const { year, month, day } = event.dateParts;
  return `${year}年${month}月${day}日`;
}

export function buildEventPreview(event, maxLength = CONTENT_LIMITS.previewText) {
  const text =
    plainTextFromMarkdown(event?.bodyMarkdown) ||
    (event?.items || [])
      .map((item) => String(item?.text || "").trim())
      .filter(Boolean)
      .join(" ");
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength).trim()}...`;
}

export function collectEventTags(event) {
  const baseTags =
    Array.isArray(event?.tags) && event.tags.length
      ? event.tags.map((tag) => String(tag || "").trim())
      : (event?.items || []).map((item) => String(item?.tag || "").trim());
  const seen = new Set();
  return baseTags
    .filter(Boolean)
    .filter((tag) => {
      if (seen.has(tag)) return false;
      seen.add(tag);
      return true;
    })
    .map((tag) => ({
      value: tag,
      label: getTagLabel(tag),
      color: getTagColor(tag),
    }));
}

export function normalizeTagValues(tags) {
  const seen = new Set();
  return (tags || [])
    .map((tag) => String(tag || "").trim())
    .filter(Boolean)
    .filter((tag) => {
      if (seen.has(tag)) return false;
      seen.add(tag);
      return true;
    });
}

export function normalizeTopicColumns(columns) {
  const seen = new Set();
  return (Array.isArray(columns) ? columns : [])
    .map((column, index) => {
      const key = String(column?.key || "").trim();
      const type = String(column?.type || "text").trim();
      const label = normalizeColumnLabel(column?.label);
      if (!COLUMN_KEY_PATTERN.test(key) || RESERVED_COLUMN_KEYS.has(key) || seen.has(key) || !label) {
        return null;
      }
      seen.add(key);
      return {
        key,
        label,
        type: COLUMN_TYPES.has(type) ? type : "text",
        width: normalizeColumnWidth(column?.width, 96),
        order: normalizeColumnOrder(column?.order, index),
        visible: column?.visible !== false,
      };
    })
    .filter(Boolean)
    .sort((left, right) => left.order - right.order || left.label.localeCompare(right.label));
}

export function normalizeBuiltinColumns(raw) {
  return {
    type: raw?.type !== false && BUILTIN_COLUMN_DEFAULTS.type,
    tags: raw?.tags !== false && BUILTIN_COLUMN_DEFAULTS.tags,
  };
}

export function buildVisibleTimelineColumns(columns, builtinState) {
  const builtins = normalizeBuiltinColumns(builtinState);
  const customColumns = normalizeTopicColumns(columns).filter((column) => column.visible);
  const visible = [
    { key: "time", label: "时间", width: 96, builtIn: true, locked: true },
    { key: "title", label: "事件", width: null, builtIn: true, locked: true },
  ];
  if (builtins.type) {
    visible.push({ key: "type", label: "类型", width: 72, builtIn: true });
  }
  visible.push(...customColumns);
  if (builtins.tags) {
    visible.push({ key: "tags", label: "标签", width: 150, builtIn: true });
  }
  return visible;
}

export function buildTimelineGridTemplate(columns, builtinState) {
  return ["28px", ...buildVisibleTimelineColumns(columns, builtinState).map((column) => column.width ? `${column.width}px` : "minmax(0,1fr)"), "30px"].join(" ");
}

export function normalizeEventExtra(extra, columns = []) {
  const allowed = new Set(normalizeTopicColumns(columns).map((column) => column.key));
  const source = extra && typeof extra === "object" ? extra : {};
  const normalized = {};
  for (const [key, value] of Object.entries(source)) {
    if (!allowed.has(key)) continue;
    normalized[key] = value == null ? "" : String(value);
  }
  return normalized;
}

export function typeLabelFromEvent(event) {
  const firstTag = collectEventTags(event)[0];
  return firstTag?.label || "—";
}

export function eventColumnValue(event, column) {
  if (!column) return "—";
  if (column.key === "time") return formatEventDate(event);
  if (column.key === "title") return event?.headline || event?.displayLabel || "未命名事件";
  if (column.key === "type") return typeLabelFromEvent(event);
  if (column.key === "tags") return collectEventTags(event).slice(0, 2);
  const value = normalizeEventExtra(event?.extra, [column])[column.key];
  return value ? String(value) : "—";
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
    tags: normalizeTagValues(Array.isArray(event?.tags) ? event.tags : []),
    attachments: (Array.isArray(event?.attachments) ? event.attachments : []).filter(hasReadableAttachment),
    relatedEvents: (Array.isArray(event?.relatedEvents) ? event.relatedEvents : []).filter(hasReadableRelatedEvent),
  };
}

export function matchesEventSearch(event, query) {
  const normalized = String(query || "").trim().toLowerCase();
  if (!normalized) return true;
  const tagText = collectEventTags(event)
    .flatMap((tag) => [tag.value, tag.label])
    .join(" ");
  const attachmentText = (event?.attachments || [])
    .map((item) => `${item?.name || ""} ${item?.filename || ""}`)
    .join(" ");
  const extraText = Object.values(event?.extra || {}).join(" ");
  const haystack = [
    event?.headline,
    event?.displayLabel,
    event?.era,
    event?.legacyYear,
    event?.bodyMarkdown,
    tagText,
    attachmentText,
    extraText,
    ...(event?.items || []).flatMap((item) => [item?.tag, item?.text]),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return haystack.includes(normalized);
}

function buildEraSubtitle(items) {
  const years = (items || [])
    .map((event) => event?.dateParts?.year)
    .filter((year) => Number.isInteger(year));
  if (!years.length) return `${items.length} 条`;
  const minYear = Math.min(...years);
  const maxYear = Math.max(...years);
  return `${minYear === maxYear ? minYear : `${minYear}–${maxYear}`} · ${items.length} 条`;
}

export function groupTimelineEvents(events, groupBy = "era", searchQuery = "") {
  const filtered = [...(events || [])].sort(compareTimelineEvents).filter((event) => matchesEventSearch(event, searchQuery));

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
  const today = new Date();
  const parts = event?.dateParts || {};
  const bodyMarkdown = event?.bodyMarkdown || defaultBodyFromItems(event?.items || []);

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
    tags: Array.isArray(event?.tags) ? normalizeTagValues(event.tags) : collectEventTags(event).map((tag) => tag.value),
    attachments: Array.isArray(event?.attachments) ? event.attachments.map((item) => ({ ...item })) : [],
    relatedEventIds: Array.isArray(event?.relatedEventIds) ? [...event.relatedEventIds] : [],
    relatedEvents: Array.isArray(event?.relatedEvents) ? event.relatedEvents.map((item) => ({ ...item })) : [],
    favorite: Boolean(event?.favorite),
    deletedAt: event?.deletedAt || null,
    items: (event?.items || [{ tag: "politics", text: bodyMarkdown || "" }]).map((item) => ({
      tag: item.tag || "politics",
      text: item.text || "",
    })),
    extra: normalizeEventExtra(event?.extra, columns),
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
