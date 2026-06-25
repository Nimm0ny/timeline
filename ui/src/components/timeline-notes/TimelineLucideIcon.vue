<script setup>
import { computed } from "vue";
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  CalendarDays,
  ChevronDown,
  FileText,
  Flag,
  Image,
  Leaf,
  LockKeyhole,
  Menu,
  MoreHorizontal,
  NotebookText,
  PenLine,
  Plus,
  Search,
  SendHorizontal,
  Settings,
  SquarePen,
  Star,
  Trash2,
  X,
} from "@lucide/vue";

const props = defineProps({
  name: {
    type: String,
    required: true,
  },
  strokeWidth: {
    type: Number,
    default: 1.8,
  },
});

const icons = {
  arrowLeft: ArrowLeft,
  arrowRight: ArrowRight,
  book: BookOpen,
  calendar: CalendarDays,
  chevronDown: ChevronDown,
  close: X,
  edit: SquarePen,
  file: FileText,
  flag: Flag,
  image: Image,
  leaf: Leaf,
  lock: LockKeyhole,
  menu: Menu,
  more: MoreHorizontal,
  note: NotebookText,
  pen: PenLine,
  plus: Plus,
  search: Search,
  send: SendHorizontal,
  settings: Settings,
  star: Star,
  trash: Trash2,
};

const icon = computed(() => icons[props.name] || MoreHorizontal);
</script>

<template>
  <component
    :is="icon"
    class="timeline-lucide-icon"
    aria-hidden="true"
    focusable="false"
    :stroke-width="props.strokeWidth"
  />
</template>
