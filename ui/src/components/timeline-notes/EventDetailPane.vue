<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
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
  isOptionColumn,
  normalizeEventExtra,
  normalizeTopicColumns,
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
  "open-related",
  "save",
  "toggle-favorite",
  "dirty-change",
  "preview-change",
  "create-option",
]);

const bodyEditableRef = ref(null);
const initialSnapshot = ref("");
const uploading = ref(false);
const sessionUploads = ref([]);
const pendingDeleteImages = ref([]);
const relatedSearchQuery = ref("");
const showRelatedSearch = ref(false);
const relatedSearchInputRef = ref(null);
const modalAttachment = ref(null);
const dragActive = ref(false);
const dateEditorOpen = ref(false);
const eraEditorOpen = ref(false);

const draft = reactive(buildEditorDraft(null, props.topicColumns));

const inEditMode = computed(() => props.mode === "edit" || props.mode === "create");
const isDeleted = computed(() => Boolean(props.event?.deletedAt || draft.deletedAt));
const topicColumns = computed(() => normalizeTopicColumns(props.topicColumns));
const readableGroups = computed(() => buildReadableDetailGroups(props.event));
const renderedBody = computed(() => renderMarkdownToHtml(props.event?.bodyMarkdown || ""));

// Unified property section: option-typed properties edit via OptionPicker, free
// ones via inline inputs. Every property renders in BOTH read and edit modes
// (empty values show 「—」), so toggling read <-> edit causes zero vertical shift.
function chipsFor(column) {
  return resolvePropertyChips(props.event, column);
}

function onCreateOption(payload) {
  emit("create-option", payload);
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
  return `${year}年${month}月${day}日`;
});

// Editor-first detail pane: tag / attachment / related sections only render when
// they hold content (or, in edit mode, once their toolbar add-button is used).
const hasAttachments = computed(
  () => (inEditMode.value ? draft.attachments : readableGroups.value.attachments).length > 0
);
const hasRelated = computed(
  () => (inEditMode.value ? selectedRelatedEvents.value : readableGroups.value.relatedEvents).length > 0
);
const showPropertySection = computed(() => topicColumns.value.length > 0);
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

function handleDocumentPointer(event) {
  if (!dateEditorOpen.value && !eraEditorOpen.value) return;
  if (event.target instanceof Element && event.target.closest(".meta-pop-wrap")) return;
  closeMetaEditors();
}

function inlineToMarkdown(node) {
  if (!node) return "";
  if (node.nodeType === Node.TEXT_NODE) return node.textContent || "";
  if (node.nodeType !== Node.ELEMENT_NODE) return "";

  const children = Array.from(node.childNodes).map(inlineToMarkdown).join("");
  const tag = node.nodeName.toLowerCase();
  if (tag === "strong" || tag === "b") return `**${children}**`;
  if (tag === "em" || tag === "i") return `*${children}*`;
  if (tag === "code") return `\`${node.textContent || ""}\``;
  if (tag === "a") return `[${children || node.textContent || ""}](${node.getAttribute("href") || ""})`;
  if (tag === "img") return `![${node.getAttribute("alt") || ""}](${node.getAttribute("src") || ""})`;
  if (tag === "br") return "\n";
  return children;
}

function blockToMarkdown(node) {
  if (!node) return "";
  if (node.nodeType === Node.TEXT_NODE) return node.textContent?.trim() || "";
  if (node.nodeType !== Node.ELEMENT_NODE) return "";

  const tag = node.nodeName.toLowerCase();
  if (tag === "h1" || tag === "h2" || tag === "h3") {
    const level = Number(tag[1]);
    return `${"#".repeat(level)} ${inlineToMarkdown(node).trim()}`.trim();
  }
  if (tag === "blockquote") {
    return inlineToMarkdown(node)
      .split("\n")
      .map((line) => (line.trim() ? `> ${line.trim()}` : ">"))
      .join("\n");
  }
  if (tag === "ul") {
    return Array.from(node.children)
      .map((item) => `- ${inlineToMarkdown(item).trim()}`.trim())
      .join("\n");
  }
  if (tag === "img") {
    return inlineToMarkdown(node);
  }
  if (tag === "div" && node.classList.contains("body-editable")) {
    return Array.from(node.childNodes)
      .map(blockToMarkdown)
      .filter(Boolean)
      .join("\n\n");
  }
  return inlineToMarkdown(node).trim();
}

