<script setup>
import { computed, nextTick, reactive, ref, watch } from "vue";
import { api } from "@/composables/useApi";
import { pushToast } from "@/composables/useToast";
import TimelineLucideIcon from "@/components/timeline-notes/TimelineLucideIcon.vue";
import { CONTENT_LIMITS } from "@/constants/contentLimits";
import {
  buildReadableDetailGroups,
  buildEditorDraft,
  formatEventDate,
  formatEventDisplayDate,
  normalizeTagValues,
} from "@/utils/timelineNotes";
import { renderMarkdownToHtml } from "@/utils/markdownPreview";
import {
  attachmentIconName,
  attachmentKind,
  buildAttachmentMarkdown,
  buildBlockInsertion,
  filterRelatedEventCandidates,
  wrapMarkdownAtRange,
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
});

const emit = defineEmits([
  "cancel",
  "create",
  "edit",
  "save",
  "open-related",
  "toggle-favorite",
  "open-menu",
  "dirty-change",
]);

const draft = reactive(buildEditorDraft(null));
const initialSnapshot = ref("");
const uploading = ref(false);
const sessionUploads = ref([]);
const pendingDeleteImages = ref([]);
const relatedSearchQuery = ref("");
const bodyDragActive = ref(false);
const bodyEditorRef = ref(null);

const inEditMode = computed(() => props.mode === "edit" || props.mode === "create");
const isDeleted = computed(() => Boolean(props.event?.deletedAt || draft.deletedAt));

const panelHeading = computed(() => {
  if (props.mode === "create") return "新建时间点";
  return props.event?.headline || "事件详情";
});

const activeBodyMarkdown = computed(() => (inEditMode.value ? draft.bodyMarkdown : props.event?.bodyMarkdown || ""));
const renderedBody = computed(() => renderMarkdownToHtml(activeBodyMarkdown.value));
const readableDetailGroups = computed(() => buildReadableDetailGroups(props.event));
const detailTags = computed(() => readableDetailGroups.value.tags);
const detailAttachments = computed(() => readableDetailGroups.value.attachments);
const detailRelatedEvents = computed(() => readableDetailGroups.value.relatedEvents);
const metaDateLabel = computed(() => {
  if ((props.mode === "edit" || props.mode === "view") && props.event?.dateRangeLabel) {
    return props.event.dateRangeLabel;
  }
  if (inEditMode.value) {
    const year = String(draft.dateYear || "").trim();
    const month = String(draft.dateMonth || "").trim();
    const day = String(draft.dateDay || "").trim();
    if (!year) return "";
    if (!month) return `${year}年`;
    if (!day) return `${year}年${month}月`;
    return `${year}年${month}月${day}日`;
  }
  return props.event?.dateRangeLabel || formatEventDisplayDate(props.event);
});
const metaTagLabel = computed(() => {
  const tags = inEditMode.value ? draft.tags : detailTags.value;
  return tags[0] || (inEditMode.value ? draft.era : props.event?.era) || props.topicTitle || "历史学习";
});

const candidateRelatedEvents = computed(() =>
  filterRelatedEventCandidates(props.candidateEvents, {
    currentId: draft.id,
    selectedIds: draft.relatedEventIds,
    query: relatedSearchQuery.value,
  })
);

const selectedRelatedEvents = computed(() => {
  const relatedLookup = new Map(
    [...props.candidateEvents, ...draft.relatedEvents].filter(Boolean).map((event) => [Number(event.id), event])
  );
  return draft.relatedEventIds.map((eventId) => relatedLookup.get(Number(eventId))).filter(Boolean);
});

const tagText = computed({
  get: () => draft.tags.join(", "),
  set: (value) => {
    draft.tags = normalizeTagValues(String(value || "").split(/[,，]/)).slice(0, CONTENT_LIMITS.tagsVisible);
  },
});

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
    tags: draft.tags,
    attachments: draft.attachments,
    relatedEventIds: draft.relatedEventIds,
    favorite: Boolean(draft.favorite),
    deletedAt: draft.deletedAt || null,
  });
}

const isDirty = computed(() => inEditMode.value && snapshotDraft() !== initialSnapshot.value);

