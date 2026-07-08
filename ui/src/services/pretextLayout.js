import {
  layoutWithLines,
  measureNaturalWidth,
  prepareWithSegments,
} from "@chenglou/pretext";
import { plainTextFromMarkdown } from "../utils/markdownPreview.js";
import { collectNoteTags } from "../utils/timelineNotes.js";

const FONT_PRESETS = {
  timelinePrimary: '700 13.12px "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif',
  timelineSecondary: '500 11.52px "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif',
  previewBody: '500 13.12px "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif',
  editorTitle: '700 17px "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif',
  editorMeta: '500 13px "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif',
  timelineCardTitle: '700 24px "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif',
  timelineCardPreview: '400 16px "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif',
  timelineCardChip: '400 14px "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif',
  exportTitle: '700 30px "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif',
  exportHeading: '700 18px "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif',
  exportBody: '500 14px "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif',
};

const TIMELINE_CARD_DEFAULTS = {
  cardWidth: 531,
  textWidth: 480,
  titleWidth: 390,
  titleLineHeight: 28,
  previewLineHeight: 28,
  chipLineHeight: 28,
  maxTitleLines: 2,
  maxPreviewLines: 2,
  minHeight: 147,
  maxHeight: 175,
  activeMinHeight: 175,
};

const TIMELINE_OFFSET_DEFAULTS = {
  feedPaddingTop: 26,
  groupGap: 26,
  cardStackTop: 19,
  cardGap: 0,
};

const prepareCache = new Map();
const widthCache = new Map();
const layoutCache = new Map();
const previewCache = new Map();
const editorHeightCache = new Map();
let supportCache;

const CACHE_LIMITS = {
  prepared: 800,
  width: 1200,
  layout: 1200,
  preview: 1200,
  editorHeight: 600,
};

function cacheKey(text, font, options = {}) {
  return JSON.stringify([font, options.wordBreak || "normal", options.letterSpacing || 0, String(text || "")]);
}

function readCache(cache, key) {
  if (!cache.has(key)) {
    return undefined;
  }
  const value = cache.get(key);
  cache.delete(key);
  cache.set(key, value);
  return value;
}

