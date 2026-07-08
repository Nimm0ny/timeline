const IMAGE_EXTENSIONS = new Set(["png", "jpg", "jpeg", "gif", "webp", "svg"]);
const TEXT_EXTENSIONS = new Set(["md", "markdown", "txt"]);
const DOCUMENT_EXTENSIONS = new Set(["doc", "docx"]);

function extensionFromAttachment(attachment = {}) {
  const value = String(attachment.filename || attachment.name || "").toLowerCase();
  const extension = value.includes(".") ? value.split(".").pop() : "";
  return extension || "";
}

function normalizeSearch(value) {
  return String(value || "").trim().toLowerCase();
}

function escapeMarkdownLabel(value) {
  return String(value || "attachment")
    .replace(/[\r\n]+/g, " ")
    .replace(/\\/g, "\\\\")
    .replace(/\[/g, "\\[")
    .replace(/\]/g, "\\]")
    .trim() || "attachment";
}

function eventSearchText(event) {
  return [
    event?.headline,
    event?.displayLabel,
    event?.era,
    event?.isoDate,
    event?.dateRangeLabel,
    ...(Array.isArray(event?.tags) ? event.tags : []),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

export function attachmentKind(attachment = {}) {
  const mimeType = String(attachment.mimeType || "").toLowerCase();
  const extension = extensionFromAttachment(attachment);
  if (attachment.imageUrl || mimeType.startsWith("image/") || IMAGE_EXTENSIONS.has(extension)) return "image";
  if (mimeType.includes("pdf") || extension === "pdf") return "pdf";
  if (mimeType.startsWith("text/") || TEXT_EXTENSIONS.has(extension)) return "text";
  if (DOCUMENT_EXTENSIONS.has(extension)) return "document";
  return "file";
}

export function attachmentIconName(attachment = {}) {
  return attachmentKind(attachment) === "image" ? "image" : "file";
}

export function buildAttachmentMarkdown(attachment = {}) {
  if (!attachment.url) return "";
  const label = escapeMarkdownLabel(attachment.name || attachment.filename || "attachment");
  return attachmentKind(attachment) === "image" ? `![${label}](${attachment.url})` : `[${label}](${attachment.url})`;
}

export function insertTextAtRange(source, insertText, start, end = start) {
  const value = String(source || "");
  const safeStart = Math.max(0, Math.min(Number(start) || 0, value.length));
  const safeEnd = Math.max(safeStart, Math.min(Number(end) || safeStart, value.length));
  const text = `${value.slice(0, safeStart)}${insertText}${value.slice(safeEnd)}`;
  const cursor = safeStart + String(insertText || "").length;
  return { text, cursorStart: cursor, cursorEnd: cursor };
}

export function wrapMarkdownAtRange(source, start, end, prefix, suffix = "") {
  const value = String(source || "");
  const safeStart = Math.max(0, Math.min(Number(start) || 0, value.length));
  const safeEnd = Math.max(safeStart, Math.min(Number(end) || safeStart, value.length));
  const selected = value.slice(safeStart, safeEnd);
  const insertText = `${prefix}${selected}${suffix}`;
  const next = insertTextAtRange(value, insertText, safeStart, safeEnd);
  return {
    text: next.text,
    cursorStart: safeStart + String(prefix || "").length,
    cursorEnd: safeStart + String(prefix || "").length + selected.length,
  };
}

export function buildBlockInsertion(source, start, end, block) {
  const value = String(source || "");
  const safeStart = Math.max(0, Math.min(Number(start) || 0, value.length));
  const safeEnd = Math.max(safeStart, Math.min(Number(end) || safeStart, value.length));
  const before = value.slice(0, safeStart);
  const after = value.slice(safeEnd);
  const prefix = before && !before.endsWith("\n\n") ? (before.endsWith("\n") ? "\n" : "\n\n") : "";
  const suffix = after && !after.startsWith("\n\n") ? (after.startsWith("\n") ? "\n" : "\n\n") : "";
  return insertTextAtRange(value, `${prefix}${block}${suffix}`, safeStart, safeEnd);
}

// 选区是否与文档区间 [from,to] 相交（含边界接触）。Live preview 据此判定某个
// markdown 构造（粗体/链接/列表行等）此刻该「显原文标记」还是「隐标记渲染」。
export function selectionTouchesRange(ranges, from, to) {
  const lo = Math.min(from, to);
  const hi = Math.max(from, to);
  return (Array.isArray(ranges) ? ranges : []).some(
    (range) => range && range.from <= hi && range.to >= lo
  );
}

export function filterRelatedNoteCandidates(events, { currentId = null, selectedIds = [], query = "", limit = 8 } = {}) {
  const selected = new Set(selectedIds.map((id) => Number(id)));
  const normalizedQuery = normalizeSearch(query);
  return (Array.isArray(events) ? events : [])
    .filter((event) => event?.id && event.id !== currentId && !event.deletedAt && !selected.has(Number(event.id)))
    .filter((event) => !normalizedQuery || eventSearchText(event).includes(normalizedQuery))
    .slice(0, limit);
}

const UNORDERED_LIST_ITEM_RE = /^(\s*)([-*+])(\s+)(\[[ xX]\]\s+)?(.*)$/;
const ORDERED_LIST_ITEM_RE = /^(\s*)(\d+)([.)])(\s+)(.*)$/;
const BLOCKQUOTE_LINE_RE = /^(\s*)(>+)(\s?)(.*)$/;

// Markdown 续行：判断当前行是否为无序/任务/有序/引用项，返回下一行应自动补的前缀。
// 空项（标记后无正文）返回 isEmpty=true，让调用方清空当前行以退出该结构。
export function markdownListContinuation(lineText) {
  const text = String(lineText ?? "");

  const unordered = text.match(UNORDERED_LIST_ITEM_RE);
  if (unordered) {
    const [, indent, bullet, gap, task, content] = unordered;
    const prefix = task ? `${indent}${bullet}${gap}[ ] ` : `${indent}${bullet}${gap}`;
    return { isEmpty: !content.trim(), prefix };
  }

  const ordered = text.match(ORDERED_LIST_ITEM_RE);
  if (ordered) {
    const [, indent, num, delimiter, gap, content] = ordered;
    const nextNumber = String(Number.parseInt(num, 10) + 1);
    return { isEmpty: !content.trim(), prefix: `${indent}${nextNumber}${delimiter}${gap}` };
  }

  const quote = text.match(BLOCKQUOTE_LINE_RE);
  if (quote) {
    const [, indent, marks, gap, content] = quote;
    return { isEmpty: !content.trim(), prefix: `${indent}${marks}${gap || " "}` };
  }

  return null;
}
