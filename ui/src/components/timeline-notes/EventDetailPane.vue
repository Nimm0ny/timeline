<script setup>
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { api } from "@/composables/useApi";
import { pushToast } from "@/composables/useToast";
import { CONTENT_LIMITS } from "@/constants/contentLimits";
import AttachmentModal from "@/components/timeline-notes/AttachmentModal.vue";
import OptionPicker from "@/components/timeline-notes/OptionPicker.vue";
import TimelineLucideIcon from "@/components/timeline-notes/TimelineLucideIcon.vue";
import {
  buildEditorDraft,
  buildReadableDetailGroups,
  formatEventDate,
  formatEventDisplayDate,
  isCheckboxChecked,
  isCheckboxColumn,
  isLinkColumn,
  isOptionColumn,
  normalizeEventExtra,
  normalizeTopicColumns,
  propertyHref,
  propertyTypeIcon,
  resolvePropertyChips,
} from "@/utils/timelineNotes";
import { renderMarkdownToHtml } from "@/utils/markdownPreview";
import {
  attachmentIconName,
  attachmentKind,
  buildAttachmentMarkdown,
  filterRelatedEventCandidates,
} from "@/utils/editorMarkdown";

const props = defineProps({
  event: {
    type: Object,
    default: null,
  },
  candidateEvents: {
    type: Array,
    default: () => [],
  },
  topicTitle: {
    type: String,
    default: "",
  },
  topicColumns: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
  error: {
    type: String,
    default: "",
  },
  mode: {
    type: String,
    default: "view",
  },
  saving: {
    type: Boolean,
    default: false,
  },
  mobile: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits([
  "cancel",
  "close",
  "edit",
  "open-menu",
  "move-to-trash",
  "preview-related",
  "hide-related-preview",
  "pin-related",
  "save",
  "toggle-favorite",
  "dirty-change",
  "preview-change",
  "create-option",
]);

// Keep the CM6 editor in its own lazy chunk, but expose the loader so we can warm
// it while the user is still reading (see onMounted) — otherwise entering edit
// mounts it a frame late, collapsing the body and flashing the rows below.
const loadMarkdownLiveEditor = () => import("@/components/timeline-notes/MarkdownLiveEditor.vue");
const MarkdownLiveEditor = defineAsyncComponent(loadMarkdownLiveEditor);

const bodyEditorRef = ref(null);
const bodyWrapRef = ref(null);
const bodyMinHeight = ref(0);
const initialSnapshot = ref("");
const uploading = ref(false);
const sessionUploads = ref([]);
const pendingDeleteImages = ref([]);
const relatedSearchQuery = ref("");
const showRelatedSearch = ref(false);
const relatedSearchInputRef = ref(null);
const modalAttachment = ref(null);
const dateEditorOpen = ref(false);
const eraEditorOpen = ref(false);
const kebabOpen = ref(false);
const addPropOpen = ref(false);
const trashArmed = ref(false);
const revealedKeys = ref(new Set());
const editorResetSeq = ref(0);
const createSessionSeq = ref(0);

const draft = reactive(buildEditorDraft(null, props.topicColumns));

const inEditMode = computed(() => props.mode === "edit" || props.mode === "create");
const isDeleted = computed(() => Boolean(props.event?.deletedAt || draft.deletedAt));
const topicColumns = computed(() => normalizeTopicColumns(props.topicColumns));
const readableGroups = computed(() => buildReadableDetailGroups(props.event));
const renderedBody = computed(() => renderMarkdownToHtml(props.event?.bodyMarkdown || ""));
const editorDocumentKey = computed(() => {
  if (draft.id) return `event:${draft.id}:${editorResetSeq.value}`;
  return `create:${createSessionSeq.value}:${editorResetSeq.value}`;
});

// Unified property section: option-typed properties edit via OptionPicker, free
// ones via inline inputs. Every property renders in BOTH read and edit modes
// (empty values show 「—」), so toggling read <-> edit causes zero vertical shift.
function chipsFor(column) {
  return resolvePropertyChips(props.event, column);
}

function onCreateOption(payload) {
  emit("create-option", payload);
}

// Obsidian-style metadata: every property row carries a small type icon so the
// 属性 area reads as scannable metadata (date/group join the same list). Glyphs
// come from the shared PROPERTY_TYPE_ICONS map (see utils/timelineNotes).
function propertyIcon(column) {
  return propertyTypeIcon(column?.type);
}

function freeInputType(column) {
  if (column?.type === "number") return "number";
  if (column?.type === "date") return "date";
  if (column?.type === "url") return "url";
  if (column?.type === "email") return "email";
  if (column?.type === "phone") return "tel";
  return "text";
}

function setCheckbox(column, event) {
  draft.extra[column.key] = event.target.checked ? "true" : "false";
}

const selectedRelatedEvents = computed(() => {
  const lookup = new Map(
    [...props.candidateEvents, ...(Array.isArray(draft.relatedEvents) ? draft.relatedEvents : [])]
      .filter(Boolean)
      .map((event) => [Number(event.id), event])
  );
  return draft.relatedEventIds.map((id) => lookup.get(Number(id))).filter(Boolean);
});

// Seamless edit: candidates stay hidden until the user opts in and actually
// searches, so entering edit mode never dumps a long list of alternatives.
const candidateRelatedEvents = computed(() => {
  const query = relatedSearchQuery.value.trim();
  if (!query) return [];
  return filterRelatedEventCandidates(props.candidateEvents, {
    currentId: draft.id,
    selectedIds: draft.relatedEventIds,
    query,
  });
});

const draftDisplayDate = computed(() => {
  const year = String(draft.dateYear || "").trim();
  const month = String(draft.dateMonth || "").trim();
  const day = String(draft.dateDay || "").trim();
  if (!year || !month || !day) return "未设置日期";
  const y = Number(year);
  const m = Number(month);
  const d = Number(day);
  // Mid-typing non-numeric input: keep the raw text rather than render "NaN年".
  if (!Number.isFinite(y) || !Number.isFinite(m) || !Number.isFinite(d)) {
    return `${year}年${month}月${day}日`;
  }
  // Reuse the read-mode formatter so the edit trigger matches read exactly
  // (year-only collapses to "1840年", BC → "公元前N年"); the popover still
  // exposes the underlying Y/M/D for editing.
  return formatEventDisplayDate({ dateParts: { year: y, month: m, day: d } });
});

// Editor-first detail pane: tag / attachment / related sections only render when
// they hold content (or, in edit mode, once their toolbar add-button is used).
const hasAttachments = computed(
  () => (inEditMode.value ? draft.attachments : readableGroups.value.attachments).length > 0
);
const hasRelated = computed(
  () => (inEditMode.value ? selectedRelatedEvents.value : readableGroups.value.relatedEvents).length > 0
);
// 属性「有就显示，没有就不显示」：阅读态只渲染有值属性，全空则整区隐藏；
// 编辑态显示有值 + 用户经「+属性」展开的空属性，底部列出其余未填项供按需添加。
function columnHasReadValue(column) {
  // Mirror columnHasDraftValue's emptiness test (trim, not truthiness) so a
  // whitespace-only value can't show in read yet hide in edit (a 1-row shift).
  if (isOptionColumn(column)) return chipsFor(column).length > 0;
  return String(props.event?.extra?.[column.key] ?? "").trim() !== "";
}
function columnHasDraftValue(column) {
  const value = draft.extra?.[column.key];
  if (column.type === "multiselect") return Array.isArray(value) && value.length > 0;
  return value !== undefined && value !== null && String(value).trim() !== "";
}
const readingProperties = computed(() => topicColumns.value.filter(columnHasReadValue));
const editingProperties = computed(() =>
  topicColumns.value.filter((column) => columnHasDraftValue(column) || revealedKeys.value.has(column.key))
);
const addableProperties = computed(() =>
  topicColumns.value.filter((column) => !columnHasDraftValue(column) && !revealedKeys.value.has(column.key))
);
const displayedProperties = computed(() => (inEditMode.value ? editingProperties.value : readingProperties.value));
function revealProperty(key) {
  const next = new Set(revealedKeys.value);
  next.add(key);
  revealedKeys.value = next;
}
// 属性区恒显（日期/分组每条笔记必有）；类型/标签/自定义为空则不渲染该行。
const showAttachmentSection = computed(() => hasAttachments.value);
const showRelatedSection = computed(() => hasRelated.value || (inEditMode.value && showRelatedSearch.value));

function revealRelatedEditor() {
  showRelatedSearch.value = true;
  nextTick(() => relatedSearchInputRef.value?.focus());
}

// Live edit preview pushed up so the center-column row reflects the draft in
// real time. Null when not editing, which also clears the overlay on the page.
const livePreview = computed(() => {
  if (!inEditMode.value || !draft.id) return null;
  return {
    id: draft.id,
    headline: draft.headline,
    dateYear: draft.dateYear,
    dateMonth: draft.dateMonth,
    dateDay: draft.dateDay,
    era: draft.era,
  };
});

function toggleDateEditor() {
  dateEditorOpen.value = !dateEditorOpen.value;
  if (dateEditorOpen.value) eraEditorOpen.value = false;
}

function toggleEraEditor() {
  eraEditorOpen.value = !eraEditorOpen.value;
  if (eraEditorOpen.value) dateEditorOpen.value = false;
}

function closeMetaEditors() {
  dateEditorOpen.value = false;
  eraEditorOpen.value = false;
}

function toggleKebab() {
  kebabOpen.value = !kebabOpen.value;
  if (kebabOpen.value) closeMetaEditors();
  else trashArmed.value = false;
}

function closeKebab() {
  kebabOpen.value = false;
  trashArmed.value = false;
}

function toggleAddProp() {
  addPropOpen.value = !addPropOpen.value;
}

function closeAddProp() {
  addPropOpen.value = false;
}

// 回收站二段确认：普通笔记点一下 armed（原地转红「移入回收站」），再点执行移入；
// 已在回收站的笔记仍走父级弹层（恢复 / 永久删除两个操作）。
function onTrashClick() {
  if (isDeleted.value) {
    emit("open-menu", props.event || draft);
    closeKebab();
    return;
  }
  if (!trashArmed.value) {
    trashArmed.value = true;
    return;
  }
  emit("move-to-trash", props.event || draft);
  closeKebab();
}

function handleDocumentPointer(event) {
  const target = event.target instanceof Element ? event.target : null;
  if (kebabOpen.value && !target?.closest(".kebab-wrap")) {
    kebabOpen.value = false;
    trashArmed.value = false;
  }
  if (addPropOpen.value && !target?.closest(".detail-prop-add")) {
    addPropOpen.value = false;
  }
  if (!dateEditorOpen.value && !eraEditorOpen.value) return;
  if (target?.closest(".meta-pop-wrap")) return;
  closeMetaEditors();
}

function openAttachment(attachment) {
  modalAttachment.value = attachment;
}

function closeAttachmentModal() {
  modalAttachment.value = null;
}

function handleBodyClick(event) {
  if (event.target instanceof HTMLImageElement) {
    openAttachment({
      name: event.target.alt || "图片",
      imageUrl: event.target.getAttribute("src"),
      url: event.target.getAttribute("src"),
      mimeType: "image/*",
    });
  }
}

// Release the body-height placeholder once the CM6 editor is live and holding its
// own height (paired with the flush:'pre' capture below) — see read→edit no-flash.
function onEditorReady() {
  bodyMinHeight.value = 0;
}

function snapshotDraft() {
  return JSON.stringify({
    id: draft.id,
    dateYear: String(draft.dateYear || ""),
    dateMonth: String(draft.dateMonth || ""),
    dateDay: String(draft.dateDay || ""),
    headline: draft.headline || "",
    era: draft.era || "",
    bodyMarkdown: draft.bodyMarkdown || "",
    image: draft.image || "",
    attachments: draft.attachments,
    relatedEventIds: draft.relatedEventIds,
    favorite: Boolean(draft.favorite),
    deletedAt: draft.deletedAt || null,
    extra: draft.extra,
  });
}

const isDirty = computed(() => inEditMode.value && snapshotDraft() !== initialSnapshot.value);

function applyDraft(sourceEvent) {
  const next = buildEditorDraft(sourceEvent, topicColumns.value);
  draft.id = next.id;
  draft.dateYear = next.dateYear;
  draft.dateMonth = next.dateMonth;
  draft.dateDay = next.dateDay;
  draft.headline = next.headline;
  draft.era = next.era || props.topicTitle || "未分期";
  draft.bodyMarkdown = next.bodyMarkdown;
  draft.image = next.image;
  draft.imageUrl = next.imageUrl;
  draft.attachments = next.attachments;
  draft.relatedEventIds = next.relatedEventIds;
  draft.relatedEvents = next.relatedEvents;
  draft.favorite = next.favorite;
  draft.deletedAt = next.deletedAt;
  draft.items = next.items;
  draft.extra = next.extra;
  relatedSearchQuery.value = "";
  showRelatedSearch.value = false;
  revealedKeys.value = new Set();
  closeMetaEditors();
  addPropOpen.value = false;
  if (!sourceEvent) {
    createSessionSeq.value += 1;
  }
  editorResetSeq.value += 1;
  initialSnapshot.value = snapshotDraft();
}

async function cleanupTransientUploads() {
  const staleUploads = [...new Set(sessionUploads.value)].filter(
    (filename) =>
      filename &&
      filename !== draft.image &&
      !draft.attachments.some((attachment) => attachment.filename === filename)
  );
  sessionUploads.value = [];
  pendingDeleteImages.value = [];
  if (!staleUploads.length) return;
  await Promise.allSettled(staleUploads.map((filename) => api.deleteImage(filename)));
}

function queueDeleteFile(filename) {
  if (!filename || pendingDeleteImages.value.includes(filename)) return;
  pendingDeleteImages.value.push(filename);
}

function buildAttachmentFromUpload(result, file) {
  return {
    id: result.id ?? null,
    name: result.originalName || file.name,
    filename: result.filename,
    thumbFilename: result.thumbFilename || null,
    originalFilename: result.originalFilename || null,
    mimeType: result.mimeType || file.type || null,
    width: result.width ?? null,
    height: result.height ?? null,
    bytes: result.bytes ?? null,
    url: result.url || `/images/${result.filename}`,
    thumbUrl: result.thumbUrl || null,
    originalUrl: result.originalUrl || null,
    imageUrl: result.imageUrl || null,
  };
}

function appendMarkdownBlock(markdownText, notice = "已插入正文") {
  if (bodyEditorRef.value?.insertBlock) {
    draft.bodyMarkdown = bodyEditorRef.value.insertBlock(markdownText);
  } else {
    draft.bodyMarkdown = [String(draft.bodyMarkdown || "").trim(), markdownText].filter(Boolean).join("\n\n");
  }
  if (notice) pushToast(notice);
}

async function uploadFiles(files, { insertIntoBody = false } = {}) {
  const selectedFiles = (Array.isArray(files) ? files : []).filter(Boolean);
  if (!selectedFiles.length) return;

  const remainingSlots = CONTENT_LIMITS.attachmentsVisible - draft.attachments.length;
  if (remainingSlots <= 0) {
    pushToast("附件数量已达上限", "error");
    return;
  }

  uploading.value = true;
  try {
    const uploadedAttachments = [];
    for (const file of selectedFiles.slice(0, remainingSlots)) {
      const result = await api.uploadImage(file);
      sessionUploads.value.push(result.filename);
      uploadedAttachments.push(buildAttachmentFromUpload(result, file));
    }

    draft.attachments = [...draft.attachments, ...uploadedAttachments].slice(0, CONTENT_LIMITS.attachmentsVisible);

    if (insertIntoBody) {
      const block = uploadedAttachments.map(buildAttachmentMarkdown).filter(Boolean).join("\n\n");
      appendMarkdownBlock(block, "图片已插入正文");
    } else {
      pushToast("附件已上传");
    }
  } catch (error) {
    pushToast(`上传失败：${error.message}`, "error");
  } finally {
    uploading.value = false;
  }
}

function uploadDroppedImages(files) {
  const imageFiles = (Array.isArray(files) ? files : []).filter((file) =>
    String(file?.type || "").startsWith("image/")
  );
  if (!imageFiles.length) {
    pushToast("仅支持拖拽或粘贴图片", "error");
    return;
  }
  uploadFiles(imageFiles, { insertIntoBody: true });
}

async function uploadAttachment(event, options) {
  const files = Array.from(event.target.files || []);
  await uploadFiles(files, options);
  event.target.value = "";
}

function removeAttachment(index) {
  const attachment = draft.attachments[index];
  if (!attachment) return;
  queueDeleteFile(attachment.filename);
  draft.attachments.splice(index, 1);
}

function appendAttachmentMarkdown(attachment) {
  const markdownText = buildAttachmentMarkdown(attachment);
  if (!markdownText) return;
  appendMarkdownBlock(markdownText);
}

function addRelatedCandidate(eventId) {
  if (!eventId || draft.relatedEventIds.includes(eventId)) return;
  draft.relatedEventIds = [...draft.relatedEventIds, eventId];
  relatedSearchQuery.value = "";
}

function removeRelatedEvent(eventId) {
  draft.relatedEventIds = draft.relatedEventIds.filter((id) => id !== eventId);
}

function relatedAnchorPayload(item, event) {
  const rect = event?.currentTarget?.getBoundingClientRect?.();
  return {
    id: item?.id,
    anchor: rect
      ? {
          top: rect.top,
          right: rect.right,
          bottom: rect.bottom,
          left: rect.left,
          width: rect.width,
          height: rect.height,
        }
      : null,
  };
}

function previewRelatedEvent(item, event) {
  if (inEditMode.value) return;
  emit("preview-related", relatedAnchorPayload(item, event));
}

function hideRelatedPreview(item) {
  if (inEditMode.value) return;
  emit("hide-related-preview", item?.id);
}

function activateRelatedEvent(item, event) {
  if (inEditMode.value) {
    removeRelatedEvent(item.id);
    return;
  }
  emit("pin-related", relatedAnchorPayload(item, event));
}

function submit() {
  if (bodyEditorRef.value?.getMarkdown) {
    draft.bodyMarkdown = bodyEditorRef.value.getMarkdown();
  }
  const dateYear = Number.parseInt(draft.dateYear, 10);
  const dateMonth = Number.parseInt(draft.dateMonth, 10);
  const dateDay = Number.parseInt(draft.dateDay, 10);
  const headline = String(draft.headline || "").trim().slice(0, CONTENT_LIMITS.cardTitle);
  const era = String(draft.era || "").trim().slice(0, CONTENT_LIMITS.eraLabel);
  const bodyMarkdown = String(draft.bodyMarkdown || "").trim().slice(0, CONTENT_LIMITS.bodyMarkdown);
  const attachments = draft.attachments.slice(0, CONTENT_LIMITS.attachmentsVisible).map((item) => ({
    id: item.id ?? null,
    name: item.name,
    filename: item.filename,
    thumbFilename: item.thumbFilename || null,
    originalFilename: item.originalFilename || null,
    mimeType: item.mimeType || null,
    width: item.width ?? null,
    height: item.height ?? null,
    bytes: item.bytes ?? null,
  }));
  const extra = normalizeEventExtra(draft.extra, topicColumns.value);

  if (!Number.isInteger(dateYear) || !Number.isInteger(dateMonth) || !Number.isInteger(dateDay) || !headline || !era || !bodyMarkdown) {
    pushToast("请补全日期、标题、分期和正文", "error");
    return false;
  }

  emit("save", {
    id: draft.id,
    data: {
      dateYear,
      dateMonth,
      dateDay,
      headline,
      era,
      image: draft.image || null,
      bodyMarkdown,
      attachments,
      relatedEventIds: draft.relatedEventIds,
      favorite: Boolean(draft.favorite),
      deletedAt: draft.deletedAt || null,
      items: [],
      extra,
    },
    imageOps: {
      deleteImages: [...new Set(pendingDeleteImages.value)],
    },
  });
  return true;
}

function discardDraft() {
  applyDraft(props.mode === "create" ? null : props.event);
}

function markSaved() {
  if (bodyEditorRef.value?.getMarkdown) {
    draft.bodyMarkdown = bodyEditorRef.value.getMarkdown();
  }
  sessionUploads.value = [];
  pendingDeleteImages.value = [];
  initialSnapshot.value = snapshotDraft();
}

defineExpose({ discardDraft, markSaved, submit });

watch(isDirty, (value) => emit("dirty-change", value), { immediate: true });
watch(livePreview, (value) => emit("preview-change", value), { immediate: true });

// Read→edit swaps the read HTML body for the async-mounted CM6 editor. Capture the
// read body's height BEFORE the DOM swaps (flush: 'pre') and pin it as a min-height,
// so the body never collapses during the async mount gap (which flashed the rows
// below up then back). onEditorReady() releases it once the editor holds its height.
watch(
  inEditMode,
  (editing) => {
    bodyMinHeight.value = editing ? bodyWrapRef.value?.offsetHeight || 0 : 0;
  },
  { flush: "pre" }
);

watch(
  () => [props.mode, props.event?.id],
  async ([mode, eventId], previous = []) => {
    const [prevMode, prevEventId] = previous;
    const switchingEditorContext = (prevMode === "edit" || prevMode === "create") && (mode !== prevMode || eventId !== prevEventId);

    if (switchingEditorContext) {
      await cleanupTransientUploads();
    }

    if (mode === "edit" || mode === "create") {
      applyDraft(mode === "create" ? null : props.event);
      return;
    }

    modalAttachment.value = null;
  },
  { immediate: true }
);

// When the property set changes mid-edit (e.g. creating a new option does an
// optimistic topic-columns update, or a column is added/removed), only reconcile
// the draft.extra slots. Never rebuild the draft here — that would discard the
// user's unsaved body / title / field edits and the option they just picked.
watch(
  () => topicColumns.value,
  (columns) => {
    if (!inEditMode.value) return;
    for (const column of columns) {
      if (!(column.key in draft.extra)) {
        draft.extra[column.key] = column.type === "multiselect" ? [] : "";
      }
    }
  },
  { deep: true }
);

onMounted(() => {
  document.addEventListener("pointerdown", handleDocumentPointer);
  // Prefetch the editor chunk during read so the read→edit swap is gap-free.
  loadMarkdownLiveEditor();
});

onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", handleDocumentPointer);
  emit("preview-change", null);
  cleanupTransientUploads();
});
</script>

