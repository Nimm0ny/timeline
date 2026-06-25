<script setup>
import { RouterView } from "vue-router";
import ToastStack from "@/components/ToastStack.vue";
</script>

<template>
  <div class="app-shell">
    <RouterView />
    <ToastStack />
  </div>
</template>
