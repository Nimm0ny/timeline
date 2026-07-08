import test from "node:test";
import assert from "node:assert/strict";

import { api } from "../src/composables/useApi.js";
import { useNotesStore } from "../src/composables/useNotesStore.js";

function indexPage(ids) {
  return {
    items: ids.map((id) => ({
      id,
      topicId: 1,
      dateKey: 18400000 + id,
      headline: `E${id}`,
      era: "Modern China",
      noteType: "entry",
    })),
    bounds: null,
    hasMore: false,
    nextCursor: null,
  };
}

// Regression for the stale-response race (wave-1 review P0): a rapid 正序⇄倒序
// toggle puts two forced page-1 fetches in flight; if the earlier (ascending)
// one resolves last it must NOT clobber the current (descending) page.
test("ensureTopicNotes drops a superseded opposite-direction response", async () => {
  const store = useNotesStore();
  const original = api.getNotes;
  const resolvers = {};
  api.getNotes = (_topicId, { dir } = {}) =>
    new Promise((resolve) => {
      resolvers[dir] = resolve;
    });

  try {
    const ascending = store.ensureTopicNotes(1, { force: true, dir: 1 }); // A (stale-to-be)
    const descending = store.ensureTopicNotes(1, { force: true, dir: -1 }); // B (current)

    resolvers[-1](indexPage([201, 202])); // B (current) resolves first
    await descending;
    resolvers[1](indexPage([101, 102])); // A (superseded) lands last
    await ascending;

    const ids = store
      .notesForTopic(1)
      .map((event) => event.id)
      .sort((a, b) => a - b);
    assert.deepEqual(ids, [201, 202]); // descending page survived; ascending was dropped
  } finally {
    api.getNotes = original;
  }
});
