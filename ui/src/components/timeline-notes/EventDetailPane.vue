<script setup>
import { computed, nextTick, reactive, ref, watch } from "vue";
import { api } from "@/composables/useApi";
import { pushToast } from "@/composables/useToast";
import TimelineLucideIcon from "@/components/timeline-notes/TimelineLucideIcon.vue";
import { CONTENT_LIMITS } from "@/constants/contentLimits";
import {
  buildEditorDraft,
  formatEventDate,
  formatEventDisplayDate,
  normalizeTagValues,
} from "@/utils/timelineNotes";
import { renderMarkdownToHtml } from "@/utils/markdownPreview";

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
const relatedCandidateId = ref("");
const bodyEditorRef = ref(null);

const inEditMode = computed(() => props.mode === "edit" || props.mode === "create");
const isDeleted = computed(() => Boolean(props.event?.deletedAt || draft.deletedAt));

const panelHeading = computed(() => {
  if (props.mode === "create") return "新建时间点";
  return props.event?.headline || "事件详情";
});

const renderedBody = computed(() => renderMarkdownToHtml(props.event?.bodyMarkdown || ""));
const detailTags = computed(() => (Array.isArray(props.event?.tags) ? props.event.tags : []));
const detailAttachments = computed(() => (Array.isArray(props.event?.attachments) ? props.event.attachments : []));
const detailRelatedEvents = computed(() => (Array.isArray(props.event?.relatedEvents) ? props.event.relatedEvents : []));
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
  props.candidateEvents.filter((event) => event.id !== draft.id && !event.deletedAt).slice(0, 80)
);

const selectedRelatedEvents = computed(() =>
  candidateRelatedEvents.value.filter((event) => draft.relatedEventIds.includes(event.id))
);

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
  relatedCandidateId.value = "";
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

async function uploadAttachment(event, { insertIntoBody = false } = {}) {
  const file = event.target.files?.[0];
  if (!file) return;

  uploading.value = true;
  try {
    const result = await api.uploadImage(file);
    const attachment = {
      id: result.id ?? null,
      name: result.originalName || file.name,
      filename: result.filename,
      mimeType: result.mimeType || file.type || null,
      url: result.url || `/images/${result.filename}`,
      imageUrl: result.imageUrl || null,
    };

    sessionUploads.value.push(result.filename);
    draft.attachments = [...draft.attachments, attachment].slice(0, CONTENT_LIMITS.attachmentsVisible);

    if (insertIntoBody) {
      appendAttachmentMarkdown(attachment, false);
      pushToast("图片已插入正文");
    } else {
      pushToast("附件已上传");
    }
  } catch (error) {
    pushToast(`上传失败：${error.message}`, "error");
  } finally {
    uploading.value = false;
    event.target.value = "";
  }
}

function removeAttachment(index) {
  const attachment = draft.attachments[index];
  if (!attachment) return;
  queueDeleteFile(attachment.filename);
  draft.attachments.splice(index, 1);
}

function appendAttachmentMarkdown(attachment, notify = true) {
  if (!attachment?.url) return;
  const markdown = attachment.imageUrl ? `![${attachment.name}](${attachment.url})` : `[${attachment.name}](${attachment.url})`;
  draft.bodyMarkdown = `${draft.bodyMarkdown.trim()}\n\n${markdown}`.trim();
  if (notify) pushToast("已插入正文");
}

function insertMarkdown(prefix, suffix = "") {
  const textarea = bodyEditorRef.value;
  if (!textarea) {
    draft.bodyMarkdown = `${draft.bodyMarkdown}${prefix}${suffix}`;
    return;
  }
  const start = textarea.selectionStart ?? draft.bodyMarkdown.length;
  const end = textarea.selectionEnd ?? start;
  const selected = draft.bodyMarkdown.slice(start, end);
  draft.bodyMarkdown = `${draft.bodyMarkdown.slice(0, start)}${prefix}${selected}${suffix}${draft.bodyMarkdown.slice(end)}`;
  nextTick(() => {
    textarea.focus();
    textarea.setSelectionRange(start + prefix.length, start + prefix.length + selected.length);
  });
}

function addRelatedCandidate() {
  const eventId = Number.parseInt(relatedCandidateId.value, 10);
  if (Number.isNaN(eventId)) return;
  if (!draft.relatedEventIds.includes(eventId)) {
    draft.relatedEventIds = [...draft.relatedEventIds, eventId];
  }
  relatedCandidateId.value = "";
}

