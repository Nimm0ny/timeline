import { reactive } from "vue";
import { api } from "@/composables/useApi";
import { buildEventPreview, compareTimelineEvents, mindmapPlainText } from "@/utils/timelineNotes";
import { plainTextFromMarkdown } from "@/utils/markdownPreview";

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

function normalizeIndexEvent(event = {}, fallbackTopicId = null) {
  const rawDateKey = event.dateKey == null || event.dateKey === "" ? null : Number.parseInt(event.dateKey, 10);
  const dateKey = Number.isFinite(rawDateKey) ? rawDateKey : null;
  const topicId = Number(event.topicId ?? event.topic_id ?? fallbackTopicId);
  return {
    ...event,
    id: Number(event.id),
    topicId,
    dateKey,
    hasDate: event.hasDate !== false && dateKey != null,
    dateParts: event.dateParts || (dateKey != null ? datePartsFromKey(dateKey) : { year: null, month: null, day: null }),
    noteType: event.noteType || "entry",
    extra: event.extra && typeof event.extra === "object" ? event.extra : {},
    favorite: Boolean(event.favorite),
    favoriteAt: event.favoriteAt ?? null,
    deletedAt: event.deletedAt ?? null,
    preview: String(event.preview || ""),
    attachmentCount: Number(event.attachmentCount || event.attachments?.length || 0),
  };
}

function normalizeDetailEvent(event = {}, fallbackTopicId = null) {
  return {
    ...event,
    id: Number(event.id),
    topicId: Number(event.topicId ?? event.topic_id ?? fallbackTopicId),
  };
}

function detailToIndexEvent(event = {}) {
  return normalizeIndexEvent({
    id: event.id,
    topicId: event.topicId,
    dateKey: event.dateKey,
    isoDate: event.isoDate,
    dateParts: event.dateParts,
    displayLabel: event.displayLabel,
    headline: event.headline,
    era: event.era,
    // Keep the note kind so the feed still flags a mindmap (and routes its click to
    // the canvas) after an edit round-trips through here.
    noteType: event.noteType || "entry",
    hasDate: event.hasDate !== false && event.dateKey != null,
    // Keep the primary image so a gallery card doesn't lose its thumbnail after
    // the event is edited (this is the index event the gallery reads). The detail
    // DTO has no separate thumb for the primary image — fall back to the full URL.
    image: event.image ?? null,
    imageUrl: event.imageUrl ?? null,
    thumbUrl: event.thumbUrl ?? event.imageUrl ?? null,
    extra: event.extra,
    favorite: event.favorite,
    favoriteAt: event.favoriteAt ?? null,
    deletedAt: event.deletedAt,
    createdAt: event.createdAt,
    updatedAt: event.updatedAt,
    preview: buildEventPreview(event, 120),
    searchText: detailSearchText(event),
    attachmentCount: Array.isArray(event.attachments) ? event.attachments.length : 0,
  });
}

function flattenSearchValues(value) {
  if (value == null) return [];
  if (Array.isArray(value)) return value.flatMap((item) => flattenSearchValues(item));
  if (typeof value === "object") return Object.values(value).flatMap((item) => flattenSearchValues(item));
  return [String(value)];
}

function detailSearchText(event = {}) {
  const attachments = Array.isArray(event.attachments) ? event.attachments : [];
  const parts = [
    event.headline,
    event.displayLabel,
    event.legacyYear,
    event.era,
    mindmapPlainText(event.bodyJson),
    plainTextFromMarkdown(event.bodyMarkdown || ""),
    ...(event.items || []).map((item) => item?.text || ""),
    ...flattenSearchValues(event.extra),
    ...attachments.map((attachment) => `${attachment?.name || ""} ${attachment?.filename || ""}`),
  ];
  return parts.join(" ").replace(/\s+/g, " ").trim();
}

function minMaxEvents(events) {
  if (!events.length) return { min: null, max: null };
  const sorted = [...events].sort(compareTimelineEvents);
  return { min: sorted[0], max: sorted[sorted.length - 1] };
}

