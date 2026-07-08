import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { deleteMarkupBackward, markdown, markdownLanguage } from "@codemirror/lang-markdown";
import { HighlightStyle, syntaxHighlighting, syntaxTree } from "@codemirror/language";
import { tags } from "@lezer/highlight";
import { Decoration, EditorView, ViewPlugin, WidgetType, keymap } from "@codemirror/view";
import { autocompletion, completionKeymap } from "@codemirror/autocomplete";
import { EditorSelection, EditorState, RangeSetBuilder, StateField } from "@codemirror/state";
import { markdownListContinuation, selectionTouchesRange } from "./editorMarkdown.js";
import { WIKILINK_PATTERN, renderTableToHtml, scanFencedCodeBlocks, scanTables } from "./markdownPreview.js";

const IMAGE_MARKDOWN_RE = /!\[([^\]\n]*)\]\(([^)\n]+)\)/g;

export function lineRangesForPositions(doc, positions) {
  const ranges = [];
  positions.forEach((position) => {
    const line = doc.lineAt(position);
    if (ranges.some((range) => range.from === line.from && range.to === line.to)) {
      return;
    }
    ranges.push({ from: line.from, to: line.to });
  });
  return ranges;
}

export function lineRangesForDocumentRanges(doc, ranges) {
  const lineRanges = [];
  const seen = new Set();

  ranges.forEach((range) => {
    const from = Math.min(range.from, range.to);
    const to = Math.max(range.from, range.to);
    let line = doc.lineAt(from);

    while (line) {
      const key = `${line.from}:${line.to}`;
      if (!seen.has(key)) {
        seen.add(key);
        lineRanges.push({ from: line.from, to: line.to });
      }
      if (line.to >= to || line.number >= doc.lines) {
        break;
      }
      line = doc.line(line.number + 1);
    }
  });

  return lineRanges;
}

export function rangeIntersectsLine(range, lineFrom, lineTo) {
  return range.from <= lineTo && range.to >= lineFrom;
}

export function collectMarkdownImageTokens(markdownText, activeLineRanges = []) {
  const tokens = [];
  let offset = 0;
  const lines = markdownText.split("\n");

  lines.forEach((line) => {
    const lineFrom = offset;
    const lineTo = offset + line.length;
    collectMarkdownImageTokensFromLine(tokens, line, lineFrom, lineTo, activeLineRanges);

    offset = lineTo + 1;
  });

  return tokens;
}

function collectMarkdownImageTokensFromLine(tokens, lineText, lineFrom, lineTo, activeLineRanges) {
  const isActive = activeLineRanges.some((range) => rangeIntersectsLine(range, lineFrom, lineTo));

  if (isActive) {
    return;
  }

  IMAGE_MARKDOWN_RE.lastIndex = 0;
  let match = IMAGE_MARKDOWN_RE.exec(lineText);
  while (match) {
    tokens.push({
      from: lineFrom + match.index,
      to: lineFrom + match.index + match[0].length,
      alt: match[1] || "",
      src: match[2] || "",
      lineFrom,
      lineTo,
    });
    match = IMAGE_MARKDOWN_RE.exec(lineText);
  }
}

export function collectMarkdownImageTokensFromDoc(doc, activeLineRanges = []) {
  const tokens = [];
  const cursor = doc.iterLines();
  let offset = 0;

  for (let step = cursor.next(); !step.done; step = cursor.next()) {
    const lineFrom = offset;
    const lineTo = offset + step.value.length;
    collectMarkdownImageTokensFromLine(tokens, step.value, lineFrom, lineTo, activeLineRanges);
    offset = lineTo + 1;
  }

  return tokens;
}

function selectionLineRanges(state) {
  return lineRangesForDocumentRanges(state.doc, state.selection.ranges);
}

export function activeLineRangesSignature(lineRanges) {
  return lineRanges.map((range) => `${range.from}:${range.to}`).join("|");
}

class MarkdownImageWidget extends WidgetType {
  constructor(token, onOpenImage) {
    super();
    this.token = token;
    this.onOpenImage = onOpenImage;
  }

  eq(other) {
    return this.token.src === other.token.src && this.token.alt === other.token.alt;
  }

  toDOM() {
    const figure = document.createElement("figure");
    figure.className = "cm-md-image-widget";

    const image = document.createElement("img");
    image.className = "timeline-markdown-image";
    image.src = this.token.src;
    image.alt = this.token.alt;
    image.loading = "lazy";

    figure.appendChild(image);

    if (this.token.alt) {
      const caption = document.createElement("figcaption");
      caption.textContent = this.token.alt;
      figure.appendChild(caption);
    }

    figure.addEventListener("click", () => {
      this.onOpenImage?.({
        name: this.token.alt || "图片",
        imageUrl: this.token.src,
        url: this.token.src,
        mimeType: "image/*",
      });
    });

    return figure;
  }

  ignoreEvent(event) {
    return event.type !== "click";
  }
}

