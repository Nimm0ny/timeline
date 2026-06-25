import { getTagLabel } from "../constants/tags.js";
import { CONTENT_LIMITS } from "../constants/contentLimits.js";
import { plainTextFromMarkdown } from "./markdownPreview.js";

function extractYearLabel(isoDate) {
  const match = String(isoDate || "").match(/^-?\d+/);
  return match ? match[0] : "";
}

function padTwo(value) {
  return String(value || 0).padStart(2, "0");
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

export function matchesEventSearch(event, query) {
  const normalized = String(query || "").trim().toLowerCase();
  if (!normalized) return true;
  const tagText = collectEventTags(event)
    .flatMap((tag) => [tag.value, tag.label])
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
    tagText,
    attachmentText,
    ...(event?.items || []).flatMap((item) => [item?.tag, item?.text]),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return haystack.includes(normalized);
}

export function groupTimelineEvents(events, groupBy = "year", searchQuery = "") {
  const filtered = [...(events || [])].sort(compareTimelineEvents).filter((event) => matchesEventSearch(event, searchQuery));
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

export function buildEditorDraft(event) {
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
