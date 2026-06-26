import { computed, onBeforeUnmount, onMounted, ref } from "vue";

const MOBILE_MAX_WIDTH = 768;
const COMPACT_DESKTOP_MAX_WIDTH = 1024;

function readViewport() {
  if (typeof window === "undefined") {
    return { width: 1024, height: 768 };
  }
  return {
    width: window.innerWidth,
    height: window.innerHeight,
  };
}

export function useViewport() {
  const viewport = ref(readViewport());

  function updateViewport() {
    viewport.value = readViewport();
  }

  onMounted(() => {
    updateViewport();
    window.addEventListener("resize", updateViewport, { passive: true });
  });

  onBeforeUnmount(() => {
    if (typeof window !== "undefined") {
      window.removeEventListener("resize", updateViewport);
    }
  });

  const width = computed(() => viewport.value.width);
  const height = computed(() => viewport.value.height);
  const isMobile = computed(() => width.value <= MOBILE_MAX_WIDTH);
  const isCompactDesktop = computed(() => width.value > MOBILE_MAX_WIDTH && width.value <= COMPACT_DESKTOP_MAX_WIDTH);

  return {
    width,
    height,
    isMobile,
    isCompactDesktop,
  };
}