function writeCache(cache, key, value, limit) {
  if (cache.has(key)) {
    cache.delete(key);
  }
  cache.set(key, value);
  while (cache.size > limit) {
    cache.delete(cache.keys().next().value);
  }
  return value;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function getPresetFont(preset) {
  const font = FONT_PRESETS[preset];
  if (!font) {
    throw new Error(`Unknown Pretext font preset: ${preset}`);
  }
  return font;
}

function normalizeInlineText(value) {
  return String(value || "")
    .replace(/\s+/g, " ")
    .trim();
}

function legacyBodyFromItems(items) {
  return (items || [])
    .map((item) => String(item?.text || "").trim())
    .filter(Boolean)
    .join(" ");
}

function bodyTextFromEvent(event) {
  return normalizeInlineText(plainTextFromMarkdown(event?.bodyMarkdown) || legacyBodyFromItems(event?.items));
}

function approximateCharWidth(preset) {
  if (preset === "timelineCardTitle") return 22;
  if (preset === "timelineCardChip") return 14;
  if (preset === "timelineCardPreview") return 16;
  return 14;
}

function fallbackLayout(text, preset, width, lineHeight) {
  const normalized = normalizeInlineText(text);
  if (!normalized) {
    return { height: 0, lineCount: 0, lines: [] };
  }

  const maxChars = Math.max(1, Math.floor((Number(width) || 1) / approximateCharWidth(preset)));
  const lines = [];
  for (let index = 0; index < normalized.length; index += maxChars) {
    const lineText = normalized.slice(index, index + maxChars);
    lines.push({
      text: lineText,
      width: Math.min(lineText.length * approximateCharWidth(preset), Number(width) || 0),
      start: null,
      end: null,
    });
  }

  return {
    height: lines.length * lineHeight,
    lineCount: lines.length,
    lines,
  };
}

function safeMaterializeTextLayout(text, preset, width, lineHeight, options = {}) {
  if (getPretextSupport().supported) {
    return materializeTextLayout(text, preset, width, lineHeight, options);
  }
  return fallbackLayout(text, preset, width, lineHeight);
}

function countChipRows(tags, width) {
  const labels = (tags || []).map((tag) => tag.label || tag.value || "").filter(Boolean);
  if (labels.length === 0) return 0;

  let rows = 1;
  let currentWidth = 0;
  for (const label of labels) {
    const measuredWidth = getPretextSupport().supported
      ? measureTextWidth(label, "timelineCardChip", { wordBreak: "keep-all" })
      : label.length * approximateCharWidth("timelineCardChip");
    const chipWidth = Math.ceil(measuredWidth) + 24;
    const nextWidth = currentWidth === 0 ? chipWidth : currentWidth + 8 + chipWidth;
    if (nextWidth > width && currentWidth > 0) {
      rows += 1;
      currentWidth = chipWidth;
    } else {
      currentWidth = nextWidth;
    }
  }
  return rows;
}

function buildClampedPreview(text, preset, width, lineHeight, maxLines) {
  const normalized = normalizeInlineText(text);
  if (!normalized) return "";

  const layout = safeMaterializeTextLayout(normalized, preset, width, lineHeight, { wordBreak: "keep-all" });
  if (layout.lineCount <= maxLines) {
    return layout.lines.map((line) => line.text.trim()).join("");
  }

  let low = 0;
  let high = normalized.length;
  let best = "";
  while (low <= high) {
    const middle = Math.floor((low + high) / 2);
    const candidate = `${normalized.slice(0, middle).trim()}...`;
    const candidateLayout = safeMaterializeTextLayout(candidate, preset, width, lineHeight, { wordBreak: "keep-all" });
    if (candidateLayout.lineCount <= maxLines) {
      best = candidate;
      low = middle + 1;
    } else {
      high = middle - 1;
    }
  }

  return best || "...";
}

export function getPretextSupport() {
  if (supportCache) {
    return supportCache;
  }

  try {
    if (typeof Intl === "undefined" || typeof Intl.Segmenter !== "function") {
      supportCache = { supported: false, reason: "Intl.Segmenter is unavailable." };
      return supportCache;
    }

    const hasCanvasRuntime =
      typeof OffscreenCanvas !== "undefined" ||
      (typeof document !== "undefined" && typeof document.createElement === "function");

    if (!hasCanvasRuntime) {
      supportCache = { supported: false, reason: "Canvas text measurement is unavailable." };
      return supportCache;
    }

    prepareWithSegments("support-check", FONT_PRESETS.previewBody, { wordBreak: "keep-all" });
    supportCache = { supported: true, reason: "" };
    return supportCache;
  } catch (error) {
    supportCache = { supported: false, reason: error?.message || "Pretext runtime initialization failed." };
    return supportCache;
  }
}

export async function waitForTimelineFonts() {
  if (typeof document === "undefined" || !document.fonts?.ready) {
    return;
  }
  try {
    await document.fonts.ready;
  } catch {
    // Font readiness is an optimization for stable measurement; rendering can continue.
  }
}

export function requirePretextSupport() {
  const support = getPretextSupport();
  if (!support.supported) {
    throw new Error(support.reason || "Pretext support check failed.");
  }
}

function getPrepared(text, font, options = {}) {
  requirePretextSupport();
  const key = cacheKey(text, font, options);
  const cached = readCache(prepareCache, key);
  if (cached) {
    return cached;
  }
  return writeCache(prepareCache, key, prepareWithSegments(String(text || ""), font, options), CACHE_LIMITS.prepared);
}

export function measureTextWidth(text, preset, options = {}) {
  const font = getPresetFont(preset);
  const key = cacheKey(text, font, options);
  const cached = readCache(widthCache, key);
  if (cached !== undefined) {
    return cached;
  }
  const prepared = getPrepared(text, font, options);
  return writeCache(widthCache, key, measureNaturalWidth(prepared), CACHE_LIMITS.width);
}

export function materializeTextLayout(text, preset, width, lineHeight, options = {}) {
  const font = getPresetFont(preset);
  const key = JSON.stringify([cacheKey(text, font, options), Number(width) || 0, Number(lineHeight) || 0]);
  const cached = readCache(layoutCache, key);
  if (cached) {
    return cached;
  }
  const prepared = getPrepared(text, font, options);
  return writeCache(layoutCache, key, layoutWithLines(prepared, width, lineHeight), CACHE_LIMITS.layout);
}

export function buildPreviewText(text, preset = "previewBody", width = 220, lineHeight = 18, maxLines = 2) {
  const normalized = String(text || "").trim();
  if (!normalized) {
    return "";
  }
  const key = JSON.stringify([normalized, preset, Number(width) || 0, Number(lineHeight) || 0, Number(maxLines) || 0]);
  const cached = readCache(previewCache, key);
  if (cached !== undefined) {
    return cached;
  }
  const result = materializeTextLayout(normalized, preset, width, lineHeight, { wordBreak: "keep-all" });
  const lines = result.lines.slice(0, maxLines).map((line) => line.text.trim());
  const joined = lines.join("");
  return writeCache(previewCache, key, result.lineCount > maxLines ? `${joined}...` : joined, CACHE_LIMITS.preview);
}

export function buildSingleLinePreview(text, preset = "timelineCardPreview", width = TIMELINE_CARD_DEFAULTS.textWidth) {
  return buildClampedPreview(text, preset, width, TIMELINE_CARD_DEFAULTS.previewLineHeight, 1);
}

export function buildTimelineCardLayout(event, options = {}) {
  const settings = { ...TIMELINE_CARD_DEFAULTS, ...options };
  const title = normalizeInlineText(event?.headline || event?.displayLabel || "");
  const bodyText = bodyTextFromEvent(event);
  const tags = collectNoteTags(event).slice(0, 3);
  const titleLayout = safeMaterializeTextLayout(
    title,
    "timelineCardTitle",
    settings.titleWidth,
    settings.titleLineHeight,
    { wordBreak: "keep-all" }
  );
  const titleLineCount = clamp(titleLayout.lineCount || 1, 1, settings.maxTitleLines);
  const previewText = buildClampedPreview(
    bodyText,
    "timelineCardPreview",
    settings.textWidth,
    settings.previewLineHeight,
    settings.maxPreviewLines
  );
  const previewLayout = safeMaterializeTextLayout(
    previewText,
    "timelineCardPreview",
    settings.textWidth,
    settings.previewLineHeight,
    { wordBreak: "keep-all" }
  );
  const previewLineCount = previewText ? clamp(previewLayout.lineCount || 1, 1, settings.maxPreviewLines) : 0;
  const tagLineCount = countChipRows(tags, settings.textWidth);
  const verticalGaps = (previewLineCount > 0 ? 12 : 0) + (tagLineCount > 0 ? 12 : 0);
  const measuredHeight =
    38 +
    titleLineCount * settings.titleLineHeight +
    previewLineCount * settings.previewLineHeight +
    tagLineCount * settings.chipLineHeight +
    verticalGaps;

  return {
    eventId: event?.id ?? null,
    cardWidth: settings.cardWidth,
    textWidth: settings.textWidth,
    previewText,
    titleLineCount,
    previewLineCount,
    tagLineCount,
    estimatedHeight: clamp(Math.ceil(measuredHeight), settings.minHeight, settings.maxHeight),
  };
}

export function buildTimelineCardLayouts(events, options = {}) {
  return new Map((events || []).map((event) => [event.id, buildTimelineCardLayout(event, options)]));
}

export function buildTimelineOffsetIndex(groups, layoutMap, options = {}) {
  const settings = { ...TIMELINE_OFFSET_DEFAULTS, ...options };
  const index = [];
  let cursor = settings.feedPaddingTop;

  for (const [groupIndex, group] of (groups || []).entries()) {
    if (groupIndex > 0) {
      cursor += settings.groupGap;
    }

    let cardTop = cursor + settings.cardStackTop;
    for (const event of group.items || []) {
      const layout = layoutMap?.get?.(event.id);
      const estimatedHeight = layout?.estimatedHeight || TIMELINE_CARD_DEFAULTS.minHeight;
      index.push({
        eventId: event.id,
        dateKey: event.dateKey,
        estimatedTop: Math.round(cardTop),
        estimatedHeight,
      });
      cardTop += estimatedHeight + settings.cardGap;
    }

    cursor = cardTop;
  }

  return index;
}

export function measureBlockHeight(lines) {
  return lines.reduce((total, line) => total + line.height, 0);
}

export function measureEditorCardHeight(node) {
  const previewText = (node.items || []).slice(0, 4).map((item) => `${item.tag}: ${item.text}`).join(" ");
  const key = JSON.stringify([node.displayLabel || node.headline || "", node.era || "", previewText]);
  const cached = readCache(editorHeightCache, key);
  if (cached !== undefined) {
    return cached;
  }
  const titleLayout = materializeTextLayout(node.displayLabel || node.headline || "", "editorTitle", 460, 24, {
    wordBreak: "keep-all",
  });
  const metaLayout = materializeTextLayout(node.era || "", "editorMeta", 460, 18, {
    wordBreak: "keep-all",
  });
  const bodyLayout = materializeTextLayout(previewText, "previewBody", 460, 20, {
    wordBreak: "keep-all",
  });
  const bodyLines = Math.min(bodyLayout.lineCount, 4);
  return writeCache(
    editorHeightCache,
    key,
    148 + titleLayout.lineCount * 24 + metaLayout.lineCount * 18 + bodyLines * 20,
    CACHE_LIMITS.editorHeight
  );
}

export function buildSvgTextBlock(text, preset, width, lineHeight, maxLines = Infinity) {
  const result = materializeTextLayout(text, preset, width, lineHeight, { wordBreak: "keep-all" });
  return {
    lines: result.lines.slice(0, maxLines).map((line) => line.text),
    lineCount: Math.min(result.lineCount, maxLines),
    height: Math.min(result.lineCount, maxLines) * lineHeight,
  };
}

export function measureTimelineLabelWidth(primaryLabel, secondaryLabel) {
  return Math.max(
    measureTextWidth(primaryLabel || "", "timelinePrimary", { wordBreak: "keep-all" }),
    measureTextWidth(secondaryLabel || "", "timelineSecondary", { wordBreak: "keep-all" })
  );
}
