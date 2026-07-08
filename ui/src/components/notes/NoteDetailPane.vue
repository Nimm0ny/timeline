<script setup>
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { api } from "@/composables/useApi";
import { pushToast } from "@/composables/useToast";
import { CONTENT_LIMITS } from "@/constants/contentLimits";
import AttachmentModal from "@/components/notes/AttachmentModal.vue";
import BacklinkPanel from "@/components/notes/BacklinkPanel.vue";
import OptionPicker from "@/components/notes/OptionPicker.vue";
import LucideIcon from "@/components/notes/LucideIcon.vue";
import {
  buildEditorDraft,
  buildReadableDetailGroups,
  classifyNoteDateInput,
  formatNoteDisplayDate,
  isCheckboxChecked,
  isCheckboxColumn,
  isLinkColumn,
  isOptionColumn,
  normalizeNoteExtra,
  normalizeTopicColumns,
  propertyHref,
  propertyTypeIcon,
  resolvePropertyChips,
} from "@/utils/timelineNotes";
import { renderCachedMarkdownToHtml } from "@/utils/markdownPreview";
import {
  attachmentIconName,
  attachmentKind,
  buildAttachmentMarkdown,
} from "@/utils/editorMarkdown";

const props = defineProps({
  event: {
    type: Object,
    default: null,
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
  // "edge" | "center" — which grid track this pane occupies (desktop layout swap,
  // docs/layout-swap-design.md §7). Drives the kebab quick-toggle label only.
  detailPosition: {
    type: String,
    default: "edge",
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
  "update-detail-position",
  "pane-drag-start",
]);

// Pane-swap drag entry point (mirror of NoteFeed): only the actionbar's own
// empty area or its flex spacer starts a drag, so the action buttons are never
// hijacked (pane-swap-drag-design.md §4). NotesPage owns the state machine.
function onActionbarPointerDown(event) {
  const target = event.target;
  if (target !== event.currentTarget && !target.classList?.contains("spacer")) return;
  if (event.button !== 0 || event.pointerType !== "mouse") return;
  event.preventDefault();
  emit("pane-drag-start", {
    pane: "detail",
    x: event.clientX,
    y: event.clientY,
    pointerType: event.pointerType,
    button: event.button,
  });
}

// Keep the CM6 editor in its own lazy chunk, but expose the loader so we can warm
// it while the user is still reading (see onMounted) — otherwise entering edit
// mounts it a frame late, collapsing the body and flashing the rows below.
const loadMarkdownLiveEditor = () => import("@/components/notes/MarkdownLiveEditor.vue");
const MarkdownLiveEditor = defineAsyncComponent(loadMarkdownLiveEditor);
const DETAIL_META_HEIGHT_KEY = "chronicle-detail-meta-height";
const DETAIL_META_MIN = 120;
const DETAIL_META_MAX = 360;
const DETAIL_META_DEFAULT = 176;

const bodyEditorRef = ref(null);
const bodyWrapRef = ref(null);
const bodyMinHeight = ref(0);
const initialSnapshot = ref("");
const uploading = ref(false);
const sessionUploads = ref([]);
const pendingDeleteImages = ref([]);
const modalAttachment = ref(null);
const dateEditorOpen = ref(false);
const eraEditorOpen = ref(false);
const kebabOpen = ref(false);
const addPropOpen = ref(false);
const trashArmed = ref(false);
const revealedKeys = ref(new Set());
const editorResetSeq = ref(0);
const createSessionSeq = ref(0);
const metaSectionHeight = ref(readMetaSectionHeight());
const metaResizeActive = ref(false);

let metaResizeStartY = 0;
let metaResizeStartHeight = metaSectionHeight.value;
let editorWarmed = false;

const draft = reactive(buildEditorDraft(null, props.topicColumns));

const inEditMode = computed(() => props.mode === "edit" || props.mode === "create");
const isDeleted = computed(() => Boolean(props.event?.deletedAt || draft.deletedAt));
const topicColumns = computed(() => normalizeTopicColumns(props.topicColumns));
const readableGroups = computed(() => buildReadableDetailGroups(props.event));
const renderedBody = computed(() =>
  renderCachedMarkdownToHtml({
    eventId: props.event?.id,
    updatedAt: props.event?.updatedAt,
    bodyMarkdown: props.event?.bodyMarkdown || "",
  })
);
const editorDocumentKey = computed(() => {
  if (draft.id) return `event:${draft.id}:${editorResetSeq.value}`;
  return `create:${createSessionSeq.value}:${editorResetSeq.value}`;
});
const metaListStyle = computed(() => ({ maxHeight: `${metaSectionHeight.value}px` }));

function clampMetaHeight(value) {
  return Math.min(DETAIL_META_MAX, Math.max(DETAIL_META_MIN, Math.round(value || DETAIL_META_DEFAULT)));
}

function readMetaSectionHeight() {
  if (typeof window === "undefined") return DETAIL_META_DEFAULT;
  const raw = window.localStorage.getItem(DETAIL_META_HEIGHT_KEY);
  return clampMetaHeight(Number.parseInt(raw || String(DETAIL_META_DEFAULT), 10));
}

function persistMetaSectionHeight() {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(DETAIL_META_HEIGHT_KEY, String(metaSectionHeight.value));
}

function stopMetaResize() {
  if (!metaResizeActive.value || typeof window === "undefined") return;
  metaResizeActive.value = false;
  window.removeEventListener("pointermove", onMetaResizeMove);
  window.removeEventListener("pointerup", stopMetaResize);
  persistMetaSectionHeight();
}

function onMetaResizeMove(event) {
  metaSectionHeight.value = clampMetaHeight(metaResizeStartHeight + (event.clientY - metaResizeStartY));
}

function startMetaResize(event) {
  if (typeof window === "undefined" || event.button !== 0) return;
  event.preventDefault();
  metaResizeActive.value = true;
  metaResizeStartY = event.clientY;
  metaResizeStartHeight = metaSectionHeight.value;
  window.addEventListener("pointermove", onMetaResizeMove);
  window.addEventListener("pointerup", stopMetaResize);
}

function resetMetaResize() {
  metaSectionHeight.value = DETAIL_META_DEFAULT;
  persistMetaSectionHeight();
}

function warmEditorNow() {
  if (editorWarmed) return;
  editorWarmed = true;
  loadMarkdownLiveEditor();
}

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
  return formatNoteDisplayDate({ dateParts: { year: y, month: m, day: d } });
});

