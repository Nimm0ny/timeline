<script setup>
import { buildSearchHighlightSegments } from "@/utils/timelineNotes";

// Renders `text` with case-insensitive occurrences of `query` wrapped in
// <mark class="tn-hl"> (the global feed highlight). Fragment root (no wrapper
// element) so it drops into any inline context — date cell, title <b>, chip,
// property column, era header. XSS-safe: every segment goes through Vue text
// interpolation, never v-html. Off-search it is a single plain segment, so the
// rendered text is byte-identical to a bare interpolation.
defineProps({
  text: { type: String, default: "" },
  query: { type: String, default: "" },
});
</script>

<template
  ><template
    v-for="(seg, i) in buildSearchHighlightSegments(text, query)"
    :key="i"
  ><mark v-if="seg.hit" class="tn-hl">{{ seg.text }}</mark><template v-else>{{ seg.text }}</template></template
></template>