function editableRootToMarkdown() {
  if (!bodyEditableRef.value) return draft.bodyMarkdown || "";
  return Array.from(bodyEditableRef.value.childNodes)
    .map(blockToMarkdown)
    .filter(Boolean)
    .join("\n\n")
    .trim();
}

function syncEditableBody(markdown) {
  if (!bodyEditableRef.value) return;
  const html = renderMarkdownToHtml(markdown || "");
  const nextHtml = html || "<p><br></p>";
  if (bodyEditableRef.value.innerHTML !== nextHtml) {
    bodyEditableRef.value.innerHTML = nextHtml;
  }
}

function handleBodyInput() {
  draft.bodyMarkdown = editableRootToMarkdown();
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
  closeMetaEditors();
  nextTick(() => {
    syncEditableBody(draft.bodyMarkdown);
    initialSnapshot.value = snapshotDraft();
  });
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
    mimeType: result.mimeType || file.type || null,
    url: result.url || `/images/${result.filename}`,
    imageUrl: result.imageUrl || null,
  };
}

function appendMarkdownBlock(markdownText, notice = "已插入正文") {
  draft.bodyMarkdown = [String(draft.bodyMarkdown || "").trim(), markdownText].filter(Boolean).join("\n\n");
  nextTick(() => syncEditableBody(draft.bodyMarkdown));
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

function handleEditablePaste(event) {
  const files = Array.from(event.clipboardData?.files || []);
  if (!files.length) return;
  event.preventDefault();
  uploadDroppedImages(files);
}

function handleEditableDrop(event) {
  event.preventDefault();
  dragActive.value = false;
  uploadDroppedImages(Array.from(event.dataTransfer?.files || []));
}

function handleEditableDragOver(event) {
  event.preventDefault();
  dragActive.value = true;
}

function handleEditableDragLeave(event) {
  if (!event.currentTarget.contains(event.relatedTarget)) {
    dragActive.value = false;
  }
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

function submit() {
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
    mimeType: item.mimeType || null,
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
  sessionUploads.value = [];
  pendingDeleteImages.value = [];
  initialSnapshot.value = snapshotDraft();
}

defineExpose({ discardDraft, markSaved, submit });

watch(isDirty, (value) => emit("dirty-change", value), { immediate: true });
watch(livePreview, (value) => emit("preview-change", value), { immediate: true });

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

watch(
  () => draft.bodyMarkdown,
  (value) => {
    if (inEditMode.value) {
      nextTick(() => syncEditableBody(value));
    }
  }
);

onMounted(() => {
  document.addEventListener("pointerdown", handleDocumentPointer);
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
        <template v-if="inEditMode">
          <label class="iconbtn" :class="{ 'is-disabled': uploading }" title="添加附件">
            <TimelineLucideIcon name="paperclip" :stroke-width="1.8" />
            <input type="file" accept=".png,.jpg,.jpeg,.gif,.webp,.svg,.pdf,.md,.txt,.docx" hidden :disabled="uploading" @change="uploadAttachment($event)" />
          </label>
          <button type="button" class="iconbtn" :class="{ on: showRelatedSearch }" title="关联事件" @click="revealRelatedEditor">
            <TimelineLucideIcon name="link" :stroke-width="1.8" />
          </button>
          <span class="divider"></span>
        </template>
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
        <button type="button" class="iconbtn" title="回收站操作" @click="emit('open-menu', props.event || draft)">
          <TimelineLucideIcon name="trash" :stroke-width="1.8" />
        </button>
        <span class="divider"></span>
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
        <button v-if="!props.mobile" id="closeBtn" type="button" class="iconbtn" title="关闭详情" @click="emit('close')">
          <TimelineLucideIcon name="close" :stroke-width="1.8" />
        </button>
      </div>

      <div class="detail-scroll scroll">
        <label v-if="inEditMode" class="detail-title-field inline">
          <input v-model="draft.headline" type="text" :maxlength="CONTENT_LIMITS.cardTitle" placeholder="时间点标题" />
        </label>
        <h1 v-else class="detail-title">{{ props.event?.headline || "未命名事件" }}</h1>

        <div class="meta-row">
          <span v-if="!inEditMode" class="meta">
            <TimelineLucideIcon name="calendar" :stroke-width="1.8" />
            <span>{{ formatEventDisplayDate(props.event) }}</span>
          </span>
          <span v-else class="meta-pop-wrap">
            <button type="button" class="meta meta-trigger" :class="{ on: dateEditorOpen }" @click.stop="toggleDateEditor">
              <TimelineLucideIcon name="calendar" :stroke-width="1.8" />
              <span>{{ draftDisplayDate }}</span>
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

          <span v-if="!inEditMode" class="meta meta-group" title="所属分组">
            <TimelineLucideIcon name="leaf" :stroke-width="1.8" />
            <span>{{ `${props.topicTitle} · ${props.event?.era || "未分期"}` }}</span>
          </span>
          <span v-else class="meta-pop-wrap">
            <button type="button" class="meta meta-trigger" :class="{ on: eraEditorOpen }" @click.stop="toggleEraEditor">
              <TimelineLucideIcon name="leaf" :stroke-width="1.8" />
              <span>{{ `${props.topicTitle} · ${draft.era || "未分期"}` }}</span>
            </button>
            <div v-if="eraEditorOpen" class="popover meta-pop" @click.stop>
              <input v-model="draft.era" class="meta-text-input" type="text" :maxlength="CONTENT_LIMITS.eraLabel" placeholder="分期名称" aria-label="分期" />
            </div>
          </span>
        </div>

        <section class="body-wrap" :class="{ editing: inEditMode, dragging: dragActive }">
          <div
            v-if="inEditMode"
            ref="bodyEditableRef"
            class="body markdown-body body-editable"
            contenteditable="true"
            spellcheck="false"
            @click="handleBodyClick"
            @input="handleBodyInput"
            @paste="handleEditablePaste"
            @drop="handleEditableDrop"
            @dragover="handleEditableDragOver"
            @dragleave="handleEditableDragLeave"
          ></div>
          <div
            v-else
            class="body markdown-body"
            v-html="renderedBody"
            @click="handleBodyClick"
          ></div>
        </section>

        <div v-if="showPropertySection" class="pane-sec">
          <div class="pane-sec-head">
            <h3>属性</h3>
          </div>
          <div class="detail-prop-list">
            <div
              v-for="column in topicColumns"
              :key="column.key"
              class="detail-prop-item"
            >
              <span class="detail-prop-label">{{ column.label }}</span>
              <div class="detail-prop-value">
                <template v-if="isOptionColumn(column)">
                  <OptionPicker
                    v-if="inEditMode"
                    :column="column"
                    v-model="draft.extra[column.key]"
                    :placeholder="`选择${column.label}`"
                    @create-option="onCreateOption"
                  />
                  <div v-else-if="chipsFor(column).length" class="pane-tags">
                    <span
                      v-for="chip in chipsFor(column)"
                      :key="chip.value"
                      class="ptag"
                      :style="{ '--dot': chip.color }"
                    >
                      <i></i>{{ chip.label }}
                    </span>
                  </div>
                  <strong v-else>—</strong>
                </template>
                <template v-else>
                  <input
                    v-if="inEditMode"
                    v-model="draft.extra[column.key]"
                    class="detail-inline-input"
                    :type="column.type === 'number' ? 'number' : column.type === 'date' ? 'date' : 'text'"
                    :placeholder="column.label"
                  />
                  <strong v-else>{{ props.event?.extra?.[column.key] || "—" }}</strong>
                </template>
              </div>
            </div>
          </div>
        </div>

        <div v-if="showAttachmentSection" class="pane-sec">
          <div class="pane-sec-head">
            <h3>附件 · {{ (inEditMode ? draft.attachments : readableGroups.attachments).length }}</h3>
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
                  :src="attachment.imageUrl"
                  :alt="attachment.name"
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
              @click="inEditMode ? removeRelatedEvent(item.id) : emit('open-related', item.id)"
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
