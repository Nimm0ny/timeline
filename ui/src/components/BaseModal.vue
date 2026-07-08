<script setup>
import LucideIcon from "@/components/timeline-notes/LucideIcon.vue";

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
  title: {
    type: String,
    default: "",
  },
  wide: {
    type: Boolean,
    default: false,
  },
  hideHeader: {
    type: Boolean,
    default: false,
  },
  ariaLabel: {
    type: String,
    default: "",
  },
  cardClass: {
    type: String,
    default: "",
  },
  bodyClass: {
    type: String,
    default: "",
  },
});

const emit = defineEmits(["update:modelValue"]);

function close() {
  emit("update:modelValue", false);
}

function onBackdropClick(event) {
  if (event.target === event.currentTarget) {
    close();
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="props.modelValue" class="modal-backdrop" @click="onBackdropClick">
      <div
        class="modal-card"
        :class="[{ 'modal-wide': props.wide }, props.cardClass]"
        role="dialog"
        aria-modal="true"
        :aria-label="props.ariaLabel || props.title"
      >
        <div v-if="!props.hideHeader" class="modal-head">
          <h3>{{ props.title }}</h3>
          <button type="button" class="icon-btn" title="关闭" @click="close">
            <LucideIcon name="close" :stroke-width="1.5" />
          </button>
        </div>
        <div class="modal-body" :class="props.bodyClass">
          <slot />
        </div>
      </div>
    </div>
  </Teleport>
</template>
