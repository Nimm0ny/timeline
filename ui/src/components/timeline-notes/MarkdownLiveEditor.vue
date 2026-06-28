<script setup>
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { buildBlockInsertion } from "../../utils/editorMarkdown";
import { createMarkdownEditorExtensions } from "../../utils/cmMarkdownLivePreview";

const props = defineProps({
  modelValue: { type: String, default: "" },
  documentKey: { type: [String, Number], required: true },
  disabled: { type: Boolean, default: false },
});

const emit = defineEmits(["update:modelValue", "open-image", "paste-files", "drop-files", "ready"]);

const rootRef = ref(null);
let editorView = null;
let isApplyingExternalValue = false;

function createEditor() {
  if (!rootRef.value) {
    return;
  }
  const state = EditorState.create({
    doc: props.modelValue || "",
    extensions: createMarkdownEditorExtensions({
      editable: !props.disabled,
      onUpdate(value) {
        if (!isApplyingExternalValue) {
          emit("update:modelValue", value);
        }
      },
      onOpenImage(payload) {
        emit("open-image", payload);
      },
      onPasteFiles(files) {
        emit("paste-files", files);
      },
      onDropFiles(files) {
        emit("drop-files", files);
      },
    }),
  });

  editorView = new EditorView({ state, parent: rootRef.value });
}

function destroyEditor() {
  editorView?.destroy();
  editorView = null;
}

function replaceDocument(value, selectionAnchor = null) {
  if (!editorView) {
    return;
  }
  const nextValue = value || "";
  isApplyingExternalValue = true;
  editorView.dispatch({
    changes: { from: 0, to: editorView.state.doc.length, insert: nextValue },
    selection: selectionAnchor === null ? undefined : { anchor: selectionAnchor },
  });
  isApplyingExternalValue = false;
}

function focus() {
  editorView?.focus();
}

function getMarkdown() {
  return editorView?.state.doc.toString() ?? props.modelValue ?? "";
}

function insertBlock(markdownText) {
  if (!editorView) {
    return props.modelValue || "";
  }
  const current = editorView.state.doc.toString();
  const selection = editorView.state.selection.main;
  const next = buildBlockInsertion(current, selection.from, selection.to, markdownText);
  replaceDocument(next.text, next.cursor);
  emit("update:modelValue", next.text);
  return next.text;
}

function replaceSelection(text) {
  if (!editorView) {
    return props.modelValue || "";
  }
  const selection = editorView.state.selection.main;
  editorView.dispatch({
    changes: { from: selection.from, to: selection.to, insert: text },
    selection: { anchor: selection.from + text.length },
  });
  return editorView.state.doc.toString();
}

function resetDocument(markdownText) {
  replaceDocument(markdownText || "", 0);
}

defineExpose({ focus, getMarkdown, insertBlock, replaceSelection, resetDocument });

onMounted(() => {
  createEditor();
  // Lets the parent release the body-height placeholder once the editor is live,
  // so the read→edit swap never collapses the body (no row flash).
  emit("ready");
});
onBeforeUnmount(destroyEditor);

watch(
  () => props.modelValue,
  (value) => {
    if (!editorView) {
      return;
    }
    const nextValue = value || "";
    if (nextValue !== editorView.state.doc.toString()) {
      replaceDocument(nextValue);
    }
  },
);

watch(
  () => [props.documentKey, props.disabled],
  async () => {
    destroyEditor();
    await nextTick();
    createEditor();
  },
);
</script>

<template>
  <div ref="rootRef" class="body markdown-body markdown-live-editor"></div>
</template>