<template>
  <aside class="col detail" :class="{ 'detail-edit': inEditMode }">
    <div v-if="props.loading" class="detail-empty">
      <h3>正在加载详情</h3>
      <p>请稍候。</p>
    </div>

    <div v-else-if="props.error" class="detail-empty">
      <h3>详情加载失败</h3>
      <p>{{ props.error }}</p>
    </div>

    <div v-else-if="!props.event && props.mode === 'view'" class="detail-empty">
      <h3>选择一条事件</h3>
      <p>点击中栏行后，右栏会展开并展示详情。</p>
    </div>

    <template v-else>
      <div class="actionbar">
        <button v-if="props.mobile" type="button" class="iconbtn" title="返回列表" @click="emit('close')">
          <TimelineLucideIcon name="arrowLeft" :stroke-width="1.8" />
        </button>
        <span class="spacer"></span>
        <button
          id="detailStar"
          type="button"
          class="iconbtn"
          :class="{ on: inEditMode ? draft.favorite : props.event?.favorite }"
          :disabled="isDeleted"
          title="收藏"
          @click="inEditMode ? (draft.favorite = !draft.favorite) : emit('toggle-favorite', props.event)"
        >
          <TimelineLucideIcon name="star" :stroke-width="1.8" />
        </button>
        <button v-if="inEditMode" type="button" class="iconbtn primary" :disabled="props.saving" title="保存" @click="submit">
          <TimelineLucideIcon name="save" :stroke-width="1.8" />
        </button>
        <button
          id="modeBtn"
          type="button"
          class="iconbtn"
          :class="{ on: inEditMode }"
          :disabled="isDeleted && !inEditMode"
          :title="inEditMode ? '阅读视图' : '编辑'"
          @click="inEditMode ? emit('cancel') : emit('edit')"
        >
          <TimelineLucideIcon :name="inEditMode ? 'eye' : 'edit'" :stroke-width="1.8" />
        </button>
        <span class="divider"></span>
        <div class="kebab-wrap">
          <button type="button" class="iconbtn" :class="{ on: kebabOpen }" title="更多操作" @click.stop="toggleKebab">
            <TimelineLucideIcon name="moreVertical" :stroke-width="1.8" />
          </button>
          <div v-if="kebabOpen" class="popover detail-kebab" @click.stop>
            <template v-if="inEditMode">
              <label class="pop-item" :class="{ 'is-disabled': uploading }">
                <TimelineLucideIcon class="pop-item-ic" name="paperclip" :stroke-width="1.8" />
                <span class="lbl">添加附件</span>
                <input type="file" accept=".png,.jpg,.jpeg,.gif,.webp,.svg,.pdf,.md,.txt,.docx" hidden :disabled="uploading" @change="uploadAttachment($event); closeKebab()" />
              </label>
              <button type="button" class="pop-item" @click="revealRelatedEditor(); closeKebab()">
                <TimelineLucideIcon class="pop-item-ic" name="link" :stroke-width="1.8" />
                <span class="lbl">关联事件</span>
              </button>
            </template>
            <button type="button" class="pop-item trash-item" :class="{ danger: trashArmed }" @click.stop="onTrashClick">
              <TimelineLucideIcon class="pop-item-ic" name="trash" :stroke-width="1.8" />
              <span class="lbl">{{ !isDeleted && trashArmed ? "移入回收站" : "回收站" }}</span>
            </button>
          </div>
        </div>
        <button v-if="!props.mobile" id="closeBtn" type="button" class="iconbtn" title="关闭详情" @click="emit('close')">
          <TimelineLucideIcon name="close" :stroke-width="1.8" />
        </button>
      </div>

      <div class="detail-scroll scroll">
        <label v-if="inEditMode" class="detail-title-field inline">
          <input v-model="draft.headline" type="text" :maxlength="CONTENT_LIMITS.cardTitle" placeholder="时间点标题" />
        </label>
        <h1 v-else class="detail-title">{{ props.event?.headline || "未命名事件" }}</h1>

        <div class="pane-sec detail-meta-sec">
          <div class="pane-sec-head">
            <h3>属性</h3>
            <div v-if="inEditMode && addableProperties.length" class="detail-prop-add">
              <button type="button" class="pane-sec-add" :class="{ on: addPropOpen }" title="添加属性" @click.stop="toggleAddProp">
                <TimelineLucideIcon name="plusSign" :stroke-width="1.8" />
              </button>
              <div v-if="addPropOpen" class="popover detail-addprop-pop" @click.stop>
                <button
                  v-for="column in addableProperties"
                  :key="column.key"
                  type="button"
                  class="pop-item"
                  @click="revealProperty(column.key); closeAddProp()"
                >
                  <TimelineLucideIcon class="pop-item-ic" :name="propertyIcon(column)" :stroke-width="1.8" />
                  <span class="lbl">{{ column.label }}</span>
                </button>
              </div>
            </div>
          </div>
          <div class="detail-prop-list">
            <!-- 日期：每条笔记必有，作为元数据首行；编辑态点开沿用现有日期弹层。 -->
            <div class="detail-prop-item">
              <span class="detail-prop-label">
                <TimelineLucideIcon name="calendar" :stroke-width="1.8" />日期
              </span>
              <div class="detail-prop-value">
                <strong v-if="!inEditMode">{{ formatEventDisplayDate(props.event) }}</strong>
                <span v-else class="meta-pop-wrap">
                  <button type="button" class="detail-meta-trigger" :class="{ on: dateEditorOpen }" @click.stop="toggleDateEditor">
                    {{ draftDisplayDate }}
                  </button>
                  <div v-if="dateEditorOpen" class="popover meta-pop" @click.stop>
                    <div class="meta-pop-date">
                      <input v-model="draft.dateYear" class="meta-input" type="text" inputmode="numeric" maxlength="8" aria-label="年" />
                      <span>年</span>
                      <input v-model="draft.dateMonth" class="meta-input sm" type="text" inputmode="numeric" maxlength="2" aria-label="月" />
                      <span>月</span>
                      <input v-model="draft.dateDay" class="meta-input sm" type="text" inputmode="numeric" maxlength="2" aria-label="日" />
                      <span>日</span>
                    </div>
                  </div>
                </span>
              </div>
            </div>
            <!-- 分组：每条笔记必有（专题·时代）。 -->
            <div class="detail-prop-item">
              <span class="detail-prop-label">
                <TimelineLucideIcon name="leaf" :stroke-width="1.8" />分组
              </span>
              <div class="detail-prop-value">
                <strong v-if="!inEditMode">{{ `${props.topicTitle} · ${props.event?.era || "未分期"}` }}</strong>
                <span v-else class="meta-pop-wrap">
                  <button type="button" class="detail-meta-trigger" :class="{ on: eraEditorOpen }" @click.stop="toggleEraEditor">
                    {{ `${props.topicTitle} · ${draft.era || "未分期"}` }}
                  </button>
                  <div v-if="eraEditorOpen" class="popover meta-pop" @click.stop>
                    <input v-model="draft.era" class="meta-text-input" type="text" :maxlength="CONTENT_LIMITS.eraLabel" placeholder="分期名称" aria-label="分期" />
                  </div>
                </span>
              </div>
            </div>
            <!-- 类型 / 标签 / 自定义属性 -->
            <div
              v-for="column in displayedProperties"
              :key="column.key"
              class="detail-prop-item"
            >
              <span class="detail-prop-label">
                <TimelineLucideIcon :name="propertyIcon(column)" :stroke-width="1.8" />{{ column.label }}
              </span>
              <div class="detail-prop-value">
                <template v-if="isOptionColumn(column)">
                  <OptionPicker
                    v-if="inEditMode"
                    :column="column"
                    v-model="draft.extra[column.key]"
                    :placeholder="`选择${column.label}`"
                    @create-option="onCreateOption"
                  />
                  <div v-else class="pane-tags">
                    <span
                      v-for="chip in chipsFor(column)"
                      :key="chip.value"
                      class="ptag"
                      :style="{ '--dot': chip.color }"
                    >
                      <i></i>{{ chip.label }}
                    </span>
                  </div>
                </template>
                <template v-else-if="isCheckboxColumn(column)">
                  <label class="detail-prop-check-wrap">
                    <input
                      type="checkbox"
                      class="detail-prop-check"
                      :checked="isCheckboxChecked(inEditMode ? draft.extra[column.key] : props.event?.extra?.[column.key])"
                      :disabled="!inEditMode"
                      @change="setCheckbox(column, $event)"
                    />
                  </label>
                </template>
                <template v-else-if="isLinkColumn(column)">
                  <input
                    v-if="inEditMode"
                    v-model="draft.extra[column.key]"
                    class="detail-inline-input"
                    :type="freeInputType(column)"
                    :placeholder="column.label"
                  />
                  <a
                    v-else-if="props.event?.extra?.[column.key]"
                    class="detail-prop-link"
                    :href="propertyHref(column.type, props.event.extra[column.key])"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <TimelineLucideIcon :name="propertyIcon(column)" :stroke-width="1.8" />
                    <span>{{ props.event.extra[column.key] }}</span>
                  </a>
                </template>
                <template v-else>
                  <input
                    v-if="inEditMode"
                    v-model="draft.extra[column.key]"
                    class="detail-inline-input"
                    :type="freeInputType(column)"
                    :placeholder="column.label"
                  />
                  <strong v-else>{{ props.event?.extra?.[column.key] }}</strong>
                </template>
              </div>
            </div>
          </div>
        </div>

        <section
          ref="bodyWrapRef"
          class="body-wrap"
          :class="{ editing: inEditMode }"
          :style="bodyMinHeight ? { minHeight: `${bodyMinHeight}px` } : null"
        >
          <MarkdownLiveEditor
            v-if="inEditMode"
            ref="bodyEditorRef"
            v-model="draft.bodyMarkdown"
            :document-key="editorDocumentKey"
            @ready="onEditorReady"
            @open-image="openAttachment"
            @paste-files="uploadDroppedImages"
            @drop-files="uploadDroppedImages"
          />
          <div
            v-else
            class="body markdown-body"
            v-html="renderedBody"
            @click="handleBodyClick"
          ></div>
        </section>

        <div v-if="showAttachmentSection" class="pane-sec">
          <div class="pane-sec-head">
            <h3>附件 · {{ (inEditMode ? draft.attachments : readableGroups.attachments).length }}</h3>
            <label v-if="inEditMode" class="pane-sec-add" :class="{ 'is-disabled': uploading }" title="添加附件">
              <TimelineLucideIcon name="plusSign" :stroke-width="1.8" />
              <input type="file" accept=".png,.jpg,.jpeg,.gif,.webp,.svg,.pdf,.md,.txt,.docx" hidden :disabled="uploading" @change="uploadAttachment($event)" />
            </label>
          </div>
          <div class="row-list">
            <div
              v-for="(attachment, index) in (inEditMode ? draft.attachments : readableGroups.attachments)"
              :key="attachment.filename || attachment.url || attachment.name || index"
              class="lrow"
            >
              <span class="lrow-ic">
                <img
                  v-if="attachmentKind(attachment) === 'image' && attachment.imageUrl"
                  class="lrow-thumb"
                  :src="attachment.thumbUrl || attachment.imageUrl"
                  :alt="attachment.name"
                  loading="lazy"
                />
                <TimelineLucideIcon v-else :name="attachmentIconName(attachment)" :stroke-width="1.8" />
              </span>
              <div class="lrow-main">
                <b>{{ attachment.name || attachment.filename || "附件" }}</b>
                <span>{{ attachment.mimeType || attachmentKind(attachment) }}</span>
              </div>
              <div class="lrow-actions">
                <button type="button" class="iconbtn sm" title="查看" @click="openAttachment(attachment)">
                  <TimelineLucideIcon name="maximize" :stroke-width="1.8" />
                </button>
                <button
                  v-if="inEditMode"
                  type="button"
                  class="iconbtn sm"
                  title="插入正文"
                  @click="appendAttachmentMarkdown(attachment)"
                >
                  <TimelineLucideIcon name="link" :stroke-width="1.8" />
                </button>
                <button
                  v-if="inEditMode"
                  type="button"
                  class="iconbtn sm"
                  title="删除附件"
                  @click="removeAttachment(index)"
                >
                  <TimelineLucideIcon name="trash" :stroke-width="1.8" />
                </button>
              </div>
            </div>
          </div>
        </div>

        <div v-if="showRelatedSection" class="pane-sec">
          <div class="pane-sec-head">
            <h3>关联事件 · {{ (inEditMode ? selectedRelatedEvents : readableGroups.relatedEvents).length }}</h3>
            <button v-if="inEditMode" type="button" class="pane-sec-add" title="关联事件" @click="revealRelatedEditor">
              <TimelineLucideIcon name="plusSign" :stroke-width="1.8" />
            </button>
          </div>
          <template v-if="inEditMode && showRelatedSearch">
            <label class="detail-inline-search">
              <TimelineLucideIcon name="search" :stroke-width="1.8" />
              <input ref="relatedSearchInputRef" v-model="relatedSearchQuery" type="search" placeholder="搜索当前专题事件" />
            </label>
            <div v-if="candidateRelatedEvents.length" class="related-results">
              <button
                v-for="candidate in candidateRelatedEvents"
                :key="candidate.id"
                type="button"
                class="related-result"
                @click="addRelatedCandidate(candidate.id)"
              >
                <strong>{{ candidate.headline }}</strong>
                <span>{{ candidate.displayLabel || formatEventDate(candidate) }}</span>
              </button>
            </div>
          </template>
          <div v-if="(inEditMode ? selectedRelatedEvents : readableGroups.relatedEvents).length" class="row-list">
            <button
              v-for="item in (inEditMode ? selectedRelatedEvents : readableGroups.relatedEvents)"
              :key="item.id"
              type="button"
              class="lrow"
              @mouseenter="previewRelatedEvent(item, $event)"
              @mouseleave="hideRelatedPreview(item)"
              @focus="previewRelatedEvent(item, $event)"
              @blur="hideRelatedPreview(item)"
              @click="activateRelatedEvent(item, $event)"
            >
              <span class="lrow-ic"><TimelineLucideIcon name="calendar" :stroke-width="1.8" /></span>
              <div class="lrow-main">
                <b>{{ item.headline || item.displayLabel || "未命名事件" }}</b>
                <span>{{ item.displayLabel || formatEventDate(item) }}</span>
              </div>
              <span class="lrow-act">
                <TimelineLucideIcon :name="inEditMode ? 'trash' : 'arrowRight'" :stroke-width="1.8" />
              </span>
            </button>
          </div>
        </div>
      </div>

      <AttachmentModal :open="Boolean(modalAttachment)" :attachment="modalAttachment" @close="closeAttachmentModal" />
    </template>
  </aside>
</template>