function buildImageDecorationSet(state, options, activeLineRanges = selectionLineRanges(state)) {
  const builder = new RangeSetBuilder();
  const tokens = collectMarkdownImageTokensFromDoc(state.doc, activeLineRanges);

  tokens.forEach((token) => {
    builder.add(
      token.from,
      token.to,
      Decoration.replace({
        widget: new MarkdownImageWidget(token, options?.onOpenImage),
        block: true,
      }),
    );
  });

  return builder.finish();
}

function buildImageDecorationState(state, options) {
  const activeLineRanges = selectionLineRanges(state);
  const activeSignature = activeLineRangesSignature(activeLineRanges);

  return {
    activeSignature,
    decorations: buildImageDecorationSet(state, options, activeLineRanges),
  };
}

export function markdownImageBlockWidgetField(options = {}) {
  return StateField.define({
    create(state) {
      return buildImageDecorationState(state, options);
    },
    update(value, transaction) {
      if (transaction.docChanged) {
        return buildImageDecorationState(transaction.state, options);
      }

      const decorations = value.decorations.map(transaction.changes);

      if (transaction.selection) {
        const activeLineRanges = selectionLineRanges(transaction.state);
        const activeSignature = activeLineRangesSignature(activeLineRanges);

        if (activeSignature === value.activeSignature) {
          return { activeSignature, decorations };
        }

        return {
          activeSignature,
          decorations: buildImageDecorationSet(transaction.state, options, activeLineRanges),
        };
      }

      return { ...value, decorations };
    },
    provide(field) {
      return EditorView.decorations.from(field, (value) => value.decorations);
    },
  });
}

// ── 围栏代码块（```/~~~）─────────────────────────────────────────────────────
// 围栏判定走 markdownPreview 的 scanFencedCodeBlocks（与读渲染器同一真源），
// 此处只把 0 基行号描述换算成 doc 位置并产出装饰（行背景盒 + 折叠围栏行）。
function buildCodeBlockDecorationSet(state) {
  const { doc } = state;
  const ranges = state.selection.ranges;
  const decos = [];

  for (const block of scanFencedCodeBlocks(doc.toString())) {
    if (block.openLine + 1 > doc.lines) continue;
    const openL = doc.line(block.openLine + 1);
    const closeL =
      block.closeLine != null && block.closeLine + 1 <= doc.lines ? doc.line(block.closeLine + 1) : null;
    const lastContentL =
      block.hasContent && block.contentToLine + 1 <= doc.lines ? doc.line(block.contentToLine + 1) : null;
    const tailL = closeL || lastContentL || openL;
    // 光标落在整块字符范围内即「活动」→ 显原文（含可编辑围栏）；否则折叠围栏。
    const active = selectionTouchesRange(ranges, openL.from, tailL.to);
    const folding = !active && block.hasContent && !!lastContentL;

    const boxFromLine = folding ? block.contentFromLine : block.openLine;
    const boxToLine = folding ? block.contentToLine : block.closeLine != null ? block.closeLine : block.contentToLine;
    for (let n = boxFromLine; n <= boxToLine && n + 1 <= doc.lines; n += 1) {
      const ln = doc.line(n + 1);
      let cls = "cm-md-code-line";
      if (n === boxFromLine) cls += " cm-md-code-first";
      if (n === boxToLine) cls += " cm-md-code-last";
      decos.push(Decoration.line({ class: cls }).range(ln.from));
    }

    if (folding) {
      // 开围栏：收「前换行 + 围栏文本」（[prevL.to, openL.to]），保留围栏后的换行，
      // 使首内容行仍是视觉行首、不丢行装饰。文首块无前行 → 退回收「围栏 + 后换行」。
      if (block.openLine > 0) {
        const prevL = doc.line(block.openLine); // 围栏前一行（1 基 = 0 基 openLine）
        decos.push(Decoration.replace({}).range(prevL.to, openL.to));
      } else {
        const firstContentL = doc.line(block.contentFromLine + 1);
        decos.push(Decoration.replace({}).range(openL.from, firstContentL.from));
      }
      if (closeL) {
        // 闭围栏：收「前换行 + 围栏文本」→ 收进末内容行尾，闭围栏后行仍是行首。
        decos.push(Decoration.replace({}).range(lastContentL.to, closeL.to));
      }
    }
  }

  return Decoration.set(decos, true);
}

function buildCodeBlockDecorationState(state) {
  return {
    activeSignature: activeLineRangesSignature(selectionLineRanges(state)),
    decorations: buildCodeBlockDecorationSet(state),
  };
}

// 跨行折叠（replace line breaks）只能由 StateField 提供，ViewPlugin 会抛
// RangeError。缓存同图片 field：仅当文档变或活动行集变才重建。
export function markdownCodeBlockField() {
  return StateField.define({
    create(state) {
      return buildCodeBlockDecorationState(state);
    },
    update(value, transaction) {
      if (transaction.docChanged) {
        return buildCodeBlockDecorationState(transaction.state);
      }
      const decorations = value.decorations.map(transaction.changes);
      if (transaction.selection) {
        const activeSignature = activeLineRangesSignature(selectionLineRanges(transaction.state));
        if (activeSignature === value.activeSignature) {
          return { activeSignature, decorations };
        }
        return buildCodeBlockDecorationState(transaction.state);
      }
      return { ...value, decorations };
    },
    provide(field) {
      return EditorView.decorations.from(field, (value) => value.decorations);
    },
  });
}

