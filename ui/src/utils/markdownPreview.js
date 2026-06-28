function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

// Reject schemes that execute script when placed in an href and rendered via
// v-html. propertyHref guards link-typed property values the same way.
function safeLinkHref(href) {
  const raw = String(href || "").trim();
  // Browsers ignore whitespace inside the scheme (e.g. "java\nscript:"), so
  // strip it before testing for script-bearing schemes.
  const scheme = raw.replace(/\s+/g, "").toLowerCase();
  return /^(javascript|vbscript|data):/.test(scheme) ? "" : raw;
}

// Inline formatting for a code-free segment (image / link / strike / bold / em).
function renderInlineSegment(segment) {
  let output = segment;

  output = output.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_, alt, src) => {
    const safeAlt = escapeHtml(alt || "");
    const safeSrc = escapeHtml(src || "");
    return `<img class="timeline-markdown-image" src="${safeSrc}" alt="${safeAlt}" loading="lazy">`;
  });
  output = output.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, label, href) => {
    const safeHref = safeLinkHref(href);
    // Unsafe scheme → drop the anchor, render the (already-escaped) label as text.
    if (!safeHref) return label;
    return `<a class="timeline-markdown-link" href="${escapeHtml(safeHref)}" target="_blank" rel="noopener noreferrer">${label}</a>`;
  });
  output = output.replace(/~~([^~]+)~~/g, "<del>$1</del>");
  output = output.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  output = output.replace(/\*([^*]+)\*/g, "<em>$1</em>");

  return output;
}

function renderInline(value) {
  const escaped = escapeHtml(value);
  // Split on inline-code spans (kept as delimiters); only non-code segments get
  // inline formatting, so markdown inside `code` stays literal — matching the
  // editor's concealment and avoiding a double-render of e.g. `**x**`.
  return escaped
    .split(/(`[^`]+`)/g)
    .map((segment) =>
      segment.length > 1 && segment.startsWith("`") && segment.endsWith("`")
        ? `<code>${segment.slice(1, -1)}</code>`
        : renderInlineSegment(segment)
    )
    .join("");
}

export function plainTextFromMarkdown(markdown) {
  const imagePlaceholder = "TIMELINEIMAGEPLACEHOLDER";
  return String(markdown || "")
    .replace(/!\[[^\]]*\]\([^)]+\)/g, ` ${imagePlaceholder} `)
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, " $1 ")
    .replace(/[`#>*_~\-\[\]()]/g, " ")
    .replaceAll(imagePlaceholder, "[图片]")
    .replace(/\s+/g, " ")
    .trim();
}

export function renderMarkdownToHtml(markdown) {
  const source = String(markdown || "").replace(/\r\n/g, "\n");
  if (!source.trim()) {
    return "";
  }

  const lines = source.split("\n");
  const html = [];
  let listType = null; // "ul" | "ol" | null

  function closeList() {
    if (listType) {
      html.push(listType === "ol" ? "</ol>" : "</ul>");
      listType = null;
    }
  }

  function openList(type) {
    if (listType && listType !== type) closeList();
    if (!listType) {
      html.push(type === "ol" ? "<ol>" : "<ul>");
      listType = type;
    }
  }

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    const trimmed = line.trim();

    if (!trimmed) {
      closeList();
      continue;
    }

    // 水平分隔线（--- / *** / ___，整行无其它内容）。
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
      closeList();
      html.push("<hr>");
      continue;
    }

    const headingMatch = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      closeList();
      const level = headingMatch[1].length;
      html.push(`<h${level}>${renderInline(headingMatch[2])}</h${level}>`);
      continue;
    }

    const blockquoteMatch = trimmed.match(/^>\s+(.+)$/);
    if (blockquoteMatch) {
      closeList();
      html.push(`<blockquote>${renderInline(blockquoteMatch[1])}</blockquote>`);
      continue;
    }

    // 任务列表项须先于普通无序列表判定（避免 [ ] 被当作正文）。
    const taskMatch = trimmed.match(/^[-*]\s+\[([ xX])\]\s+(.+)$/);
    if (taskMatch) {
      openList("ul");
      const checked = taskMatch[1] !== " ";
      const box = `<span class="md-task"${checked ? ' data-checked="true"' : ""} role="checkbox" aria-checked="${checked}"></span>`;
      html.push(`<li class="md-task-item">${box}${renderInline(taskMatch[2])}</li>`);
      continue;
    }

    const orderedMatch = trimmed.match(/^(\d+)[.)]\s+(.+)$/);
    if (orderedMatch) {
      openList("ol");
      html.push(`<li>${renderInline(orderedMatch[2])}</li>`);
      continue;
    }

    const listMatch = trimmed.match(/^[-*]\s+(.+)$/);
    if (listMatch) {
      openList("ul");
      html.push(`<li>${renderInline(listMatch[1])}</li>`);
      continue;
    }

    closeList();
    html.push(`<p>${renderInline(trimmed)}</p>`);
  }

  closeList();
  return html.join("");
}
