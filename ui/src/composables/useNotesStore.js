import { reactive } from "vue";
import { api } from "./useApi.js";
import {
  buildNotePreview,
  compareTimelineEvents,
  mergeTopicNotePage,
  mindmapPlainText,
  planTopicPageFetch,
} from "../utils/timelineNotes.js";
import { plainTextFromMarkdown } from "../utils/markdownPreview.js";

const DEFAULT_TOPIC_PAGE_SIZE = 100;
const DETAIL_CACHE_LIMIT = 40;

function datePartsFromKey(dateKey) {
  const key = Number.parseInt(dateKey, 10) || 0;
  const year = Math.trunc(key / 10000);
  const month = Math.trunc((Math.abs(key) % 10000) / 100) || 1;
  const day = Math.abs(key) % 100 || 1;
  return { year, month, day };
}

function normalizeTopic(topic = {}) {
  return {
    ...topic,
    id: Number(topic.id),
    columns: Array.isArray(topic.columns) ? topic.columns : [],
    eventCount: Number(topic.eventCount || 0),
    minDateKey: topic.minDateKey ?? null,
    maxDateKey: topic.maxDateKey ?? null,
    minDate: topic.minDate ?? null,
    maxDate: topic.maxDate ?? null,
  };
}

function normalizeIndexNote(note = {}, fallbackTopicId = null) {
  const rawDateKey = note.dateKey == null || note.dateKey === "" ? null : Number.parseInt(note.dateKey, 10);
  const dateKey = Number.isFinite(rawDateKey) ? rawDateKey : null;
  const topicId = Number(note.topicId ?? note.topic_id ?? fallbackTopicId);
  return {
    ...note,
    id: Number(note.id),
    topicId,
    dateKey,
    hasDate: note.hasDate !== false && dateKey != null,
    dateParts: note.dateParts || (dateKey != null ? datePartsFromKey(dateKey) : { year: null, month: null, day: null }),
    noteType: note.noteType || "entry",
    extra: note.extra && typeof note.extra === "object" ? note.extra : {},
    favorite: Boolean(note.favorite),
    favoriteAt: note.favoriteAt ?? null,
    deletedAt: note.deletedAt ?? null,
    preview: String(note.preview || ""),
    attachmentCount: Number(note.attachmentCount || note.attachments?.length || 0),
  };
}

function normalizeDetailNote(note = {}, fallbackTopicId = null) {
  return {
    ...note,
    id: Number(note.id),
    topicId: Number(note.topicId ?? note.topic_id ?? fallbackTopicId),
  };
}

function hasFullNoteDetail(note = {}) {
  return (
    "bodyMarkdown" in note ||
    "bodyJson" in note ||
    "attachments" in note ||
    "items" in note ||
    "relatedEvents" in note
  );
}

function detailToIndexNote(note = {}) {
  return normalizeIndexNote({
    id: note.id,
    topicId: note.topicId,
    dateKey: note.dateKey,
    isoDate: note.isoDate,
    dateParts: note.dateParts,
    displayLabel: note.displayLabel,
    headline: note.headline,
    era: note.era,
    // Keep the note kind so the feed still flags a mindmap (and routes its click to
    // the canvas) after an edit round-trips through here.
    noteType: note.noteType || "entry",
    hasDate: note.hasDate !== false && note.dateKey != null,
    // Keep the primary image so a gallery card doesn't lose its thumbnail after
    // the note is edited (this is the index note the gallery reads). The detail
    // DTO has no separate thumb for the primary image — fall back to the full URL.
    image: note.image ?? null,
    imageUrl: note.imageUrl ?? null,
    thumbUrl: note.thumbUrl ?? note.imageUrl ?? null,
    extra: note.extra,
    favorite: note.favorite,
    favoriteAt: note.favoriteAt ?? null,
    deletedAt: note.deletedAt,
    createdAt: note.createdAt,
    updatedAt: note.updatedAt,
    preview: buildNotePreview(note, 120),
    searchText: detailSearchText(note),
    attachmentCount: Array.isArray(note.attachments) ? note.attachments.length : 0,
  });
}

function flattenSearchValues(value) {
  if (value == null) return [];
  if (Array.isArray(value)) return value.flatMap((item) => flattenSearchValues(item));
  if (typeof value === "object") return Object.values(value).flatMap((item) => flattenSearchValues(item));
  return [String(value)];
}