// ── GFM 表格 ─────────────────────────────────────────────────────────────────
// 判定走 markdownPreview 的 scanTables（与读渲染器同一真源）。光标不在表内时，整表
// 以块级 widget 渲染成 <table>（与读模式逐字节同 HTML → 读↔编辑零位移）；光标落入
// 表的字符范围则不渲染、显原文（管道符可编辑）。点击 widget 把光标落到对应源行（转原文）。
class MarkdownTableWidget extends WidgetType {
  constructor(table, doc) {
    super();
    this.table = table;
    const rowPos = [doc.line(table.fromLine + 1).from]; // 表头行起始偏移
    if (table.bodyFromLine != null) {
      for (let r = 0; r < table.rows.length; r += 1) {
        const lineNo = table.bodyFromLine + 1 + r;
        rowPos.push((lineNo <= doc.lines ? doc.line(lineNo) : doc.line(doc.lines)).from);
      }
    }
    this.rowPos = rowPos;
    this.html = renderTableToHtml(table, { rowPos });
  }

  eq(other) {
    return other.html === this.html;
  }

  toDOM(view) {
    const wrap = document.createElement("div");
    wrap.className = "cm-md-table-widget";
    wrap.innerHTML = this.html;
    // 点击 → 把光标落到被点的源行，selection 触达表范围 → StateField 转原文可编辑。
    wrap.addEventListener("mousedown", (event) => {
      const tr = event.target.closest ? event.target.closest("tr[data-pos]") : null;
      const pos = tr ? Number(tr.getAttribute("data-pos")) : this.rowPos[0];
      if (Number.isFinite(pos)) {
        event.preventDefault();
        view.dispatch({ selection: { anchor: pos }, scrollIntoView: true });
        view.focus();
      }
    });
    return wrap;
  }
}

function buildTableDecorationSet(state) {
  const { doc } = state;
  const ranges = state.selection.ranges;
  const decos = [];

  for (const table of scanTables(doc.toString())) {
    if (table.fromLine + 1 > doc.lines) continue;
    const headerL = doc.line(table.fromLine + 1);
    const lastL = table.toLine + 1 <= doc.lines ? doc.line(table.toLine + 1) : doc.line(doc.lines);
    // 光标落在整表字符范围内即「活动」→ 显原文；否则块级 widget 渲染整表。
    if (selectionTouchesRange(ranges, headerL.from, lastL.to)) continue;
    decos.push(
      Decoration.replace({ widget: new MarkdownTableWidget(table, doc), block: true }).range(
        headerL.from,
        lastL.to,
      ),
    );
  }

  return Decoration.set(decos, true);
}

function buildTableDecorationState(state) {
  return {
    activeSignature: activeLineRangesSignature(selectionLineRanges(state)),
    decorations: buildTableDecorationSet(state),
  };
}

// 跨行块 widget（replace line breaks）只能由 StateField 提供。缓存同图片/代码块 field。
export function markdownTableField() {
  return StateField.define({
    create(state) {
      return buildTableDecorationState(state);
    },
    update(value, transaction) {
      if (transaction.docChanged) {
        return buildTableDecorationState(transaction.state);
      }
      const decorations = value.decorations.map(transaction.changes);
      if (transaction.selection) {
        const activeSignature = activeLineRangesSignature(selectionLineRanges(transaction.state));
        if (activeSignature === value.activeSignature) {
          return { activeSignature, decorations };
        }
        return buildTableDecorationState(transaction.state);
      }
      return { ...value, decorations };
    },
    provide(field) {
      return EditorView.decorations.from(field, (value) => value.decorations);
    },
  });
}

export function filesFromEvent(event, key) {
  return Array.from(event[key]?.files || []).filter(Boolean);
}

// Typora 式实时渲染（基础档）：标记符（#、**、- 等 processingInstruction）淡化降噪，
// 标题分级、强调/斜体/删除线/行内码/链接/引用上样式。隐藏标记的「所见即所得」属进阶档。
export const markdownHighlightStyle = HighlightStyle.define([
  // 标题字号/字重对齐读模式 .markdown-body（浏览器默认 h1..h6 + 700），
  // 保证含标题文档在阅读↔编辑切换时标题不缩放、不位移（spec §7.2 同款排版）。
  { tag: tags.heading1, fontSize: "2em", fontWeight: "700" },
  { tag: tags.heading2, fontSize: "1.5em", fontWeight: "700" },
  { tag: tags.heading3, fontSize: "1.17em", fontWeight: "700" },
  { tag: tags.heading4, fontSize: "1em", fontWeight: "700" },
  { tag: tags.heading5, fontSize: "0.83em", fontWeight: "700" },
  { tag: tags.heading6, fontSize: "0.67em", fontWeight: "700" },
  { tag: tags.strong, fontWeight: "700" },
  { tag: tags.emphasis, fontStyle: "italic" },
  { tag: tags.strikethrough, textDecoration: "line-through" },
  { tag: tags.monospace, fontFamily: "var(--tn-font-mono, ui-monospace, SFMono-Regular, Menlo, monospace)", fontSize: "0.92em" },
  { tag: [tags.link, tags.url], color: "var(--accent)" },
  { tag: tags.quote, color: "var(--text-muted)" },
  { tag: tags.contentSeparator, color: "var(--text-faint)", fontWeight: "600" },
  { tag: tags.processingInstruction, color: "var(--text-faint)" },
]);

