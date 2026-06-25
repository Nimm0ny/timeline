import { reactive } from "vue";
import { api } from "./useApi";

const THEME_META = {
  dark: { label: "暗色", icon: "☾" },
  light: { label: "明亮", icon: "☀" },
};

const state = reactive({
  current: "dark",
  themes: [],
  loaded: false,
});

function ensureThemeLink() {
  let link = document.getElementById("theme-link");
  if (!link) {
    link = document.createElement("link");
    link.id = "theme-link";
    link.rel = "stylesheet";
    document.head.appendChild(link);
  }
  return link;
}

export function themeMeta(name) {
  return THEME_META[name] || { label: name, icon: "◐" };
}

export function applyTheme(name, options = {}) {
  const link = ensureThemeLink();
  const suffix = options.cacheBust ? `?t=${Date.now()}` : "";
  state.current = name;
  link.href = `/theme/${name}.css${suffix}`;
  localStorage.setItem("theme", name);
}

export async function initTheme() {
  ensureThemeLink();
  state.current = localStorage.getItem("theme") || "dark";
  applyTheme(state.current);

  try {
    state.themes = await api.listThemes();
  } catch (_) {
    state.themes = ["dark", "light"];
  } finally {
    state.loaded = true;
  }
}

export async function refreshThemes() {
  state.themes = await api.listThemes();
}

export function useThemeStore() {
  return state;
}
