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

// 围栏代码块（```/~~~）扫描器——读渲染器与 CM 编辑器共用此单一真源，保证两
// 端对「哪几行是代码块」判定一致（读↔编辑零位移的前提）。返回 0 基行号描述。
export function scanFencedCodeBlocks(text) {
  const lines = String(text ?? "").replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const open = lines[i].trim().match(/^(`{3,}|~{3,})(.*)$/);
    // 反引号围栏的 info 串不得含反引号（否则不是合法围栏）。
    if (open && !(open[1][0] === "`" && open[2].includes("`"))) {
      const fenceChar = open[1][0];
      const fenceLen = open[1].length;
      const lang = open[2].trim().split(/\s+/)[0] || "";
      let j = i + 1;
      let closed = false;
      for (; j < lines.length; j += 1) {
        const close = lines[j].trim().match(/^(`{3,}|~{3,})$/);
        if (close && close[1][0] === fenceChar && close[1].length >= fenceLen) {
          closed = true;
          break;
        }
      }
      const contentFromLine = i + 1;
      const contentToLine = (closed ? j : lines.length) - 1;
      blocks.push({
        openLine: i,
        closeLine: closed ? j : null,
        contentFromLine,
        contentToLine,
        hasContent: contentToLine >= contentFromLine,
        closed,
        lang,
      });
      i = closed ? j + 1 : lines.length;
    } else {
      i += 1;
    }
  }
  return blocks;
}

// 表格单元格拆分：去掉首尾各一个 `|`，按未转义的 `|` 切分，`\|` 还原成字面竖线。
function splitTableRow(line) {
  let s = String(line).trim();
  if (s.startsWith("|")) s = s.slice(1);
  if (s.endsWith("|")) s = s.slice(0, -1);
  const cells = [];
  let cur = "";
  for (let k = 0; k < s.length; k += 1) {
    const ch = s[k];
    if (ch === "\\" && s[k + 1] === "|") {
      cur += "|";
      k += 1;
      continue;
    }
    if (ch === "|") {
      cells.push(cur.trim());
      cur = "";
      continue;
    }
    cur += ch;
  }
  cells.push(cur.trim());
  return cells;
}

// 分隔行（| --- | :--: |）→ 每列对齐数组（left/right/center/null）；不是合法分隔行返回 null。
// 必须含 `|`（否则 `---` 仍是水平分隔线 <hr>，而非单列表格）。
function parseTableDelimiter(line) {
  const s = String(line).trim();
  if (!s.includes("|") || !s.includes("-")) return null;
  const cells = splitTableRow(s);
  if (cells.length === 0) return null;
  const aligns = [];
  for (const cell of cells) {
    if (!/^:?-+:?$/.test(cell)) return null;
    const left = cell.startsWith(":");
    const right = cell.endsWith(":");
    aligns.push(left && right ? "center" : right ? "right" : left ? "left" : null);
  }
  return aligns;
}

// GFM 表格扫描器——读渲染器与 CM 编辑器共用此单一真源（同围栏代码块）。表头行须
// 含 `|` 且下一行是合法分隔行；表体行连续到空行/无 `|`/代码围栏边界为止。返回 0 基行号。
export function scanTables(text) {
  const lines = String(text ?? "").replace(/\r\n/g, "\n").split("\n");
  const lastIdx = lines.length - 1;
  const fences = scanFencedCodeBlocks(text);
  const inFence = (n) =>
    fences.some((b) => n >= b.openLine && n <= (b.closeLine != null ? b.closeLine : lastIdx));

  const tables = [];
  let i = 0;
  while (i < lines.length) {
    if (inFence(i)) {
      i += 1;
      continue;
    }
    const headerLine = lines[i];
    const delimLine = i + 1 <= lastIdx ? lines[i + 1] : null;
    const headerHasPipe = headerLine.includes("|") && headerLine.trim() !== "";
    const aligns = delimLine != null && !inFence(i + 1) ? parseTableDelimiter(delimLine) : null;
    const header = headerHasPipe && aligns ? splitTableRow(headerLine) : null;
    // GFM：分隔行列数须等于表头列数，且表头至少一个非空单元格——否则普通含 | 的正文
    // （后跟一行 dash）会被误判成表；也确保与 Lezer 的表格识别一致（CM 编辑器据此跳过）。
    const isTable = header != null && aligns.length === header.length && header.some((cell) => cell !== "");
    if (isTable) {
      const colCount = header.length;
      const alignsNorm = [];
      for (let c = 0; c < colCount; c += 1) alignsNorm.push(aligns[c] != null ? aligns[c] : null);
      const rows = [];
      let j = i + 2;
      for (; j <= lastIdx; j += 1) {
        if (inFence(j)) break;
        const r = lines[j];
        if (r.trim() === "" || !r.includes("|")) break;
        rows.push(splitTableRow(r));
      }
      const hasBody = rows.length > 0;
      const toLine = hasBody ? j - 1 : i + 1;
      tables.push({
        fromLine: i,
        toLine,
        headerLine: i,
        delimiterLine: i + 1,
        bodyFromLine: hasBody ? i + 2 : null,
        bodyToLine: hasBody ? toLine : null,
        aligns: alignsNorm,
        header,
        rows,
      });
      i = toLine + 1;
    } else {
      i += 1;
    }
  }
  return tables;
}