function removeRelatedEvent(eventId) {
  draft.relatedEventIds = draft.relatedEventIds.filter((id) => id !== eventId);
}

function openRelatedEvent(eventId) {
  if (!eventId) return;
  emit("open-related", eventId);
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

  sessionUploads.value = [];
  pendingDeleteImages.value = [];
  initialSnapshot.value = snapshotDraft();
  return true;
}

function discardDraft() {
  applyDraft(props.mode === "create" ? null : props.event);
}

defineExpose({ submit, discardDraft });
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

      <template v-if="!inEditMode">
        <div class="timeline-detail-head">
          <h3 class="timeline-pane-title">{{ panelHeading }}</h3>
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

        <section class="timeline-reading-body">
          <div v-if="renderedBody" class="timeline-markdown-body" v-html="renderedBody"></div>
          <p v-else class="timeline-pane-empty">暂无正文。</p>
        </section>
      </template>

      <template v-else>
        <div class="timeline-edit-head">
          <label class="timeline-title-field">
            <input
              v-model="draft.headline"
              type="text"
              :maxlength="CONTENT_LIMITS.cardTitle"
              placeholder="时间点标题"
            />
          </label>
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
          </div>
        </div>

        <section class="timeline-edit-box">
          <div class="timeline-markdown-toolbar" aria-label="Markdown 工具栏">
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
              <input type="file" accept=".png,.jpg,.jpeg,.gif,.webp,.svg,.pdf,.md,.txt,.doc,.docx" hidden :disabled="uploading" @change="uploadAttachment($event)" />
            </label>
          </div>
          <textarea
            ref="bodyEditorRef"
            v-model="draft.bodyMarkdown"
            class="timeline-markdown-editor"
            :maxlength="CONTENT_LIMITS.bodyMarkdown"
            placeholder="使用 Markdown 记录事件正文。"
          ></textarea>
        </section>
      </template>

      <section class="timeline-pane-section">
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

      <section class="timeline-pane-section">
        <div class="timeline-section-title-row">
          <h4>附件</h4>
          <span v-if="inEditMode" class="timeline-section-helper">{{ uploading ? "上传中..." : "可插入正文或挂载资料" }}</span>
        </div>
        <div v-if="(inEditMode ? draft.attachments : detailAttachments).length" class="timeline-support-list">
          <component
            :is="inEditMode ? 'div' : 'a'"
            v-for="(attachment, index) in (inEditMode ? draft.attachments : detailAttachments).slice(0, CONTENT_LIMITS.attachmentsVisible)"
            :key="attachment.filename"
            class="timeline-support-row"
            :href="!inEditMode ? attachment.url : undefined"
            target="_blank"
            rel="noopener noreferrer"
          >
            <span class="timeline-file-badge" :class="{ image: attachment.imageUrl }" aria-hidden="true"></span>
            <div class="timeline-support-main">
              <strong>{{ attachment.name }}</strong>
              <span>{{ attachment.mimeType || "文件" }}</span>
            </div>
            <div v-if="inEditMode" class="timeline-row-actions">
              <button type="button" class="timeline-text-btn" @click="appendAttachmentMarkdown(attachment)">插入正文</button>
              <button type="button" class="timeline-text-btn" @click="removeAttachment(index)">删除</button>
            </div>
            <span v-else class="timeline-support-action">打开</span>
          </component>
        </div>
        <p v-else class="timeline-pane-empty">暂无附件。</p>
      </section>

      <section class="timeline-pane-section timeline-related-section">
        <div class="timeline-section-title-row">
          <h4>相关时间点</h4>
          <span v-if="inEditMode" class="timeline-section-helper">来自当前笔记本</span>
        </div>

        <div v-if="inEditMode" class="timeline-inline-actions timeline-related-picker">
          <select v-model="relatedCandidateId" class="timeline-related-select">
            <option value="">选择一条笔记</option>
            <option v-for="candidate in candidateRelatedEvents" :key="candidate.id" :value="candidate.id">
              {{ candidate.headline }}
            </option>
          </select>
          <button type="button" class="timeline-secondary-btn" @click="addRelatedCandidate">添加</button>
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
              <strong>{{ item.headline }}</strong>
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