// ── Typora 进阶档：隐藏标记的所见即所得（Live Preview）────────────────────────
// 语法树 + 视口驱动：仅装饰可见行。光标所在的构造显原始标记（可编辑），其余
// 隐藏标记并就地渲染（# 消失、**粗**、- → •、[ ] → 复选框、--- → 分隔线）。
// 行内构造按节点范围判活、块级构造按整行判活（贴近 Obsidian 手感）。

class MarkdownBulletWidget extends WidgetType {
  eq() {
    return true;
  }
  toDOM() {
    const dot = document.createElement("span");
    dot.className = "cm-md-bullet";
    dot.textContent = "•";
    dot.setAttribute("aria-hidden", "true");
    return dot;
  }
}

class MarkdownRuleWidget extends WidgetType {
  eq() {
    return true;
  }
  toDOM() {
    const rule = document.createElement("span");
    rule.className = "cm-md-hr";
    rule.setAttribute("aria-hidden", "true");
    return rule;
  }
}

class MarkdownTaskWidget extends WidgetType {
  constructor(checked, from, to) {
    super();
    this.checked = checked;
    this.from = from;
    this.to = to;
  }
  eq(other) {
    return other.checked === this.checked && other.from === this.from && other.to === this.to;
  }
  toDOM(view) {
    const box = document.createElement("input");
    box.type = "checkbox";
    box.className = "cm-md-task";
    box.checked = this.checked;
    // 阻止取焦/移动光标，仅切换源码里的 [ ] ⇄ [x]。
    box.addEventListener("mousedown", (event) => event.preventDefault());
    box.addEventListener("change", () => {
      view.dispatch({
        changes: { from: this.from, to: this.to, insert: this.checked ? "[ ]" : "[x]" },
        userEvent: "input.markdown-task",
      });
    });
    return box;
  }
  ignoreEvent() {
    return true;
  }
}

// W4 维基链接 widget：把 [[<id>|别名]] / [[标题]] 渲成一枚原子链接片（光标不在 token 内时）。
// 三态：resolved（id 且目标存活，accent + 可点/悬浮）/ dangling（id 但目标已删，muted 不可点）/
// unbound（裸标题无 id，样式化但不可导航——唯一性归后端定，前端读渲染器不猜）。点击走 mousedown
// + preventDefault（不把光标移进 token，否则 selectionTouches → 显原文），与 MarkdownTaskWidget 同法；
// 导航/悬浮预览复用页面既有 pin-related / preview-related（handlers 由 EventDetailPane 注入）。
class WikilinkWidget extends WidgetType {
  constructor(display, id, state, handlers) {
    super();
    this.display = display;
    this.id = id; // number | null
    this.state = state; // "resolved" | "dangling" | "unbound"
    this.handlers = handlers || {};
  }
  eq(other) {
    return other.display === this.display && other.id === this.id && other.state === this.state;
  }
  toDOM() {
    const el = document.createElement("span");
    el.className = `cm-md-wikilink cm-md-wikilink-${this.state}`;
    el.textContent = this.display;
    const navigable = this.id != null && this.state === "resolved";
    if (navigable) {
      el.setAttribute("data-note-id", String(this.id));
      const payload = () => {
        const rect = el.getBoundingClientRect();
        return {
          id: this.id,
          anchor: { top: rect.top, right: rect.right, bottom: rect.bottom, left: rect.left, width: rect.width, height: rect.height },
        };
      };
      el.addEventListener("mousedown", (event) => {
        event.preventDefault();
        this.handlers.onOpen?.(payload());
      });
      el.addEventListener("mouseenter", () => this.handlers.onPreview?.(payload()));
      el.addEventListener("mouseleave", () => this.handlers.onHide?.(this.id));
    }
    return el;
  }
  ignoreEvent() {
    return true;
  }
}

const HEADING_NODE_NAMES = new Set([
  "ATXHeading1",
  "ATXHeading2",
  "ATXHeading3",
  "ATXHeading4",
  "ATXHeading5",
  "ATXHeading6",
]);