// 把 scanTables 的描述渲染成 <table class="md-table">——读渲染器与 CM widget 共用，
// 保证两端 HTML 结构一致（读↔编辑零位移）。opts.rowPos 仅 CM widget 传入：给每个
// <tr> 加 data-pos（该行在文档中的起始偏移），供点击表格时把光标落到对应行（转原文可编辑）。
export function renderTableToHtml(table, opts = {}) {
  const rowPos = opts.rowPos || null;
  const alignStyle = (a) => (a ? ` style="text-align:${a}"` : "");
  const posAttr = (idx) => (rowPos && rowPos[idx] != null ? ` data-pos="${rowPos[idx]}"` : "");
  const headCells = table.header
    .map((cell, c) => `<th${alignStyle(table.aligns[c])}>${renderInline(cell)}</th>`)
    .join("");
  const head = `<thead><tr${posAttr(0)}>${headCells}</tr></thead>`;
  let body = "";
  if (table.rows.length) {
    const rowsHtml = table.rows
      .map((row, r) => {
        const tds = [];
        for (let c = 0; c < table.header.length; c += 1) {
          tds.push(`<td${alignStyle(table.aligns[c])}>${renderInline(row[c] != null ? row[c] : "")}</td>`);
        }
        return `<tr${posAttr(r + 1)}>${tds.join("")}</tr>`;
      })
      .join("");
    body = `<tbody>${rowsHtml}</tbody>`;
  }
  return `<table class="md-table">${head}${body}</table>`;
}

export function renderMarkdownToHtml(markdown) {
  const source = String(markdown || "").replace(/\r\n/g, "\n");
  if (!source.trim()) {
    return "";
  }

  const lines = source.split("\n");
  const codeBlockByOpen = new Map(scanFencedCodeBlocks(source).map((block) => [block.openLine, block]));
  const tableByHeader = new Map(scanTables(source).map((table) => [table.fromLine, table]));
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

  for (let i = 0; i < lines.length; i += 1) {
    // 围栏代码块（``` / ~~~）：内容原样保留（HTML 转义、不套 inline markdown、
    // 不当列表/标题），空白靠 CSS white-space: pre-wrap。判定走共享 scanner。
    const codeBlock = codeBlockByOpen.get(i);
    if (codeBlock) {
      closeList();
      const langClass = codeBlock.lang ? ` class="language-${escapeHtml(codeBlock.lang)}"` : "";
      const body = codeBlock.hasContent ? lines.slice(codeBlock.contentFromLine, codeBlock.contentToLine + 1) : [];
      const code = body.map((bodyLine) => escapeHtml(bodyLine)).join("\n");
      html.push(`<pre class="md-code-block"><code${langClass}>${code}</code></pre>`);
      i = codeBlock.closed ? codeBlock.closeLine : lines.length - 1; // 跳过整块（含闭合行）。
      continue;
    }

    // GFM 表格：判定走共享 scanTables（与 CM 编辑器同一真源）。整表渲染为 <table>，
    // 单元格内容过 renderInline（行内 markdown），随后跳过整块。
    const table = tableByHeader.get(i);
    if (table) {
      closeList();
      html.push(renderTableToHtml(table));
      i = table.toLine; // 循环 i += 1 → 表后一行。
      continue;
    }

    const rawLine = lines[i];
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
