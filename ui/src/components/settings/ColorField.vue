<script setup>
import { computed } from "vue";

const props = defineProps({
  label: { type: String, default: "" },
  modelValue: { type: String, default: "#000000" },
});

const emit = defineEmits(["update:modelValue"]);

const hex = computed({
  get: () => props.modelValue,
  set: (value) => emit("update:modelValue", value),
});

function onHexInput(event) {
  const raw = String(event.target.value || "").trim();
  if (/^#?[0-9a-fA-F]{6}$/.test(raw)) {
    emit("update:modelValue", raw.startsWith("#") ? raw : `#${raw}`);
  }
}
</script>

<template>
  <label class="color-field">
    <span class="color-field-label">{{ props.label }}</span>
    <span class="color-field-control">
      <span class="color-swatch" :style="{ background: hex }">
        <input type="color" :value="hex" @input="hex = $event.target.value" />
      </span>
      <input class="color-hex" type="text" :value="hex" maxlength="7" spellcheck="false" @change="onHexInput" />
    </span>
  </label>
</template>
