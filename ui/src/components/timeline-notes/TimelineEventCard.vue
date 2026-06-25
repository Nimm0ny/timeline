<script setup>
import { computed } from "vue";
import TimelineLucideIcon from "@/components/timeline-notes/TimelineLucideIcon.vue";
import { buildEventPreview, collectEventTags } from "@/utils/timelineNotes";

const props = defineProps({
  event: {
    type: Object,
    required: true,
  },
  layout: {
    type: Object,
    default: null,
  },
  active: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["select", "toggle-favorite", "open-menu"]);

const tags = computed(() => collectEventTags(props.event).slice(0, 3));
const previewText = computed(() => props.layout?.previewText || buildEventPreview(props.event));
const cardStyle = computed(() => {
  if (!props.layout?.estimatedHeight) return {};
  const activeHeight = Math.max(props.layout.estimatedHeight, props.layout.activeMinHeight || 175);
  return {
    "--timeline-card-height": `${props.layout.estimatedHeight}px`,
    "--timeline-card-active-height": `${activeHeight}px`,
  };
});

function selectCard() {
  emit("select", props.event.id);
}
</script>

<template>
  <article
    class="timeline-note-card"
    :data-event-id="props.event.id"
    :class="{ active: props.active, deleted: props.event.deletedAt }"
    :style="cardStyle"
    tabindex="0"
    role="button"
    @click="selectCard"
    @keydown.enter.prevent="selectCard"
    @keydown.space.prevent="selectCard"
  >
    <div class="timeline-note-head">
      <h3>{{ props.event.headline || props.event.displayLabel }}</h3>
      <div class="timeline-card-actions">
        <button
          type="button"
          class="timeline-card-icon"
          :class="{ active: props.event.favorite }"
          :disabled="Boolean(props.event.deletedAt)"
          :aria-label="props.event.favorite ? '取消收藏' : '收藏'"
          @click.stop="emit('toggle-favorite', props.event)"
        >
          <TimelineLucideIcon name="star" :stroke-width="1.8" />
        </button>
        <button
          type="button"
          class="timeline-card-icon"
          aria-label="更多操作"
          @click.stop="emit('open-menu', props.event)"
        >
          <TimelineLucideIcon name="more" :stroke-width="1.8" />
        </button>
      </div>
    </div>

    <p>{{ previewText }}</p>

    <div class="timeline-chip-row">
      <span v-for="tag in tags" :key="tag.value" class="timeline-chip">
        {{ tag.label }}
      </span>
    </div>
  </article>
</template>
