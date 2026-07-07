import test from "node:test";
import assert from "node:assert/strict";

import { api } from "../src/composables/useApi.js";
import { useTimelineStore } from "../src/composables/useTimelineStore.js";

function detailEvent(id) {
  return {
    id,
    topicId: 1,
    dateKey: 18400101 + id,
    dateParts: { year: 1840, month: 1, day: id },
    isoDate: `1840-01-${String(id).padStart(2, "0")}`,
    displayLabel: `1840-01-${String(id).padStart(2, "0")}`,
    headline: `Event ${id}`,
    era: "Modern China",
    noteType: "entry",
    bodyMarkdown: `Body ${id}`,
    attachments: [],
    relatedEvents: [],
    items: [],
    extra: {},
    favorite: false,
    deletedAt: null,
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
  };
}

test("ensureEventDetail forwards AbortSignal to api.getEvent", async () => {
  const store = useTimelineStore();
  const original = api.getEvent;
  const controller = new AbortController();
  let seenSignal = null;
  api.getEvent = async (id, options = {}) => {
    seenSignal = options.signal;
    return detailEvent(id);
  };

  try {
    const event = await store.ensureEventDetail(9, { signal: controller.signal });
    assert.equal(event.id, 9);
    assert.equal(seenSignal, controller.signal);
  } finally {
    api.getEvent = original;
  }
});

test("detail cache is capped and keeps the protected entry", () => {
  const store = useTimelineStore();
  store.setProtectedDetailId(1);
  for (let index = 1; index <= 45; index += 1) {
    store.upsertEvent(detailEvent(index));
  }

  assert.equal(store.state.detailCache.size, 40);
  assert.ok(store.detailById(1));
  assert.equal(store.detailById(2), null);
  assert.ok(store.detailById(45));
});