function buildLivePreviewDecorations(view, wikilinkConfig) {
  const { state } = view;
  const ranges = state.selection.ranges;
  const doc = state.doc;
  const all = [];
  const atomic = [];
  const quoteLines = new Set();
  const footnoteDefLines = new Set();

  // 表格行集合（doc 偏移区间）由 scanTables 决定——与 markdownTableField 同一真源。
  // ViewPlugin 必须跳过落在表内的任何节点：否则 scanTables 比 Lezer 宽松的情形下
  // （列数不齐、空表头等），Lezer 不产 Table 节点 → 单元格内 EmphasisMark 等被装饰，
  // 与 StateField 的块级 replace 重叠 → CM 抛错。按 scanTables 跳过即保证两端一致。
  const tableSkipRanges = scanTables(doc.toString()).map((table) => {
    const fromL = doc.line(table.fromLine + 1);
    const toL = table.toLine + 1 <= doc.lines ? doc.line(table.toLine + 1) : doc.line(doc.lines);
    return { from: fromL.from, to: toL.to };
  });
  const inSkippedTable = (pos) => tableSkipRanges.some((r) => pos >= r.from && pos <= r.to);

  const pushReplace = (from, to, spec) => {
    if (from >= to) return;
    const deco = Decoration.replace(spec);
    all.push(deco.range(from, to));
    atomic.push(deco.range(from, to));
  };
  const pushMark = (from, to, cls) => {
    if (from >= to) return;
    all.push(Decoration.mark({ class: cls }).range(from, to));
  };
  const pushLine = (linePos, cls, seen) => {
    if (seen.has(linePos)) return;
    seen.add(linePos);
    all.push(Decoration.line({ class: cls }).range(linePos));
  };
  const lineActive = (pos) => {
    const line = doc.lineAt(pos);
    return selectionTouchesRange(ranges, line.from, line.to);
  };
  const concealWithTrailingSpace = (from, to) => {
    let end = to;
    if (doc.sliceString(end, end + 1) === " ") end += 1;
    pushReplace(from, end, {});
  };

  for (const visible of view.visibleRanges) {
    syntaxTree(state).iterate({
      from: visible.from,
      to: visible.to,
      enter: (node) => {
        const name = node.name;

        // 图片由块级 image StateField 接管，跳过整棵子树避免装饰重叠。
        if (name === "Image") return false;

        // 围栏代码块由 markdownCodeBlockField（StateField）接管：行背景盒 +
        // 光标不在块内时折叠开/闭围栏行（跨行 replace 只能由 StateField 提供，
        // ViewPlugin 不许）。此处跳过整棵子树，避免 CodeMark 等被二次装饰。
        if (name === "FencedCode") return false;

        // 表格由 markdownTableField（StateField）接管。按 scanTables 行集跳过（而非
        // 依赖 Lezer 的 Table 节点名），保证与块级 widget 同一判定，杜绝装饰重叠。
        if (inSkippedTable(node.from)) return false;

        if (name === "HeaderMark") {
          if (!lineActive(node.from)) concealWithTrailingSpace(node.from, node.to);
          return undefined;
        }

        if (name === "EmphasisMark" || name === "StrikethroughMark") {
          const parent = node.node.parent;
          if (parent && !selectionTouchesRange(ranges, parent.from, parent.to)) {
            pushReplace(node.from, node.to, {});
          }
          return undefined;
        }

        if (name === "InlineCode") {
          const marks = node.node.getChildren("CodeMark");
          if (marks.length >= 2) {
            pushMark(marks[0].to, marks[marks.length - 1].from, "cm-md-inline-code");
          }
          return undefined; // 继续下探，由 CodeMark 隐藏反引号
        }

        if (name === "CodeMark") {
          const parent = node.node.parent;
          if (parent && parent.name === "InlineCode" && !selectionTouchesRange(ranges, parent.from, parent.to)) {
            pushReplace(node.from, node.to, {});
          }
          return undefined;
        }

        if (name === "Link") {
          const marks = node.node.getChildren("LinkMark");
          // 脚注引用/定义 [^…]（无 URL，2 个 LinkMark）由下方按行 regex 处理：Lezer 无脚注
          // 语法，会把同行多个 [^x] 合并成一个 Link、把定义行当 LinkReference——解析不稳，故跳过。
          // 但 [^x](url)（带 URL，4 个 LinkMark）是真链接，照常渲染，与读渲染器 link-first 一致。
          if (doc.sliceString(node.from, node.from + 2) === "[^" && marks.length < 4) return false;
          // 维基链接 [[..]]：Lezer 可能把内层 [..] 当 shortcut 链接节点（2 个 LinkMark、无 URL）。交给
          // 下方 wikilink regex 段渲染，这里跳过整棵子树避免两处 replace 重叠。**仅当无 URL（<4 marks）**
          // 时才跳——否则 [[foo](url)] 这类真的带链接会被误吞、不渲染。命中两形：节点起于外层 [[，或内层
          // 被外层 [ ] 包裹。
          if (
            marks.length < 4 &&
            (doc.sliceString(node.from, node.from + 2) === "[[" ||
              (doc.sliceString(node.from - 1, node.from) === "[" && doc.sliceString(node.to, node.to + 1) === "]"))
          )
            return false;
          if (selectionTouchesRange(ranges, node.from, node.to)) return false; // 编辑态显原文
          if (marks.length >= 2) {
            const open = marks[0];
            const close = marks[1];
            pushReplace(node.from, open.to, {}); // 隐藏 [
            pushReplace(close.from, node.to, {}); // 隐藏 ](url)
            pushMark(open.to, close.from, "cm-md-link"); // 链接文字着色
          }
          return false;
        }

        if (name === "ListMark") {
          const item = node.node.parent; // ListItem
          const list = item ? item.parent : null;
          if (!list || list.name !== "BulletList") return undefined; // 有序列表保留数字
          if (lineActive(node.from)) return undefined;
          if (item.getChild("Task")) {
            pushReplace(node.from, node.to, {}); // 任务项：隐藏 bullet，仅留复选框
          } else {
            pushReplace(node.from, node.to, { widget: new MarkdownBulletWidget() });
          }
          return undefined;
        }

        if (name === "TaskMarker") {
          if (lineActive(node.from)) return undefined;
          const checked = /[xX]/.test(doc.sliceString(node.from, node.to));
          pushReplace(node.from, node.to, {
            widget: new MarkdownTaskWidget(checked, node.from, node.to),
          });
          return undefined;
        }

        if (name === "QuoteMark") {
          const line = doc.lineAt(node.from);
          pushLine(line.from, "cm-md-quote-line", quoteLines);
          if (!selectionTouchesRange(ranges, line.from, line.to)) {
            concealWithTrailingSpace(node.from, node.to);
          }
          return undefined;
        }

        if (name === "HorizontalRule") {
          const line = doc.lineAt(node.from);
          if (!selectionTouchesRange(ranges, line.from, line.to)) {
            pushReplace(line.from, line.to, { widget: new MarkdownRuleWidget() });
          }
          return undefined;
        }

        return undefined;
      },
    });
  }

  // ── 脚注（按行 regex，不走语法树）──────────────────────────────────────────
  // 行内 [^label] → 上标；行首 [^label]: → 定义行。须跳过表格/代码/图片块区：表格 widget /
  // 代码 / 图片各自块级 replace，脚注 replace 落进去会重叠令 CM 抛错。表格单元格里的脚注由
  // renderTableToHtml→renderInline 渲染（读与 widget 同走此路、一致）；代码/图片块内读渲染器
  // 不渲染脚注，故跳过即保一致。
  const codeSkipRanges = scanFencedCodeBlocks(doc.toString()).map((b) => {
    const fromL = doc.line(b.openLine + 1);
    const toIdx = Math.min(b.closeLine != null ? b.closeLine : doc.lines - 1, doc.lines - 1);
    return { from: fromL.from, to: doc.line(toIdx + 1).to };
  });
  const imageSkipRanges = collectMarkdownImageTokensFromDoc(doc, []).map((t) => ({ from: t.from, to: t.to }));
  const inBlockSkip = (pos) =>
    inSkippedTable(pos) ||
    codeSkipRanges.some((r) => pos >= r.from && pos <= r.to) ||
    imageSkipRanges.some((r) => pos >= r.from && pos < r.to);
  const FN_REF_RE = /\[\^([^\]\s]+)\]/g;
  for (const visible of view.visibleRanges) {
    const firstLine = doc.lineAt(visible.from).number;
    const lastLine = doc.lineAt(visible.to).number;
    for (let n = firstLine; n <= lastLine; n += 1) {
      const line = doc.line(n);
      if (inBlockSkip(line.from)) continue;
      const text = line.text;
      // 定义行 [^label]: 内容（须行首不缩进）→ 行首标记隐藏 + label 前缀 + 整行 def 样式。
      const defMatch = /^\[\^([^\]\s]+)\]:/.exec(text);
      if (defMatch && !selectionTouchesRange(ranges, line.from, line.to)) {
        const label = defMatch[1];
        const labelStart = line.from + 2; // 跳过 [^
        const labelEnd = labelStart + label.length;
        pushLine(line.from, "cm-md-footnote-def-line", footnoteDefLines);
        pushReplace(line.from, labelStart, {}); // [^
        pushMark(labelStart, labelEnd, "cm-md-footnote-label");
        pushReplace(labelEnd, labelEnd + 2, {}); // ]:（冒号后空白保留，与读渲染器一致）
      }
      // 行内引用 [^label]（含定义行内容里的引用；定义行首标记 index 0 已处理、跳过）。
      FN_REF_RE.lastIndex = 0;
      let m;
      while ((m = FN_REF_RE.exec(text)) !== null) {
        if (defMatch && m.index === 0) continue;
        // [[^…]]：前一字符是 [ → 这个 [^ 是维基链接的内层，交给下方 wikilink 段整体渲染。脚注不在
        // 此插装饰，否则脚注 replace(内层) 与 wikilink replace(整段) 重叠 → Decoration.set 抛错、整个
        // 编辑器渲染崩。
        if (m.index > 0 && text[m.index - 1] === "[") continue;
        if (text[m.index + m[0].length] === "(") continue; // [^x](url) 是真链接，由语法树渲染
        const from = line.from + m.index;
        const to = from + m[0].length;
        if (inBlockSkip(from)) continue;
        if (selectionTouchesRange(ranges, from, to)) continue; // 光标在引用内显原文
        const labelStart = from + 2; // 跳过 [^
        const labelEnd = to - 1; // ] 前
        pushReplace(from, labelStart, {}); // [^
        pushMark(labelStart, labelEnd, "cm-md-footnote-ref");
        pushReplace(labelEnd, to, {}); // ]
      }
    }
  }

  // ── 维基链接 [[<id>|别名]] / [[标题]]（按行 regex，镜像脚注段）──────────────────────
  // caret 在 token 内 → 显原文；否则 → atomic 链接 widget。跳过表格/代码/图片块（同脚注，避免与块级
  // replace 重叠）。id 的解析/落库在后端（§6.3），此处纯装饰：某 id 是否 resolved 看 wikilinkConfig
  // .targets（= 该笔记 linkTargets，随 autocomplete 选中即时补入，见 wikilinkCompletionSource）。
  const wlTargets = wikilinkConfig?.targets || {};
  const wlHandlers = {
    onOpen: wikilinkConfig?.onOpen,
    onPreview: wikilinkConfig?.onPreview,
    onHide: wikilinkConfig?.onHide,
  };
  const WIKILINK_LIVE_RE = new RegExp(WIKILINK_PATTERN, "g");
  for (const visible of view.visibleRanges) {
    const firstLine = doc.lineAt(visible.from).number;
    const lastLine = doc.lineAt(visible.to).number;
    for (let n = firstLine; n <= lastLine; n += 1) {
      const line = doc.line(n);
      if (inBlockSkip(line.from)) continue;
      const text = line.text;
      WIKILINK_LIVE_RE.lastIndex = 0;
      let wm;
      while ((wm = WIKILINK_LIVE_RE.exec(text)) !== null) {
        const title = (wm[2] || "").trim();
        if (!title) continue;
        const from = line.from + wm.index;
        const to = from + wm[0].length;
        if (inBlockSkip(from)) continue;
        if (selectionTouchesRange(ranges, from, to)) continue; // 光标在内显原文（读↔编辑同位）
        const id = wm[1] ? Number(wm[1]) : null;
        let stateName;
        if (id == null) stateName = "unbound";
        else if (Object.prototype.hasOwnProperty.call(wlTargets, String(id))) stateName = "resolved";
        else stateName = "dangling";
        pushReplace(from, to, { widget: new WikilinkWidget(title, id, stateName, wlHandlers) });
      }
    }
  }

  return {
    decorations: Decoration.set(all, true),
    atomic: Decoration.set(atomic, true),
  };
}

