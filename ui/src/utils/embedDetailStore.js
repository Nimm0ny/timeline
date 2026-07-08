// Reactive per-canvas full-markdown store for note-embed cards at the T2 "full" tier (W5b-2,
// §7.2/§7.4). When a card is zoomed large enough (§7.3), CanvasEditor fetches the embedded note's
// detail through the shared LRU-40 detail cache (ensureNoteDetail), renders it once with the
// read-mode markdown renderer, and stashes the HTML here; EmbedCardNode reads it and shows the
// full note in place of the 120-char preview.
//
// A SEPARATE off-snapshot channel, like canvasTierStore / embedPreviewStore: the HTML never
// touches node.data, so pan / zoom / T2-promotion trigger no history:change → no save → no
// updated_at bump (docs/notes-app-pivot-design.md §5.5 / §7.8). Keyed by String(noteId). The
// budget caps CONCURRENT full cards; the store itself accumulates one entry per distinct note that
// crosses the full tier this session, so it is bounded by the board's distinct full-tier notes
// (not by the 24 budget) and cleared on canvas note switch / editor unmount. Detail-cache staleness
// is accepted (§6.8/§7.8): an embedded note edited elsewhere refreshes on the next canvas open.
import { reactive } from "vue";

const store = reactive(new Map());

// The rendered full-markdown entry { html } for a note id, or undefined if not yet resolved —
// the card then keeps showing its preview (fail-open, never blank). A resolved-but-empty body is
// stored as { html: "" }, which reads falsy so the card still falls back to preview.
export function getEmbedDetailHtml(noteId) {
  if (noteId == null || noteId === "") return undefined;
  return store.get(String(noteId));
}

// Stash the rendered HTML for a note id. Presence (even of "") marks the id resolved for this
// canvas session, so CanvasEditor won't re-fetch it on every settle; a failed fetch sets nothing
// and is retried on the next recompute.
export function setEmbedDetail(noteId, html) {
  if (noteId == null || noteId === "") return;
  store.set(String(noteId), { html: html || "" });
}

// Drop all rendered detail — on canvas note switch / editor unmount so one board's full text
// can't bleed into the next.
export function clearEmbedDetails() {
  store.clear();
}
