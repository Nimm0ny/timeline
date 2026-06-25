<script setup>
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
      <div class="modal-card" :class="{ 'modal-wide': props.wide }">
        <div class="modal-head">
          <h3>{{ props.title }}</h3>
          <button type="button" class="icon-btn" @click="close">×</button>
        </div>
        <div class="modal-body">
          <slot />
        </div>
      </div>
    </div>
  </Teleport>
</template>