export function markdownLivePreviewPlugin(wikilinkConfig) {
  return ViewPlugin.fromClass(
    class {
      constructor(view) {
        const built = buildLivePreviewDecorations(view, wikilinkConfig);
        this.decorations = built.decorations;
        this.atomic = built.atomic;
      }
      update(update) {
        if (update.docChanged || update.selectionSet || update.viewportChanged) {
          const built = buildLivePreviewDecorations(update.view, wikilinkConfig);
          this.decorations = built.decorations;
          this.atomic = built.atomic;
        }
      }
    },
    {
      decorations: (value) => value.decorations,
      provide: (plugin) =>
        EditorView.atomicRanges.of((view) => view.plugin(plugin)?.atomic || Decoration.none),
    },
  );
}

function continueMarkdownStructure(view) {
  const { state } = view;
  const range = state.selection.main;
  if (!range.empty) return false;
  const line = state.doc.lineAt(range.from);
  const continuation = markdownListContinuation(line.text);
  if (!continuation) return false;
  if (continuation.isEmpty) {
    view.dispatch({
      changes: { from: line.from, to: line.to, insert: "" },
      selection: { anchor: line.from },
      userEvent: "delete.markdown-list",
    });
    return true;
  }
  if (range.from !== line.to) return false;
  const insert = state.lineBreak + continuation.prefix;
  view.dispatch({
    changes: { from: range.from, insert },
    selection: { anchor: range.from + insert.length },
    userEvent: "input.markdown-list",
  });
  return true;
}