// Editor-first detail pane: tag / attachment / related sections only render when
// they hold content (or, in edit mode, once their toolbar add-button is used).
const hasAttachments = computed(
  () => (inEditMode.value ? draft.attachments : readableGroups.value.attachments).length > 0
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
  const wikilink = wikilinkFromEvent(event);
  if (wikilink) {
    event.preventDefault();
    emit("pin-related", wikilink);
    return;
  }
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

function applyDraft(sourceNote) {
  const next = buildEditorDraft(sourceNote, topicColumns.value);
  draft.id = next.id;
  draft.dateYear = next.dateYear;
  draft.dateMonth = next.dateMonth;
  draft.dateDay = next.dateDay;
  draft.headline = next.headline;
  draft.era = next.era || props.topicTitle || "未分组";
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
  revealedKeys.value = new Set();
  closeMetaEditors();
  addPropOpen.value = false;
  if (!sourceNote) {
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

// W4 反向链接：BacklinkPanel 只上报 sourceId/topicId/anchor，这里把它翻译成与
// 「关联事件」完全相同的 emit，复用页面既有的预览弹层与跨笔记本打开路径，
// 不新增导航通道（open -> pin-related -> 页面 openRelatedPreview / 完整打开）。
function onBacklinkPreview(payload) {
  emit("preview-related", { id: payload.sourceId, anchor: payload.anchor });
}

function onBacklinkHidePreview(sourceId) {
  emit("hide-related-preview", sourceId);
}

function onBacklinkOpen(payload) {
  emit("pin-related", { id: payload.sourceId, anchor: payload.anchor });
}

// W4 维基链接：编辑态 CM widget 与阅读态 <a data-note-id> 都上报 {id, anchor}，翻译成与
// 「关联事件」/backlink 完全相同的 emit，复用页面既有预览弹层 + 跨笔记本打开路径，不新增导航通道。
// 点击 → pin-related（钉住预览，可再「打开完整」）；悬浮 → preview-related；移出 → hide。
function searchNotesForWikilink(query, params = {}) {
  return api.search(query, params);
}

function onWikilinkOpen(payload) {
  emit("pin-related", { id: payload.id, anchor: payload.anchor });
}

function onWikilinkPreview(payload) {
  emit("preview-related", { id: payload.id, anchor: payload.anchor });
}

function onWikilinkHidePreview(id) {
  emit("hide-related-preview", id);
}

// 阅读态 body 用 v-html 渲染，[[..]] 是 <a class="timeline-wikilink" data-note-id>。用事件委托
// 在容器上捕获点击/悬浮/键盘，翻成与编辑态 widget 同一套 emit（同一预览/打开路径）。
function wikilinkPayloadFromAnchor(anchor) {
  if (!anchor) return null;
  const id = Number(anchor.getAttribute("data-note-id"));
  if (!id) return null;
  const rect = anchor.getBoundingClientRect();
  return {
    id,
    anchor: { top: rect.top, right: rect.right, bottom: rect.bottom, left: rect.left, width: rect.width, height: rect.height },
  };
}

function wikilinkFromEvent(domEvent) {
  return wikilinkPayloadFromAnchor(domEvent.target?.closest?.("a.timeline-wikilink[data-note-id]"));
}

function onReadBodyOver(domEvent) {
  if (inEditMode.value) return;
  const anchor = domEvent.target?.closest?.("a.timeline-wikilink[data-note-id]");
  if (!anchor) return;
  // 别名含行内 md（如 [[42|**x**]]→<a><strong>x</strong></a>）时，指针在锚点内部子元素间移动会
  // 连发 mouseout/mouseover；relatedTarget 仍在同一锚内就跳过，避免预览闪烁重建。
  if (anchor.contains(domEvent.relatedTarget)) return;
  const payload = wikilinkPayloadFromAnchor(anchor);
  if (payload) emit("preview-related", payload);
}

function onReadBodyOut(domEvent) {
  if (inEditMode.value) return;
  const anchor = domEvent.target?.closest?.("a.timeline-wikilink[data-note-id]");
  if (!anchor) return;
  if (anchor.contains(domEvent.relatedTarget)) return; // 只有真正离开锚点才收预览
  emit("hide-related-preview", Number(anchor.getAttribute("data-note-id")));
}

// role=link + tabindex=0 让键盘用户能 Tab 到维基链接；无 href 的锚点 Enter/Space 不会自动触发
// click，故显式转发到与点击相同的 pin-related 打开路径。
function onReadBodyKeydown(domEvent) {
  if (inEditMode.value) return;
  if (domEvent.key !== "Enter" && domEvent.key !== " ") return;
  const payload = wikilinkFromEvent(domEvent);
  if (!payload) return;
  domEvent.preventDefault();
  emit("pin-related", payload);
}

function submit() {
  if (bodyEditorRef.value?.getMarkdown) {
    draft.bodyMarkdown = bodyEditorRef.value.getMarkdown();
  }
  const { status: dateStatus, dateFields } = classifyNoteDateInput(
    draft.dateYear,
    draft.dateMonth,
    draft.dateDay
  );
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
  const extra = normalizeNoteExtra(draft.extra, topicColumns.value);

  // De-temporalized authoring: a note needs a title + body, but the date is optional.
  // All three date fields blank → an undated note; a partial date is rejected; era is a
  // timeline bucket, so it's required only once the note is actually dated.
  if (!headline || !bodyMarkdown) {
    pushToast("请补全标题和正文", "error");
    return false;
  }
  if (dateStatus === "partial") {
    pushToast("日期请填完整的年月日，或整体留空表示无日期", "error");
    return false;
  }
  if (dateStatus === "dated" && !era) {
    pushToast("有日期的笔记需要选择分组", "error");
    return false;
  }

  emit("save", {
    id: draft.id,
    data: {
      ...dateFields,
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
      warmEditorNow();
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
});

onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", handleDocumentPointer);
  emit("preview-change", null);
  stopMetaResize();
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
      <div class="actionbar" @pointerdown="onActionbarPointerDown">
        <button v-if="props.mobile" type="button" class="iconbtn" title="返回列表" @click="emit('close')">
          <LucideIcon name="arrowLeft" :stroke-width="1.5" />
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
          <LucideIcon name="star" :stroke-width="1.5" />
        </button>
        <button v-if="inEditMode" type="button" class="iconbtn primary" :disabled="props.saving" title="保存" @click="submit">
          <LucideIcon name="save" :stroke-width="1.5" />
        </button>
        <button
          id="modeBtn"
          type="button"
          class="iconbtn"
          :class="{ on: inEditMode }"
          :disabled="isDeleted && !inEditMode"
          :title="inEditMode ? '阅读视图' : '编辑'"
          @mouseenter="warmEditorNow"
          @focus="warmEditorNow"
          @click="inEditMode ? emit('cancel') : emit('edit')"
        >
          <LucideIcon :name="inEditMode ? 'eye' : 'edit'" :stroke-width="1.5" />
        </button>
        <span class="divider"></span>
        <div class="kebab-wrap">
          <button type="button" class="iconbtn" :class="{ on: kebabOpen }" title="更多操作" @click.stop="toggleKebab">
            <LucideIcon name="moreVertical" :stroke-width="1.5" />
          </button>
          <div v-if="kebabOpen" class="popover detail-kebab" @click.stop>
            <template v-if="inEditMode">
              <label class="pop-item" :class="{ 'is-disabled': uploading }">
                <LucideIcon class="pop-item-ic" name="paperclip" :stroke-width="1.5" />
                <span class="lbl">添加附件</span>
                <input type="file" accept=".png,.jpg,.jpeg,.gif,.webp,.svg,.pdf,.md,.txt,.docx" hidden :disabled="uploading" @change="uploadAttachment($event); closeKebab()" />
              </label>
            </template>
            <button
              v-if="!props.mobile"
              type="button"
              class="pop-item"
              @click="emit('update-detail-position', props.detailPosition === 'center' ? 'edge' : 'center'); closeKebab()"
            >
              <LucideIcon class="pop-item-ic" name="swap" :stroke-width="1.5" />
              <span class="lbl">{{ props.detailPosition === "center" ? "详情贴边显示" : "详情居中显示" }}</span>
            </button>
            <button type="button" class="pop-item trash-item" :class="{ danger: trashArmed }" @click.stop="onTrashClick">
              <LucideIcon class="pop-item-ic" name="trash" :stroke-width="1.5" />
              <span class="lbl">{{ !isDeleted && trashArmed ? "移入回收站" : "回收站" }}</span>
            </button>
          </div>
        </div>
        <button v-if="!props.mobile" id="closeBtn" type="button" class="iconbtn" title="关闭详情" @click="emit('close')">
          <LucideIcon name="close" :stroke-width="1.5" />
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
                <LucideIcon name="plusSign" :stroke-width="1.5" />
              </button>
              <div v-if="addPropOpen" class="popover detail-addprop-pop" @click.stop>
                <button
                  v-for="column in addableProperties"
                  :key="column.key"
                  type="button"
                  class="pop-item"
                  @click="revealProperty(column.key); closeAddProp()"
                >
                  <LucideIcon class="pop-item-ic" :name="propertyIcon(column)" :stroke-width="1.5" />
                  <span class="lbl">{{ column.label }}</span>
                </button>
              </div>
            </div>
          </div>
          <div class="detail-prop-list-wrap" :style="metaListStyle">
            <div class="detail-prop-list">
              <!-- 日期：每条笔记必有，作为元数据首行；编辑态点开沿用现有日期弹层。 -->
              <div class="detail-prop-item">
                <span class="detail-prop-label">
                  <LucideIcon name="calendar" :stroke-width="1.5" />日期
                </span>
                <div class="detail-prop-value">
                  <strong v-if="!inEditMode">{{ formatNoteDisplayDate(props.event) }}</strong>
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
                  <LucideIcon name="leaf" :stroke-width="1.5" />分组
                </span>
                <div class="detail-prop-value">
                  <strong v-if="!inEditMode">{{ `${props.topicTitle} · ${props.event?.era || "未分组"}` }}</strong>
                  <span v-else class="meta-pop-wrap">
                    <button type="button" class="detail-meta-trigger" :class="{ on: eraEditorOpen }" @click.stop="toggleEraEditor">
                      {{ `${props.topicTitle} · ${draft.era || "未分组"}` }}
                    </button>
                    <div v-if="eraEditorOpen" class="popover meta-pop" @click.stop>
                      <input v-model="draft.era" class="meta-text-input" type="text" :maxlength="CONTENT_LIMITS.eraLabel" placeholder="分组名称" aria-label="分组" />
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
                  <LucideIcon :name="propertyIcon(column)" :stroke-width="1.5" />{{ column.label }}
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
                      <LucideIcon :name="propertyIcon(column)" :stroke-width="1.5" />
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
          <button
            type="button"
            class="detail-meta-divider"
            :class="{ active: metaResizeActive }"
            title="拖动调整属性区高度，双击重置"
            @mousedown="startMetaResize"
            @dblclick="resetMetaResize"
          ></button>
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
            :link-targets="event?.linkTargets || {}"
            :search-notes="searchNotesForWikilink"
            @ready="onEditorReady"
            @open-image="openAttachment"
            @paste-files="uploadDroppedImages"
            @drop-files="uploadDroppedImages"
            @open-wikilink="onWikilinkOpen"
            @preview-wikilink="onWikilinkPreview"
            @hide-wikilink-preview="onWikilinkHidePreview"
          />
          <div
            v-else
            class="body markdown-body"
            v-html="renderedBody"
            @click="handleBodyClick"
            @mouseover="onReadBodyOver"
            @mouseout="onReadBodyOut"
            @keydown="onReadBodyKeydown"
          ></div>
        </section>

        <div v-if="showAttachmentSection" class="pane-sec">
          <div class="pane-sec-head">
            <h3>附件 · {{ (inEditMode ? draft.attachments : readableGroups.attachments).length }}</h3>
            <label v-if="inEditMode" class="pane-sec-add" :class="{ 'is-disabled': uploading }" title="添加附件">
              <LucideIcon name="plusSign" :stroke-width="1.5" />
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
                  decoding="async"
                  fetchpriority="low"
                />
                <LucideIcon v-else :name="attachmentIconName(attachment)" :stroke-width="1.5" />
              </span>
              <div class="lrow-main">
                <b>{{ attachment.name || attachment.filename || "附件" }}</b>
                <span>{{ attachment.mimeType || attachmentKind(attachment) }}</span>
              </div>
              <div class="lrow-actions">
                <button type="button" class="iconbtn sm" title="查看" @click="openAttachment(attachment)">
                  <LucideIcon name="maximize" :stroke-width="1.5" />
                </button>
                <button
                  v-if="inEditMode"
                  type="button"
                  class="iconbtn sm"
                  title="插入正文"
                  @click="appendAttachmentMarkdown(attachment)"
                >
                  <LucideIcon name="link" :stroke-width="1.5" />
                </button>
                <button
                  v-if="inEditMode"
                  type="button"
                  class="iconbtn sm"
                  title="删除附件"
                  @click="removeAttachment(index)"
                >
                  <LucideIcon name="trash" :stroke-width="1.5" />
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- 反向链接：incoming [[wikilink]] 的阅读态面板（收起默认、展开懒加载）。
             预览/打开转发到页面既有关联机制（同 pin/preview-related）。 -->
        <BacklinkPanel
          v-if="!inEditMode && props.event?.id"
          :event-id="props.event.id"
          @open="onBacklinkOpen"
          @preview="onBacklinkPreview"
          @hide-preview="onBacklinkHidePreview"
        />
      </div>

      <AttachmentModal :open="Boolean(modalAttachment)" :attachment="modalAttachment" @close="closeAttachmentModal" />
    </template>
  </aside>
</template>
