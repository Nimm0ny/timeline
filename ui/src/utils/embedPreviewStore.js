// Reactive preview store for canvas note-embed cards (W5 §7.4). An embed card renders another
// note's title/preview; on canvas open we fetch every embedded id in ONE batch-preview request
// and fill this store, so N cards cost O(1) round-trips and pan/zoom triggers zero fetches.
//
// Kept SEPARATE from noteUtils.js's EVENT_PREVIEW_CACHE on purpose: that one is a plain
// (non-reactive) Map, but an embed card must re-render the instant its batch lands — that needs
// Vue reactivity. Keyed by String(noteId). A requested id the backend omits is marked "missing"
// (deleted/inaccessible target → tombstone, §7.5). An id that was never requested returns
// undefined, so the card falls back to the headline cached in its node data until a batch lands.
import { reactive } from "vue";
import { api } from "@/composables/useApi";

const store = reactive(new Map());
const STORE_LIMIT = 600;

// LRU touch: delete-then-set moves a re-resolved key to the BACK of the Map's insertion order,
// so the current canvas's just-fetched entries are always the newest and eviction (from the
// front) only ever drops genuinely stale entries — never a card that is still on screen.
function setEntry(key, value) {
  store.delete(key);
  store.set(key, value);
}

function evictIfNeeded() {
  while (store.size > STORE_LIMIT) {
    const oldest = store.keys().next().value;
    if (oldest === undefined) break;
    store.delete(oldest);
  }
}

// The reactive entry for a note id, or undefined if never fetched (caller shows a fallback).
export function getEmbedEntry(noteId) {
  if (noteId == null || noteId === "") return undefined;
  return store.get(String(noteId));
}

// Fetch preview data for a set of embedded ids and fill the store. Called on every canvas open —
// it always refetches (that single batch is the §7.4 budget) so a renamed/edited target shows its
// fresh title without a reload.
export async function resolveEmbedPreviews(ids) {
  const wanted = [];
  const seen = new Set();
  for (const raw of ids || []) {
    if (raw == null || raw === "") continue;
    const key = String(raw);
    if (seen.has(key)) continue;
    seen.add(key);
    wanted.push(key);
  }
  if (!wanted.length) return;
  try {
    const rows = await api.getNotesBatchPreview(wanted.map((key) => Number(key)));
    const returned = new Set();
    for (const row of Array.isArray(rows) ? rows : []) {
      const key = String(row.id);
      returned.add(key);
      setEntry(key, {
        status: "resolved",
        headline: (row.headline || "").trim(),
        preview: (row.preview || "").trim(),
        container: (row.container || "").trim(),
        noteType: row.noteType || "entry",
      });
    }
    // Any requested id the backend did not return is deleted/inaccessible → tombstone.
    for (const key of wanted) {
      if (!returned.has(key)) setEntry(key, { status: "missing" });
    }
    evictIfNeeded();
  } catch {
    // A failed refetch must not leave a STALE tombstone standing (a since-restored note would
    // keep showing "已删除"): drop any tombstone for the requested ids so it reverts to the
    // neutral fallback and retries on the next open. Never-fetched ids stay unset (fallback).
    for (const key of wanted) {
      if (store.get(key)?.status === "missing") store.delete(key);
    }
  }
}
