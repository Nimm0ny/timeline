import { reactive } from "vue";

const state = reactive({
  items: [],
});

let nextId = 1;

export function pushToast(message, type = "success") {
  const id = nextId++;
  state.items.push({ id, message, type });
  window.setTimeout(() => {
    removeToast(id);
  }, 2600);
}

export function removeToast(id) {
  const index = state.items.findIndex((item) => item.id === id);
  if (index >= 0) {
    state.items.splice(index, 1);
  }
}

export function useToastStore() {
  return state;
}
