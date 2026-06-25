# Prototype Icon Source Audit

## Conclusion

`timeline_notes_pixel_perfect_1920x1080_one_view.html` does not contain original design source, SVG symbols, iconfont files, or Figma/Sketch metadata. It contains one embedded PNG screenshot and hotspot styles only.

Runtime implementation decision: the product now uses Lucide SVG icons from `@lucide/vue`, rendered through `ui/src/components/timeline-notes/TimelineLucideIcon.vue`. This audit remains a source-finding record only; it is not the active implementation plan for icon tokens.

PNG metadata check:
- PNG size: `1,451,825` bytes
- SHA-256: `35e0e0eef3936b2741481d58890490794f1d13dd78bd1695f583b562e270a5f9`
- Chunks: `IHDR`, multiple `IDAT`, `IEND`
- Text metadata chunks: `0`

## Source SVGs Found Locally

Some icon sources exist in older DOM prototypes and were reviewed without tracing the PNG:

- Source file: `prototypes/timeline-notes-product.html`
- Supplemental source file: `prototypes/timeline-notes-mobile-apple.html`

Those older symbols are not retained as project assets because the current runtime icon source is Lucide.

## Missing Original Sources

No local original source was found for these newer one-view prototype icons:

- red book brand mark in the 1920 one-view PNG
- right actionbar left arrow
- right actionbar right arrow
- right actionbar lock
- right actionbar three-dot more
- Obsidian-style edit/read toggle icon if it differs from close/edit source
- composer flag icon
- right detail meta green plant icon

The previous project-side token approach for those icons was not original source asset usage. It has been retired in favor of Lucide runtime SVG icons unless the upstream design source is later supplied.

## Required Upstream Asset

To avoid PNG tracing for missing icons, request one of these from the prototype author or design tool:

- Figma file or shared design link with icon components
- exported SVG sprite
- iconfont package: `.ttf/.woff/.woff2` plus CSS mapping
- raw SVG folder
- original non-raster HTML/CSS prototype that generated the 1920 one-view PNG