function wrapSelectionWith(view, marker) {
  const transaction = view.state.changeByRange((range) => {
    const selected = view.state.sliceDoc(range.from, range.to);
    const insert = `${marker}${selected}${marker}`;
    return {
      changes: { from: range.from, to: range.to, insert },
      range: EditorSelection.range(range.from + marker.length, range.from + marker.length + selected.length),
    };
  });
  view.dispatch(transaction, { userEvent: "input.markdown-wrap" });
  return true;
}

function insertMarkdownLink(view) {
  const transaction = view.state.changeByRange((range) => {
    const selected = view.state.sliceDoc(range.from, range.to) || "链接文字";
    const insert = `[${selected}]()`;
    return {
      changes: { from: range.from, to: range.to, insert },
      range: EditorSelection.cursor(range.from + insert.length - 1),
    };
  });
  view.dispatch(transaction, { userEvent: "input.markdown-link" });
  return true;
}

export const markdownEditingKeymap = [
  { key: "Enter", run: continueMarkdownStructure },
  { key: "Backspace", run: deleteMarkupBackward },
  { key: "Mod-b", run: (view) => wrapSelectionWith(view, "**") },
  { key: "Mod-i", run: (view) => wrapSelectionWith(view, "*") },
  { key: "Mod-k", run: insertMarkdownLink },
];

