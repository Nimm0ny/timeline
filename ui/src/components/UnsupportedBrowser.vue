<script setup>
defineProps({
  reason: {
    type: String,
    default: "",
  },
});
</script>

<template>
  <main class="unsupported-shell">
    <section class="unsupported-panel">
      <p class="eyebrow">Unsupported Browser</p>
      <h1>Pretext runtime is required.</h1>
      <p class="unsupported-copy">
        This app now depends on `Intl.Segmenter` and browser canvas text measurement for timeline, editor, and export layout.
      </p>
      <p class="unsupported-reason">{{ reason || "The current browser runtime cannot initialize Pretext." }}</p>
    </section>
  </main>
</template>
