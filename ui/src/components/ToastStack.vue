<script setup>
import { useToastStore, removeToast } from "@/composables/useToast";

const toastStore = useToastStore();
</script>

<template>
  <div class="toast-stack">
    <transition-group name="toast">
      <div
        v-for="item in toastStore.items"
        :key="item.id"
        class="toast-item"
        :class="`toast-${item.type}`"
      >
        <span>{{ item.message }}</span>
        <button class="toast-close" type="button" @click="removeToast(item.id)">
          ×
        </button>
      </div>
    </transition-group>
  </div>
</template>