// W4 `[[` 自动补全源：光标前是未闭合的 [[<query> 时，用 FTS（searchNotes 复用 /api/search）拉候选，
// 选中即插 id 形态 [[<id>|别名]]（id 寻址=改名不断链，§6.1）。FTS 已排序/筛选，故 filter:false 让 CM
// 不用含 "[[" 的原文二次过滤把候选全滤掉。apply 用函数：插入之外还把选中 id 记进 wikilinkConfig.targets，
// 令装饰下一帧即渲 resolved，不必等重开笔记刷新 linkTargets（否则刚插的链接会瞬间显 dangling）。
function wikilinkCompletionSource(searchNotes, wikilinkConfig) {
  return async (context) => {
    const token = context.matchBefore(/\[\[([^\[\]|\n]*)$/);
    if (!token) return null;
    const query = token.text.slice(2);
    if (!context.explicit && !query.trim()) return null; // 刚敲 [[ 先不弹，等首字（Ctrl-Space 除外）
    let rows = [];
    try {
      rows = (await searchNotes(query, { limit: 20 })) || [];
    } catch {
      rows = [];
    }
    const options = rows
      .filter((row) => row && row.id != null)
      .map((row) => {
        const headline = (row.headline || "").trim() || `#${row.id}`;
        const insert = `[[${row.id}|${headline}]]`;
        return {
          label: headline,
          detail: row.container || undefined,
          type: "link",
          apply: (view, _completion, from, to) => {
            // 若光标后紧跟已存在的 ]]（用户先敲了闭合再回填），一并吞掉——插入自带 ]]，否则出现 ]]]]。
            const end = view.state.sliceDoc(to, to + 2) === "]]" ? to + 2 : to;
            view.dispatch({
              changes: { from, to: end, insert },
              selection: { anchor: from + insert.length },
              userEvent: "input.complete",
            });
            if (wikilinkConfig?.targets) wikilinkConfig.targets[String(row.id)] = headline;
          },
        };
      });
    return { from: token.from, options, filter: false };
  };
}

export function createMarkdownEditorExtensions(options = {}) {
  const editable = options.editable !== false;
  // 装饰与补全共享同一 config 对象（apply 会就地补 targets）；即便无 searchNotes 也建，好让
  // 装饰照常按 linkTargets 判 resolved/dangling。
  const wikilinkConfig = {
    targets: { ...(options.linkTargets || {}) },
    onOpen: options.onOpenWikilink,
    onPreview: options.onPreviewWikilink,
    onHide: options.onHideWikilinkPreview,
  };
  const wikilinkExtensions = options.searchNotes
    ? [
        autocompletion({ override: [wikilinkCompletionSource(options.searchNotes, wikilinkConfig)], icons: false }),
        keymap.of(completionKeymap),
      ]
    : [];

  return [
    history(),
    markdown({ base: markdownLanguage }),
    syntaxHighlighting(markdownHighlightStyle),
    markdownLivePreviewPlugin(wikilinkConfig),
    // 补全 keymap 须在 markdownEditingKeymap 之前：弹窗开时 Enter 走 acceptCompletion，无弹窗时
    // acceptCompletion 返回 false → 落到下面的 continueMarkdownStructure（列表续行），互不打架。
    ...wikilinkExtensions,
    keymap.of(markdownEditingKeymap),
    keymap.of([...historyKeymap, ...defaultKeymap]),
    EditorView.lineWrapping,
    EditorState.readOnly.of(!editable),
    EditorView.editable.of(editable),
    markdownImageBlockWidgetField({ onOpenImage: options.onOpenImage }),
    markdownCodeBlockField(),
    markdownTableField(),
    EditorView.updateListener.of((update) => {
      if (update.docChanged) {
        options.onUpdate?.(update.state.doc.toString());
      }
    }),
    EditorView.domEventHandlers({
      paste(event) {
        const files = filesFromEvent(event, "clipboardData");
        if (!files.length) {
          return false;
        }
        event.preventDefault();
        options.onPasteFiles?.(files);
        return true;
      },
      drop(event) {
        const files = filesFromEvent(event, "dataTransfer");
        if (!files.length) {
          return false;
        }
        event.preventDefault();
        options.onDropFiles?.(files);
        return true;
      },
    }),
  ];
}
