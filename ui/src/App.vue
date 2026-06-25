<script setup>
import { RouterView } from "vue-router";
import LoginModal from "@/components/LoginModal.vue";
import ToastStack from "@/components/ToastStack.vue";
</script>

<template>
  <div class="app-shell">
    <RouterView />
    <LoginModal />
    <ToastStack />
  </div>
</template>
