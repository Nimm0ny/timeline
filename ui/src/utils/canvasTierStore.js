// Reactive per-canvas fidelity-tier map for note-embed cards (W5b §7.3). CanvasEditor
// classifies each embed card ("hidden" | "shell" | "preview") on pan/zoom settle and writes
// the batch here; EmbedCardNode reads getCardTier(node.id) and renders at that fidelity.
//
// Deliberately a SEPARATE channel from the X6 node's data: writing tier into node.data /
// node.prop would fire history:change → a content save → bump updated_at (and, mid-pan, one
// PUT per frame). Riding a reactive store OFF the snapshot keeps pan/zoom free of DB writes
// (docs/notes-app-pivot-design.md §5.5 / §7.8). Mirrors embedPreviewStore.js's reactive Map.
// Keyed by String(nodeId); scoped to the open canvas and cleared on note switch / unmount.
import { reactive } from "vue";

const store = reactive(new Map());

// The computed tier for a node id, or undefined before the first recompute — the card then
// falls back to its own default ("preview") so a not-yet-classified card never renders blank.
export function getCardTier(nodeId) {
  if (nodeId == null || nodeId === "") return undefined;
  return store.get(String(nodeId));
}

// Batch-write the tier for every embed node in one recompute. Diffs against the current map
// so ONLY cards whose tier actually changed re-render (a settled, no-op recompute triggers
// nothing), and prunes ids no longer present (a removed embed card). `entries` = iterable of
// [nodeId, tier].
export function setCardTiers(entries) {
  const next = new Map();
  for (const [id, tier] of entries) next.set(String(id), tier);
  for (const [key, tier] of next) {
    if (store.get(key) !== tier) store.set(key, tier);
  }
  for (const key of [...store.keys()]) {
    if (!next.has(key)) store.delete(key);
  }
}

// Drop all tiers — called on canvas note switch / editor unmount so a previous board's tiers
// can't bleed into the next one.
export function clearCardTiers() {
  store.clear();
}
