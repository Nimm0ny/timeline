import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { markdown } from "@codemirror/lang-markdown";
import { Decoration, EditorView, WidgetType, keymap } from "@codemirror/view";
import { EditorState, RangeSetBuilder, StateField } from "@codemirror/state";

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

export function createMarkdownEditorExtensions(options = {}) {
  const editable = options.editable !== false;

  return [
    history(),
    markdown(),
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