export function useTimelineStore() {
  const state = reactive({
    topics: [],
    eventsIndex: [],
    detailCache: new Map(),
    indexLoaded: false,
    topicsLoaded: false,
    loadedTopicIds: new Set(),
    loading: false,
  });
  const topicEventRequests = new Map();

  function replaceTopics(topics) {
    state.topics.splice(0, state.topics.length, ...(topics || []).map(normalizeTopic));
  }

  function replaceEvents(events) {
    state.eventsIndex.splice(0, state.eventsIndex.length, ...(events || []).map(normalizeIndexEvent).sort(compareTimelineEvents));
  }

  function replaceTopicEvents(topicId, events = [], bounds = null) {
    const id = Number(topicId);
    if (!id) return;
    const normalized = (events || []).map((event) => normalizeIndexEvent(event, id));
    const others = state.eventsIndex.filter((event) => event.topicId !== id);
    state.eventsIndex.splice(0, state.eventsIndex.length, ...others, ...normalized);
    state.eventsIndex.sort(compareTimelineEvents);
    for (const event of events || []) {
      const detail = normalizeDetailEvent(event, id);
      if (detail.id) state.detailCache.set(detail.id, detail);
    }
    state.loadedTopicIds.add(id);
    updateTopicSummary(id, bounds);
  }

  function topicById(topicId) {
    const id = Number(topicId);
    return state.topics.find((topic) => topic.id === id) || null;
  }

  function detailById(eventId) {
    return state.detailCache.get(Number(eventId)) || null;
  }

  function eventById(eventId) {
    const id = Number(eventId);
    return state.eventsIndex.find((event) => event.id === id) || detailById(id);
  }

  function eventsForTopic(topicId) {
    const id = Number(topicId);
    return state.eventsIndex.filter((event) => event.topicId === id).sort(compareTimelineEvents);
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
    const events = eventsForTopic(id);
    const { min, max } = minMaxEvents(events);
    topic.eventCount = events.length;
    topic.minDateKey = min?.dateKey ?? null;
    topic.maxDateKey = max?.dateKey ?? null;
    topic.minDate = min?.isoDate ?? null;
    topic.maxDate = max?.isoDate ?? null;
  }

  function isTopicEventsLoaded(topicId) {
    return state.loadedTopicIds.has(Number(topicId));
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
      replaceEvents(payload.events || []);
      state.loadedTopicIds.clear();
      for (const topic of state.topics) state.loadedTopicIds.add(topic.id);
      state.topicsLoaded = true;
      state.indexLoaded = true;
    } finally {
      state.loading = false;
    }
  }

  async function ensureTopicEvents(topicId, { force = false } = {}) {
    const id = Number(topicId);
    if (!id) return [];
    if (isTopicEventsLoaded(id) && !force) return eventsForTopic(id);
    const existing = topicEventRequests.get(id);
    if (existing && !force) return existing;
    const request = api
      .getTimelineEvents(id)
      .then((payload) => {
        const items = Array.isArray(payload) ? payload : payload?.items || [];
        replaceTopicEvents(id, items, Array.isArray(payload) ? null : payload?.bounds || null);
        return eventsForTopic(id);
      })
      .finally(() => {
        topicEventRequests.delete(id);
      });
    topicEventRequests.set(id, request);
    return request;
  }

  async function ensureEventDetail(eventId) {
    const id = Number(eventId);
    if (!id) return null;
    const cached = detailById(id);
    if (cached) return cached;
    return upsertEvent(await api.getEvent(id));
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
    replaceEvents(state.eventsIndex.filter((event) => event.topicId !== id));
    state.loadedTopicIds.delete(id);
    for (const eventId of [...state.detailCache.keys()]) {
      const cached = state.detailCache.get(eventId);
      if (cached?.topicId === id) state.detailCache.delete(eventId);
    }
  }

  function upsertEvent(event) {
    const detail = normalizeDetailEvent(event);
    const indexEvent = detailToIndexEvent(detail);
    const index = state.eventsIndex.findIndex((item) => item.id === indexEvent.id);
    if (index >= 0) {
      state.eventsIndex[index] = { ...state.eventsIndex[index], ...indexEvent };
    } else {
      state.eventsIndex.push(indexEvent);
    }
    state.eventsIndex.sort(compareTimelineEvents);
    state.detailCache.set(detail.id, detail);
    updateTopicSummary(indexEvent.topicId);
    return detail;
  }

  function patchEvent(eventId, patch) {
    const id = Number(eventId);
    const index = state.eventsIndex.findIndex((event) => event.id === id);
    const topicId = index >= 0 ? state.eventsIndex[index].topicId : detailById(id)?.topicId;
    if (index >= 0) state.eventsIndex[index] = { ...state.eventsIndex[index], ...patch };
    const cached = state.detailCache.get(id);
    if (cached) state.detailCache.set(id, { ...cached, ...patch });
    updateTopicSummary(topicId);
  }

  function removeEvent(eventId) {
    const id = Number(eventId);
    const existing = eventById(id);
    replaceEvents(state.eventsIndex.filter((event) => event.id !== id));
    state.detailCache.delete(id);
    updateTopicSummary(existing?.topicId);
  }

  return {
    state,
    detailById,
    ensureTopicEvents,
    ensureEventDetail,
    eventById,
    eventsForTopic,
    isTopicEventsLoaded,
    loadIndex,
    loadTopics,
    patchEvent,
    removeEvent,
    removeTopic,
    topicById,
    upsertEvent,
    upsertTopic,
  };
}
