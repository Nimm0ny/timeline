import { reactive } from "vue";
import { getPretextSupport } from "@/services/pretextLayout";

const state = reactive({
  checked: false,
  supported: false,
  reason: "",
});

export function initPretextSupport() {
  const support = getPretextSupport();
  state.checked = true;
  state.supported = support.supported;
  state.reason = support.reason;
}

export function usePretextSupportStore() {
  return state;
}