function applyDraft(sourceEvent) {
  const next = buildEditorDraft(sourceEvent);
  draft.id = next.id;
  draft.dateYear = next.dateYear;
  draft.dateMonth = next.dateMonth;
  draft.dateDay = next.dateDay;
  draft.headline = next.headline;
  draft.era = next.era || props.topicTitle || "历史学习";
  draft.bodyMarkdown = next.bodyMarkdown;
  draft.image = next.image;
  draft.imageUrl = next.imageUrl;
  draft.tags = next.tags.length ? next.tags : [draft.era];
  draft.attachments = next.attachments;
  draft.relatedEventIds = next.relatedEventIds;
  draft.relatedEvents = next.relatedEvents;
  draft.favorite = next.favorite;
  draft.deletedAt = next.deletedAt;
  draft.items = next.items;
  relatedSearchQuery.value = "";
  nextTick(() => {
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
  if (staleUploads.length === 0) return;
  await Promise.allSettled(staleUploads.map((filename) => api.deleteImage(filename)));
}

watch(
  () => [props.mode, props.event?.id],
  async ([mode, eventId], previous = []) => {
    const [previousMode, previousEventId] = previous;
    const wasEditing = previousMode === "edit" || previousMode === "create";
    const switchingEditorContext = wasEditing && (mode !== previousMode || eventId !== previousEventId);

    if (switchingEditorContext) {
      await cleanupTransientUploads();
    }

    if (mode === "edit" || mode === "create") {
      applyDraft(mode === "create" ? null : props.event);
    }
  },
  { immediate: true }
);

watch(isDirty, (value) => emit("dirty-change", value), { immediate: true });

function queueDeleteFile(filename) {
  if (!filename || pendingDeleteImages.value.includes(filename)) return;
  pendingDeleteImages.value.push(filename);
}

function bodySelection() {
  const textarea = bodyEditorRef.value;
  const bodyLength = String(draft.bodyMarkdown || "").length;
  if (!textarea) return { start: bodyLength, end: bodyLength };
  return {
    start: textarea.selectionStart ?? bodyLength,
    end: textarea.selectionEnd ?? textarea.selectionStart ?? bodyLength,
  };
}

function applyBodyEdit(result) {
  draft.bodyMarkdown = result.text;
  nextTick(() => {
    const textarea = bodyEditorRef.value;
    if (!textarea) return;
    textarea.focus();
    textarea.setSelectionRange(result.cursorStart, result.cursorEnd);
  });
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

async function uploadAttachment(event, { insertIntoBody = false } = {}) {
  const files = Array.from(event.target.files || []);
  await uploadFiles(files, { insertIntoBody });
  event.target.value = "";
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

    if (insertIntoBody && uploadedAttachments.length) {
      insertMarkdownBlock(uploadedAttachments.map(buildAttachmentMarkdown).filter(Boolean).join("\n\n"), false);
      pushToast("图片已插入正文");
    } else {
      pushToast("附件已上传");
    }
  } catch (error) {
    pushToast(`上传失败：${error.message}`, "error");
  } finally {
    uploading.value = false;
  }
}

async function uploadDroppedImages(files) {
  const fileList = Array.from(files || []);
  const imageFiles = fileList.filter((file) => String(file.type || "").startsWith("image/"));
  if (!imageFiles.length) {
    pushToast("仅支持拖拽或粘贴图片", "error");
    return;
  }
  if (imageFiles.length !== fileList.length) {
    pushToast("已忽略非图片文件", "error");
  }
  await uploadFiles(imageFiles, { insertIntoBody: true });
}

function handleEditorPaste(event) {
  if (!inEditMode.value) return;
  const files = Array.from(event.clipboardData?.files || []);
  if (!files.length) return;
  event.preventDefault();
  uploadDroppedImages(files);
}

function handleEditorDrop(event) {
  if (!inEditMode.value) return;
  event.preventDefault();
  bodyDragActive.value = false;
  uploadDroppedImages(event.dataTransfer?.files || []);
}

function handleEditorDragOver(event) {
  if (!inEditMode.value) return;
  event.preventDefault();
  bodyDragActive.value = true;
}

function handleEditorDragLeave(event) {
  if (!event.currentTarget.contains(event.relatedTarget)) {
    bodyDragActive.value = false;
  }
}

function removeAttachment(index) {
  const attachment = draft.attachments[index];
  if (!attachment) return;
  queueDeleteFile(attachment.filename);
  draft.attachments.splice(index, 1);
}

function appendAttachmentMarkdown(attachment, notify = true) {
  const markdown = buildAttachmentMarkdown(attachment);
  if (!markdown) return;
  insertMarkdownBlock(markdown, false);
  if (notify) pushToast("已插入正文");
}

function insertMarkdown(prefix, suffix = "") {
  const { start, end } = bodySelection();
  applyBodyEdit(wrapMarkdownAtRange(draft.bodyMarkdown, start, end, prefix, suffix));
}

function insertMarkdownBlock(markdown, notify = true) {
  if (!markdown) return;
  const { start, end } = bodySelection();
  applyBodyEdit(buildBlockInsertion(draft.bodyMarkdown, start, end, markdown));
  if (notify) pushToast("已插入正文");
}

function addRelatedCandidate(eventId) {
  if (!eventId) return;
  if (!draft.relatedEventIds.includes(eventId)) {
    draft.relatedEventIds = [...draft.relatedEventIds, eventId];
  }
  relatedSearchQuery.value = "";
}

function removeRelatedEvent(eventId) {
  draft.relatedEventIds = draft.relatedEventIds.filter((id) => id !== eventId);
}

function openRelatedEvent(eventId) {
  if (!eventId) return;
  emit("open-related", eventId);
}

function openAttachment(attachment) {
  if (!attachment?.url) return;
  window.open(attachment.url, "_blank", "noopener");
}

function markSaved() {
  sessionUploads.value = [];
  pendingDeleteImages.value = [];
  initialSnapshot.value = snapshotDraft();
}

async function cancelEdit() {
  emit("cancel");
}

function submit() {
  const dateYear = Number.parseInt(draft.dateYear, 10);
  const dateMonth = Number.parseInt(draft.dateMonth, 10);
  const dateDay = Number.parseInt(draft.dateDay, 10);
  const headline = String(draft.headline || "").trim().slice(0, CONTENT_LIMITS.cardTitle);
  const era = String(draft.era || "").trim().slice(0, CONTENT_LIMITS.eraLabel);
  const bodyMarkdown = String(draft.bodyMarkdown || "").trim().slice(0, CONTENT_LIMITS.bodyMarkdown);
  const tags = draft.tags.slice(0, CONTENT_LIMITS.tagsVisible);
  const attachments = draft.attachments.slice(0, CONTENT_LIMITS.attachmentsVisible).map((item) => ({
    id: item.id ?? null,
    name: item.name,
    filename: item.filename,
    mimeType: item.mimeType || null,
  }));

  if (
    Number.isNaN(dateYear) ||
    Number.isNaN(dateMonth) ||
    Number.isNaN(dateDay) ||
    !headline ||
    !era ||
    !bodyMarkdown
  ) {
    pushToast("请补全日期、标题、年代和正文", "error");
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
      tags,
      attachments,
      relatedEventIds: draft.relatedEventIds,
      favorite: Boolean(draft.favorite),
      deletedAt: draft.deletedAt || null,
      items: [],
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

defineExpose({ submit, discardDraft, markSaved });
</script>

<template>
  <aside class="timeline-detail-panel" :class="{ 'is-edit-mode': inEditMode, 'is-read-mode': !inEditMode }">
    <div v-if="props.loading" class="timeline-detail-empty">
      <h3>正在加载详情</h3>
      <p>请稍候。</p>
    </div>

    <div v-else-if="props.error" class="timeline-detail-empty">
      <h3>详情加载失败</h3>
      <p>{{ props.error }}</p>
    </div>

    <div v-else-if="!props.event && props.mode === 'view'" class="timeline-detail-empty">
      <h3>选择一条事件</h3>
      <p>右栏会展示当前时间点的详细内容。</p>
    </div>

    <template v-else>
      <div class="timeline-detail-actionbar">
        <div class="timeline-nav-actions">
          <button type="button" class="timeline-icon-btn" aria-label="上一条">
            <TimelineLucideIcon name="arrowLeft" :stroke-width="1.8" />
          </button>
          <button type="button" class="timeline-icon-btn" aria-label="下一条">
            <TimelineLucideIcon name="arrowRight" :stroke-width="1.8" />
          </button>
        </div>
        <div class="timeline-pane-actions">
          <button
            type="button"
            class="timeline-icon-btn timeline-star-btn"
            :class="{ active: (inEditMode ? draft.favorite : props.event?.favorite) }"
            :disabled="isDeleted"
            :aria-label="(inEditMode ? draft.favorite : props.event?.favorite) ? '取消收藏' : '收藏'"
            @click="inEditMode ? (draft.favorite = !draft.favorite) : emit('toggle-favorite', props.event)"
          >
            <TimelineLucideIcon name="star" :stroke-width="1.8" />
          </button>
          <button type="button" class="timeline-icon-btn" aria-label="锁定">
            <TimelineLucideIcon name="lock" :stroke-width="1.8" />
          </button>
          <button type="button" class="timeline-icon-btn" aria-label="更多操作" @click="emit('open-menu', props.event || draft)">
            <TimelineLucideIcon name="more" :stroke-width="1.8" />
          </button>
          <button
            v-if="inEditMode"
            type="button"
            class="timeline-save-btn"
            :disabled="props.saving"
            @click="submit"
          >
            {{ props.saving ? "保存中..." : "保存" }}
          </button>
          <button
            type="button"
            class="timeline-icon-btn timeline-view-toggle"
            :aria-label="inEditMode ? '阅读视图' : '编辑'"
            :disabled="isDeleted && !inEditMode"
            @click="inEditMode ? cancelEdit() : emit('edit')"
          >
            <TimelineLucideIcon :name="inEditMode ? 'close' : 'edit'" :stroke-width="1.8" />
          </button>
        </div>
      </div>

      <div class="timeline-detail-head">
        <label v-if="inEditMode" class="timeline-title-field">
          <input
            v-model="draft.headline"
            type="text"
            :maxlength="CONTENT_LIMITS.cardTitle"
            placeholder="时间点标题"
          />
        </label>
        <h3 v-else class="timeline-pane-title">{{ panelHeading }}</h3>
        <div class="timeline-event-meta-line" aria-label="时间和标签">
          <span class="timeline-event-meta-item">
            <TimelineLucideIcon name="calendar" :stroke-width="1.7" />
            <span>{{ metaDateLabel }}</span>
          </span>
          <span class="timeline-event-meta-item timeline-event-meta-tag">
            <TimelineLucideIcon name="leaf" :stroke-width="1.55" />
            <span>{{ metaTagLabel }}</span>
            <TimelineLucideIcon class="timeline-event-meta-chevron" name="chevronDown" :stroke-width="1.8" />
          </span>
          <span v-if="props.event?.deletedAt" class="timeline-event-meta-status">已在回收站</span>
        </div>
      </div>

      <section
        class="timeline-markdown-surface"
        :class="{ 'is-editing': inEditMode, 'is-dragging': bodyDragActive }"
        @dragover="handleEditorDragOver"
        @dragleave="handleEditorDragLeave"
        @drop="handleEditorDrop"
      >
        <textarea
          v-if="inEditMode"
          ref="bodyEditorRef"
          v-model="draft.bodyMarkdown"
          class="timeline-markdown-editor"
          :maxlength="CONTENT_LIMITS.bodyMarkdown"
          placeholder="使用 Markdown 记录事件正文。"
          @paste="handleEditorPaste"
        ></textarea>
        <div v-else-if="renderedBody" class="timeline-markdown-body" v-html="renderedBody"></div>
        <p v-else class="timeline-pane-empty timeline-markdown-empty">暂无正文。</p>

        <div v-if="inEditMode" class="timeline-markdown-toolbar" aria-label="Markdown 工具栏">
          <button type="button" @click="insertMarkdown('**', '**')">B</button>
          <button type="button" @click="insertMarkdown('*', '*')"><em>I</em></button>
          <button type="button" @click="insertMarkdown('## ')">H</button>
          <button type="button" @click="insertMarkdown('- ')">•</button>
          <button type="button" @click="insertMarkdown('1. ')">1.</button>
          <button type="button" @click="insertMarkdown('`', '`')">&lt;/&gt;</button>
          <button type="button" @click="insertMarkdown('&gt; ')">“</button>
          <button type="button" @click="insertMarkdown('[', '](url)')">⌁</button>
          <label>
            <span>▧</span>
            <input type="file" accept="image/*" hidden :disabled="uploading" @change="uploadAttachment($event, { insertIntoBody: true })" />
          </label>
          <label>
            <span>＋</span>
            <input type="file" accept=".png,.jpg,.jpeg,.gif,.webp,.svg,.pdf,.md,.txt,.docx" hidden :disabled="uploading" @change="uploadAttachment($event)" />
          </label>
        </div>
      </section>

      <section v-if="inEditMode || detailTags.length" class="timeline-pane-section">
        <div class="timeline-section-title-row">
          <h4>标签</h4>
          <button v-if="inEditMode" type="button" class="timeline-mini-soft-btn" @click="draft.tags = [...draft.tags, ''].slice(0, CONTENT_LIMITS.tagsVisible)">+</button>
        </div>
        <label v-if="inEditMode" class="timeline-field compact">
          <input v-model="tagText" type="text" :maxlength="120" placeholder="历史学习, 事件" />
        </label>
        <div v-if="(inEditMode ? draft.tags : detailTags).length" class="timeline-chip-row">
          <span
            v-for="tag in (inEditMode ? draft.tags : detailTags).slice(0, CONTENT_LIMITS.tagsVisible)"
            :key="tag"
            class="timeline-chip"
          >
            {{ tag }}
          </span>
        </div>
        <p v-else class="timeline-pane-empty">暂无标签。</p>
      </section>

      <section v-if="inEditMode || detailAttachments.length" class="timeline-pane-section">
        <div class="timeline-section-title-row">
          <h4>附件</h4>
          <span v-if="inEditMode" class="timeline-section-helper">{{ uploading ? "上传中..." : "可插入正文或挂载资料" }}</span>
        </div>
        <div v-if="(inEditMode ? draft.attachments : detailAttachments).length" class="timeline-support-list timeline-attachment-list">
          <div
            v-for="(attachment, index) in (inEditMode ? draft.attachments : detailAttachments).slice(0, CONTENT_LIMITS.attachmentsVisible)"
            :key="attachment.filename || attachment.url || attachment.name || index"
            class="timeline-support-row"
          >
            <span class="timeline-file-preview" :class="`kind-${attachmentKind(attachment)}`" aria-hidden="true">
              <img v-if="attachmentKind(attachment) === 'image' && attachment.imageUrl" :src="attachment.imageUrl" :alt="attachment.name" />
              <TimelineLucideIcon v-else :name="attachmentIconName(attachment)" :stroke-width="1.7" />
            </span>
            <div class="timeline-support-main">
              <strong>{{ attachment.name || attachment.filename || "附件" }}</strong>
              <span>{{ attachment.mimeType || "文件" }}</span>
            </div>
            <div class="timeline-row-actions">
              <button type="button" class="timeline-text-btn" @click="openAttachment(attachment)">打开</button>
              <button v-if="inEditMode" type="button" class="timeline-text-btn" @click="appendAttachmentMarkdown(attachment)">插入正文</button>
              <button v-if="inEditMode" type="button" class="timeline-text-btn danger" @click="removeAttachment(index)">删除</button>
            </div>
          </div>
        </div>
        <p v-else class="timeline-pane-empty">暂无附件。</p>
      </section>

      <section v-if="inEditMode || detailRelatedEvents.length" class="timeline-pane-section timeline-related-section">
        <div class="timeline-section-title-row">
          <h4>相关时间点</h4>
          <span v-if="inEditMode" class="timeline-section-helper">来自当前笔记本</span>
        </div>

        <div v-if="inEditMode" class="timeline-related-picker">
          <label class="timeline-related-search">
            <TimelineLucideIcon name="search" :stroke-width="1.7" />
            <input v-model="relatedSearchQuery" type="search" placeholder="搜索标题、日期、标签" />
          </label>
          <div v-if="candidateRelatedEvents.length" class="timeline-related-results">
            <button
              v-for="candidate in candidateRelatedEvents"
              :key="candidate.id"
              type="button"
              class="timeline-related-result"
              @click="addRelatedCandidate(candidate.id)"
            >
              <strong>{{ candidate.headline }}</strong>
              <span>{{ candidate.displayLabel || formatEventDate(candidate) }}</span>
            </button>
          </div>
          <p v-else-if="relatedSearchQuery" class="timeline-pane-empty">没有匹配的时间点。</p>
        </div>

        <div v-if="(inEditMode ? selectedRelatedEvents : detailRelatedEvents).length" class="timeline-support-list">
          <button
            v-for="item in (inEditMode ? selectedRelatedEvents : detailRelatedEvents).slice(0, CONTENT_LIMITS.relatedNotesVisible)"
            :key="item.id"
            type="button"
            class="timeline-support-row"
            @click="inEditMode ? removeRelatedEvent(item.id) : openRelatedEvent(item.id)"
          >
            <div class="timeline-support-main">
              <strong>{{ item.headline || item.displayLabel || formatEventDate(item) || "未命名时间点" }}</strong>
              <span>{{ item.displayLabel || formatEventDate(item) }}</span>
            </div>
            <span class="timeline-support-action">{{ inEditMode ? "移除" : "查看" }}</span>
          </button>
        </div>
        <p v-else class="timeline-pane-empty">暂无相关时间点。</p>
      </section>
    </template>
  </aside>
</template>
