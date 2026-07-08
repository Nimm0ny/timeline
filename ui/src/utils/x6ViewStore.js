// Per-note X6 viewport (pan + zoom) persistence in localStorage.
//
// The viewport is a per-device UI state — like a scroll position — NOT note content.
// Keeping it OUT of the DB `body_json` snapshot means panning/zooming a canvas or
// mindmap never bumps the note's `updated_at`. That matters twice over: it stops a note
// from wrongly floating to the top of `updated desc` feeds just because it was looked
// at, and it stops the canvas autosave from firing a PUT on every pan frame (which W5's
// continuous-pan lazy rendering would amplify). Content edits still autosave to the DB;
// only the viewport rides localStorage. See docs/notes-app-pivot-design.md §5.5.

const PREFIX = "x6view:";

function keyFor(scope, noteId) {
  if (noteId == null || noteId === "") return "";
  return `${PREFIX}${scope}:${noteId}`;
}

// Returns { tx, ty, zoom } or null (missing/corrupt/unavailable → caller falls back to
// the snapshot's legacy view, then centerContent).
export function readX6View(scope, noteId) {
  const key = keyFor(scope, noteId);
  if (!key) return null;
  try {
    // `typeof localStorage` must sit INSIDE the try: in a sandboxed iframe (no
    // allow-same-origin) merely reading the `localStorage` property throws SecurityError,
    // so an outside guard would throw before the try — crashing applyGraphState on open.
    if (typeof localStorage === "undefined") return null;
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && (parsed.tx != null || parsed.ty != null || parsed.zoom != null)) {
      return { tx: Number(parsed.tx) || 0, ty: Number(parsed.ty) || 0, zoom: Number(parsed.zoom) || 1 };
    }
  } catch {
    // Corrupt entry — ignore and let the caller fall back.
  }
  return null;
}

export function writeX6View(scope, noteId, view) {
  const key = keyFor(scope, noteId);
  if (!key || !view) return;
  try {
    // See readX6View: the localStorage property read itself can throw, so keep it in the try.
    if (typeof localStorage === "undefined") return;
    localStorage.setItem(key, JSON.stringify({ tx: view.tx || 0, ty: view.ty || 0, zoom: view.zoom || 1 }));
  } catch {
    // Storage full / disabled — the viewport just won't persist; non-fatal.
  }
}
