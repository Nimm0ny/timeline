import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { deleteMarkupBackward, markdown, markdownLanguage } from "@codemirror/lang-markdown";
import { HighlightStyle, syntaxHighlighting, syntaxTree } from "@codemirror/language";
import { tags } from "@lezer/highlight";
import { Decoration, EditorView, ViewPlugin, WidgetType, keymap } from "@codemirror/view";
import { EditorSelection, EditorState, RangeSetBuilder, StateField } from "@codemirror/state";
import { markdownListContinuation, selectionTouchesRange } from "./editorMarkdown.js";

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
  { tag: tags.monospace, fontFamily: "var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace)", fontSize: "0.92em" },
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

const HEADING_NODE_NAMES = new Set([
  "ATXHeading1",
  "ATXHeading2",
  "ATXHeading3",
  "ATXHeading4",
  "ATXHeading5",
  "ATXHeading6",
]);

function buildLivePreviewDecorations(view) {
  const { state } = view;
  const ranges = state.selection.ranges;
  const doc = state.doc;
  const all = [];
  const atomic = [];
  const quoteLines = new Set();

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
          if (selectionTouchesRange(ranges, node.from, node.to)) return false; // 编辑态显原文
          const marks = node.node.getChildren("LinkMark");
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

  return {
    decorations: Decoration.set(all, true),
    atomic: Decoration.set(atomic, true),
  };
}

export function markdownLivePreviewPlugin() {
  return ViewPlugin.fromClass(
    class {
      constructor(view) {
        const built = buildLivePreviewDecorations(view);
        this.decorations = built.decorations;
        this.atomic = built.atomic;
      }
      update(update) {
        if (update.docChanged || update.selectionSet || update.viewportChanged) {
          const built = buildLivePreviewDecorations(update.view);
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

export function createMarkdownEditorExtensions(options = {}) {
  const editable = options.editable !== false;

  return [
    history(),
    markdown({ base: markdownLanguage }),
    syntaxHighlighting(markdownHighlightStyle),
    markdownLivePreviewPlugin(),
    keymap.of(markdownEditingKeymap),
    keymap.of([...historyKeymap, ...defaultKeymap]),
    EditorView.lineWrapping,
    EditorState.readOnly.of(!editable),
    EditorView.editable.of(editable),
    markdownImageBlockWidgetField({ onOpenImage: options.onOpenImage }),
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