function detailSearchText(note = {}) {
  const attachments = Array.isArray(note.attachments) ? note.attachments : [];
  const parts = [
    note.headline,
    note.displayLabel,
    note.legacyYear,
    note.era,
    mindmapPlainText(note.bodyJson),
    plainTextFromMarkdown(note.bodyMarkdown || ""),
    ...(note.items || []).map((item) => item?.text || ""),
    ...flattenSearchValues(note.extra),
    ...attachments.map((attachment) => `${attachment?.name || ""} ${attachment?.filename || ""}`),
  ];
  return parts.join(" ").replace(/\s+/g, " ").trim();
}

function minMaxNotes(notes) {
  if (!notes.length) return { min: null, max: null };
  const sorted = [...notes].sort(compareTimelineEvents);
  return { min: sorted[0], max: sorted[sorted.length - 1] };
}

export function useNotesStore() {
  const state = reactive({
    topics: [],
    notesIndex: [],
    detailCache: new Map(),
    topicPages: {},
    indexLoaded: false,
    topicsLoaded: false,
    loadedTopicIds: new Set(),
    loading: false,
  });
  const topicNoteRequests = new Map();
  // Monotonic per-topic fetch generation. A reset fetch (initial / forced page-1)
  // bumps it, so a slower superseded response — e.g. the ascending page from a
  // rapid 正序⇄倒序 toggle landing after the descending one — is dropped instead of
  // clobbering the current page. Append fetches capture the current gen, never bump.
  const topicFetchGen = new Map();
  const topicGen = (id) => topicFetchGen.get(id) || 0;
  const bumpTopicGen = (id) => {
    const next = topicGen(id) + 1;
    topicFetchGen.set(id, next);
    return next;
  };
  let protectedDetailId = null;
  let detailTouchSequence = 0;
  const detailTouchedAt = new Map();

  function markDetailUsed(id) {
    const next = Number(id);
    if (!next) return;
    detailTouchSequence += 1;
    detailTouchedAt.set(next, detailTouchSequence);
  }

  function writeDetailCache(detail) {
    const id = Number(detail?.id);
    if (!id) return;
    if (state.detailCache.has(id)) state.detailCache.delete(id);
    state.detailCache.set(id, detail);
    markDetailUsed(id);
    evictDetailCache();
  }

  function evictDetailCache() {
    while (state.detailCache.size > DETAIL_CACHE_LIMIT) {
      let oldestId = null;
      let oldestTouch = Number.POSITIVE_INFINITY;
      for (const [id] of state.detailCache) {
        if (id === protectedDetailId) continue;
        const touchedAt = detailTouchedAt.get(id) || 0;
        if (touchedAt < oldestTouch) {
          oldestTouch = touchedAt;
          oldestId = id;
        }
      }
      if (oldestId == null) break;
      state.detailCache.delete(oldestId);
      detailTouchedAt.delete(oldestId);
    }
  }

  function replaceTopics(topics) {
    state.topics.splice(0, state.topics.length, ...(topics || []).map(normalizeTopic));
  }

  function setTopics(topics) {
    replaceTopics(topics);
    state.topicsLoaded = true;
  }

  function replaceNotes(notes) {
    state.notesIndex.splice(0, state.notesIndex.length, ...(notes || []).map(normalizeIndexNote).sort(compareTimelineEvents));
  }

  function topicPageState(topicId) {
    return state.topicPages[Number(topicId)] || { loaded: false, hasMore: false, nextCursor: null };
  }

  function replaceTopicNotes(topicId, notes = [], bounds = null, { append = false, hasMore = false, nextCursor = null } = {}) {
    const id = Number(topicId);
    if (!id) return;
    const normalized = (notes || []).map((note) => normalizeIndexNote(note, id));
    const existingTopicNotes = append ? state.notesIndex.filter((note) => note.topicId === id) : [];
    const mergedTopicNotes = mergeTopicNotePage(existingTopicNotes, normalized, { append });
    const others = state.notesIndex.filter((note) => note.topicId !== id);
    state.notesIndex.splice(0, state.notesIndex.length, ...others, ...mergedTopicNotes);
    state.notesIndex.sort(compareTimelineEvents);
    for (const note of notes || []) {
      if (!hasFullNoteDetail(note)) continue;
      const detail = normalizeDetailNote(note, id);
      if (detail.id) writeDetailCache(detail);
    }
    state.loadedTopicIds.add(id);
    state.topicPages[id] = {
      loaded: true,
      hasMore: Boolean(hasMore),
      nextCursor: nextCursor ?? null,
    };
    updateTopicSummary(id, bounds);
  }

  function topicById(topicId) {
    const id = Number(topicId);
    return state.topics.find((topic) => topic.id === id) || null;
  }

  function detailById(noteId) {
    const id = Number(noteId);
    const cached = state.detailCache.get(id) || null;
    if (cached) markDetailUsed(id);
    return cached && hasFullNoteDetail(cached) ? cached : null;
  }

  function noteById(noteId) {
    const id = Number(noteId);
    return state.notesIndex.find((note) => note.id === id) || detailById(id);
  }

  function notesForTopic(topicId) {
    const id = Number(topicId);
    return state.notesIndex.filter((note) => note.topicId === id).sort(compareTimelineEvents);
  }

  function applyTopicBounds(topic, bounds) {
    topic.eventCount = Number(bounds.eventCount || 0);
    topic.minDateKey = bounds.minDateKey ?? null;
    topic.maxDateKey = bounds.maxDateKey ?? null;
    topic.minDate = bounds.minDate ?? null;
    topic.maxDate = bounds.maxDate ?? null;
    if ("hasImage" in bounds) topic.hasImage = Boolean(bounds.hasImage);
    if ("supportedZoomLevels" in bounds) topic.supportedZoomLevels = bounds.supportedZoomLevels;
  }

  function updateTopicSummary(topicId, bounds = null) {
    const id = Number(topicId);
    const topic = topicById(id);
    if (!topic) return;
    if (bounds) {
      applyTopicBounds(topic, bounds);
      return;
    }
    if (!state.loadedTopicIds.has(id)) return;
    if (topicPageState(id).hasMore) return;
    const notes = notesForTopic(id);
    const { min, max } = minMaxNotes(notes);
    topic.eventCount = notes.length;
    topic.minDateKey = min?.dateKey ?? null;
    topic.maxDateKey = max?.dateKey ?? null;
    topic.minDate = min?.isoDate ?? null;
    topic.maxDate = max?.isoDate ?? null;
  }

  function isTopicNotesLoaded(topicId) {
    return state.loadedTopicIds.has(Number(topicId));
  }

  function topicHasMore(topicId) {
    return Boolean(topicPageState(topicId).hasMore);
  }

  function topicNextCursor(topicId) {
    return topicPageState(topicId).nextCursor ?? null;
  }

  async function loadTopics({ force = false } = {}) {
    if (state.topicsLoaded && !force) return;
    state.loading = true;
    try {
      replaceTopics(await api.listTopics());
      state.topicsLoaded = true;
    } finally {
      state.loading = false;
    }
  }

  async function loadIndex({ force = false } = {}) {
    if (state.indexLoaded && !force) return;
    state.loading = true;
    try {
      const payload = await api.getIndex();
      replaceTopics(payload.topics || []);
      replaceNotes(payload.events || []);
      state.loadedTopicIds.clear();
      for (const topic of state.topics) state.loadedTopicIds.add(topic.id);
      state.topicPages = Object.fromEntries(state.topics.map((topic) => [topic.id, { loaded: true, hasMore: false, nextCursor: null }]));
      state.topicsLoaded = true;
      state.indexLoaded = true;
    } finally {
      state.loading = false;
    }
  }

  async function ensureTopicNotes(topicId, { force = false, append = false, cursor = null, limit = DEFAULT_TOPIC_PAGE_SIZE, dir = 1 } = {}) {
    const id = Number(topicId);
    if (!id) return [];
    const fetchDir = Number(dir) < 0 ? -1 : 1;
    const currentPage = topicPageState(id);
    const plan = planTopicPageFetch(
      { loaded: isTopicNotesLoaded(id), hasMore: currentPage.hasMore, nextCursor: currentPage.nextCursor },
      { append, cursor, force }
    );
    if (!plan.shouldFetch) return notesForTopic(id);
    const requestCursor = plan.requestCursor;
    // dir rides the request key so a forced re-fetch under a new direction is a
    // distinct in-flight request, never deduped against the old-direction one.
    const requestKey = `${id}:${fetchDir}:${append ? requestCursor || "append" : force ? "force" : "initial"}`;
    const existing = topicNoteRequests.get(requestKey);
    if (existing && !force) return existing;
    // Bump only when we actually issue a new request (after the dedup return above,
    // so a deduped initial load doesn't strand the in-flight one under a newer gen).
    const gen = append ? topicGen(id) : bumpTopicGen(id);
    const request = api
      .getTimelineEvents(id, { cursor: requestCursor, limit, dir: fetchDir })
      .then((payload) => {
        if (gen !== topicGen(id)) return notesForTopic(id); // superseded by a newer reset — drop
        const items = Array.isArray(payload) ? payload : payload?.items || [];
        replaceTopicNotes(id, items, Array.isArray(payload) ? null : payload?.bounds || null, {
          append,
          hasMore: Array.isArray(payload) ? false : payload?.hasMore || false,
          nextCursor: Array.isArray(payload) ? null : payload?.nextCursor || null,
        });
        return notesForTopic(id);
      })
      .finally(() => {
        topicNoteRequests.delete(requestKey);
      });
    topicNoteRequests.set(requestKey, request);
    return request;
  }

  async function ensureNoteDetail(noteId, options = {}) {
    const id = Number(noteId);
    if (!id) return null;
    const cached = detailById(id);
    if (cached) return cached;
    return upsertNote(await api.getEvent(id, options));
  }

  function setProtectedDetailId(noteId) {
    const id = Number(noteId);
    protectedDetailId = Number.isInteger(id) && id > 0 ? id : null;
    evictDetailCache();
  }

  function upsertTopic(topic) {
    const normalized = normalizeTopic(topic);
    const index = state.topics.findIndex((item) => item.id === normalized.id);
    if (index >= 0) {
      state.topics[index] = { ...state.topics[index], ...normalized };
    } else {
      state.topics.push(normalized);
      state.topics.sort((left, right) => left.id - right.id);
    }
    return topicById(normalized.id);
  }

  function removeTopic(topicId) {
    const id = Number(topicId);
    replaceTopics(state.topics.filter((topic) => topic.id !== id));
    replaceNotes(state.notesIndex.filter((note) => note.topicId !== id));
    state.loadedTopicIds.delete(id);
    delete state.topicPages[id];
    for (const noteId of [...state.detailCache.keys()]) {
      const cached = state.detailCache.get(noteId);
      if (cached?.topicId === id) {
        state.detailCache.delete(noteId);
        detailTouchedAt.delete(noteId);
      }
    }
  }

  function upsertNote(note) {
    const detail = normalizeDetailNote(note);
    const indexNote = detailToIndexNote(detail);
    const index = state.notesIndex.findIndex((item) => item.id === indexNote.id);
    if (index >= 0) {
      state.notesIndex[index] = { ...state.notesIndex[index], ...indexNote };
    } else {
      state.notesIndex.push(indexNote);
    }
    state.notesIndex.sort(compareTimelineEvents);
    writeDetailCache(detail);
    updateTopicSummary(indexNote.topicId);
    return detail;
  }

  function patchNote(noteId, patch) {
    const id = Number(noteId);
    const index = state.notesIndex.findIndex((note) => note.id === id);
    const topicId = index >= 0 ? state.notesIndex[index].topicId : detailById(id)?.topicId;
    if (index >= 0) state.notesIndex[index] = { ...state.notesIndex[index], ...patch };
    const cached = state.detailCache.get(id);
    if (cached) writeDetailCache({ ...cached, ...patch });
    updateTopicSummary(topicId);
  }

  function removeNote(noteId) {
    const id = Number(noteId);
    const existing = noteById(id);
    replaceNotes(state.notesIndex.filter((note) => note.id !== id));
    state.detailCache.delete(id);
    detailTouchedAt.delete(id);
    updateTopicSummary(existing?.topicId);
  }

  return {
    state,
    detailById,
    ensureTopicNotes,
    ensureNoteDetail,
    noteById,
    notesForTopic,
    isTopicNotesLoaded,
    loadIndex,
    loadTopics,
    patchNote,
    removeNote,
    removeTopic,
    setProtectedDetailId,
    setTopics,
    topicById,
    topicHasMore,
    topicNextCursor,
    upsertNote,
    upsertTopic,
  };
}
