<script setup>
import { computed } from "vue";
import {
  AlignLeft,
  ArrowRight,
  ArrowUpDown,
  BarChart3,
  BookOpen,
  CalendarDays,
  CalendarSearch,
  Check,
  ChevronDown,
  ChevronRight,
  ChevronsDownUp,
  ChevronsUpDown,
  CircleHelp,
  CirclePlus,
  Clock3,
  Columns3,
  Download,
  Eye,
  EyeOff,
  FileText,
  Filter,
  Folder,
  FolderPlus,
  Hash,
  Image,
  LibraryBig,
  Link2,
  List,
  Maximize2,
  MoreHorizontal,
  NotebookText,
  Paperclip,
  Pin,
  Save,
  Search,
  Settings,
  SlidersHorizontal,
  SquarePen,
  Star,
  Leaf,
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
  arrowRight: ArrowRight,
  arrowUpDown: ArrowUpDown,
  alignLeft: AlignLeft,
  bar: BarChart3,
  book: BookOpen,
  calendar: CalendarDays,
  calendarSearch: CalendarSearch,
  check: Check,
  chevronDown: ChevronDown,
  chevronRight: ChevronRight,
  chevronsUpDown: ChevronsUpDown,
  close: X,
  clock: Clock3,
  columns: Columns3,
  download: Download,
  edit: SquarePen,
  eye: Eye,
  eyeOff: EyeOff,
  file: FileText,
  filter: Filter,
  fold: ChevronsDownUp,
  unfold: ChevronsUpDown,
  folder: Folder,
  folderPlus: FolderPlus,
  hash: Hash,
  help: CircleHelp,
  image: Image,
  library: LibraryBig,
  leaf: Leaf,
  link: Link2,
  list: List,
  maximize: Maximize2,
  more: MoreHorizontal,
  note: NotebookText,
  notebook: NotebookText,
  paperclip: Paperclip,
  pin: Pin,
  plus: CirclePlus,
  plusCircle: CirclePlus,
  save: Save,
  search: Search,
  settings: Settings,
  sliders: SlidersHorizontal,
  squarePen: SquarePen,
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
