import { reactive } from "vue";
import {
  DARK_TOKENS,
  DEFAULT_THEME,
  LIGHT_TOKENS,
  MARKDOWN_CUSTOM_KEY,
  PRESET_KNOBS,
  THEME_STORAGE_KEY,
} from "../constants/theme.js";

// Token-override theme engine: a few knobs (mode/accent/background/foreground/
// contrast/fonts/markdown) derive the full :root token set. A pure preset applies
// its exact base tokens (no drift); customized knobs overlay recomputed groups.
// See docs/appearance-system-design.md.

const state = reactive({
  config: { ...DEFAULT_THEME },
  resolvedMode: "light", // light | dark, after resolving "system"
});

let mediaQuery = null;

/* ---------- color helpers ---------- */
function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function hexToRgb(hex) {
  const clean = String(hex || "").trim().replace("#", "");
  const full = clean.length === 3 ? clean.split("").map((c) => c + c).join("") : clean;
  const int = Number.parseInt(full, 16);
  if (!Number.isFinite(int) || full.length !== 6) return { r: 0, g: 0, b: 0 };
  return { r: (int >> 16) & 255, g: (int >> 8) & 255, b: int & 255 };
}

function rgbToHex({ r, g, b }) {
  const to = (v) => clamp(Math.round(v), 0, 255).toString(16).padStart(2, "0");
  return `#${to(r)}${to(g)}${to(b)}`;
}

// t = 0 returns a, t = 1 returns b.
function mixHex(a, b, t) {
  const ca = hexToRgb(a);
  const cb = hexToRgb(b);
  const ratio = clamp(t, 0, 1);
  return rgbToHex({
    r: ca.r + (cb.r - ca.r) * ratio,
    g: ca.g + (cb.g - ca.g) * ratio,
    b: ca.b + (cb.b - ca.b) * ratio,
  });
}

function alpha(hex, a) {
  const { r, g, b } = hexToRgb(hex);
  return `rgba(${r}, ${g}, ${b}, ${a})`;
}

function isLightColor(hex) {
  const { r, g, b } = hexToRgb(hex);
  // perceived luminance
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.6;
}

/* ---------- token derivation ---------- */
function accentGroup(accent) {
  return {
    "--accent": accent,
    "--accent-hover": mixHex(accent, "#000000", 0.12),
    "--accent-contrast": isLightColor(accent) ? "#1d1b18" : "#ffffff",
    "--accent-soft": alpha(accent, 0.1),
    "--accent-soft-2": alpha(accent, 0.16),
    "--accent-line": alpha(accent, 0.34),
  };
}

function backgroundGroup(background, dark, foreground) {
  const lift = "#ffffff";
  const r = dark
    ? { sidebar: 0.03, timeline: 0.05, detail: 0.08, surface: 0.08, surface2: 0.12 }
    : { sidebar: 0.3, timeline: 0.7, detail: 1, surface: 1, surface2: 0.45 };
  return {
    "--bg-app": background,
    "--bg-sidebar": mixHex(background, lift, r.sidebar),
    "--bg-timeline": mixHex(background, lift, r.timeline),
    "--bg-detail": mixHex(background, lift, r.detail),
    "--bg-surface": mixHex(background, lift, r.surface),
    "--bg-surface-2": mixHex(background, lift, r.surface2),
    "--bg-hover": alpha(foreground, dark ? 0.06 : 0.045),
  };
}

function textGroup(foreground, background, dark, contrast) {
  const extreme = dark ? "#ffffff" : "#000000";
  // higher contrast keeps muted/faint nearer the foreground
  const spread = clamp((100 - contrast) / 100, 0, 0.6);
  return {
    "--text": foreground,
    "--text-strong": mixHex(foreground, extreme, 0.28),
    "--text-muted": mixHex(foreground, background, 0.32 + spread * 0.4),
    "--text-faint": mixHex(foreground, background, 0.55 + spread * 0.5),
    "--rail": mixHex(background, foreground, 0.22),
    "--border": mixHex(background, foreground, 0.12 + spread * 0.1),
    "--border-soft": mixHex(background, foreground, 0.07),
    "--border-strong": mixHex(background, foreground, 0.2 + spread * 0.12),
  };
}

function fontStack(name) {
  const fallback = '"Noto Sans SC", "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif';
  if (!name || name === "Noto Sans SC") return fallback;
  return `"${name}", ${fallback}`;
}

function resolveMode(mode) {
  if (mode === "dark") return "dark";
  if (mode === "light") return "light";
  if (typeof window !== "undefined" && window.matchMedia) {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return "light";
}

// A knob is a real customization only when it differs from BOTH preset defaults.
// This keeps "system" mode seed-agnostic: its light-seeded knobs are NOT treated
// as overrides when system resolves to dark (and vice-versa), so a pure preset —
// including the default first-run on a dark-mode OS — always yields the exact
// base token set, never a light-on-dark hybrid.
function isCustomKnob(config, key) {
  const value = config[key];
  return value != null && value !== PRESET_KNOBS.light[key] && value !== PRESET_KNOBS.dark[key];
}

export function deriveTokens(config) {
  const resolved = resolveMode(config.mode);
  const dark = resolved === "dark";
  const base = dark ? DARK_TOKENS : LIGHT_TOKENS;
  const presetKnobs = dark ? PRESET_KNOBS.dark : PRESET_KNOBS.light;
  const tokens = { ...base };

  if (isCustomKnob(config, "accent")) {
    Object.assign(tokens, accentGroup(config.accent));
  }
  const background = config.background || presetKnobs.background;
  const foreground = config.foreground || presetKnobs.foreground;
  const contrast = Number.isFinite(config.contrast) ? config.contrast : presetKnobs.contrast;
  if (isCustomKnob(config, "background")) {
    Object.assign(tokens, backgroundGroup(background, dark, foreground));
  }
  if (isCustomKnob(config, "foreground") || isCustomKnob(config, "contrast") || isCustomKnob(config, "background")) {
    Object.assign(tokens, textGroup(foreground, background, dark, contrast));
  }
  return { tokens, resolved };
}

/* ---------- custom markdown ---------- */
function ensureCustomMarkdownStyle() {
  let style = document.getElementById("md-custom-style");
  if (!style) {
    style = document.createElement("style");
    style.id = "md-custom-style";
    document.head.appendChild(style);
  }
  return style;
}

// Scope imported CSS to `.markdown-body` so it can't bleed into the app shell.
// Accepts Typora-style `#write` selectors too by remapping them.
function scopeMarkdownCss(css) {
  const safe = String(css || "").replace(/<\/?style[^>]*>/gi, "");
  return safe.replace(/(^|[}\s,])(#write|body|html)\b/gi, "$1.markdown-body");
}

export function setCustomMarkdown(css) {
  localStorage.setItem(MARKDOWN_CUSTOM_KEY, css || "");
  if (state.config.markdown === "custom") applyTheme(state.config);
}

export function getCustomMarkdown() {
  return localStorage.getItem(MARKDOWN_CUSTOM_KEY) || "";
}

/* ---------- apply / persist ---------- */
export function applyTheme(config) {
  const merged = { ...DEFAULT_THEME, ...config };
  const { tokens, resolved } = deriveTokens(merged);
  const root = document.documentElement;
  for (const [name, value] of Object.entries(tokens)) {
    root.style.setProperty(name, value);
  }
  root.style.setProperty("--tn-font", fontStack(merged.uiFont));
  root.dataset.theme = resolved;
  root.dataset.md = merged.markdown || "default";

  const customStyle = ensureCustomMarkdownStyle();
  customStyle.textContent = merged.markdown === "custom" ? scopeMarkdownCss(getCustomMarkdown()) : "";

  state.config = merged;
  state.resolvedMode = resolved;
  localStorage.setItem(THEME_STORAGE_KEY, JSON.stringify(merged));
}

export function updateThemeConfig(patch) {
  applyTheme({ ...state.config, ...patch });
}

export function applyPreset(mode) {
  // Seed knob values from the matching preset; for "system" the seed is
  // seed-agnostic in deriveTokens, so it never forces a hybrid on the other OS theme.
  const seed = mode === "dark" ? PRESET_KNOBS.dark : PRESET_KNOBS.light;
  applyTheme({ ...seed, mode, markdown: state.config.markdown });
}

export function importThemeJson(json) {
  let parsed;
  try {
    parsed = typeof json === "string" ? JSON.parse(json) : json;
  } catch {
    throw new Error("主题 JSON 解析失败");
  }
  if (!parsed || typeof parsed !== "object") throw new Error("无效的主题数据");
  applyTheme({ ...DEFAULT_THEME, ...parsed });
}

export function exportThemeJson() {
  return JSON.stringify(state.config, null, 2);
}

export function initTheme() {
  let stored = null;
  try {
    const raw = localStorage.getItem(THEME_STORAGE_KEY);
    if (raw) stored = JSON.parse(raw);
  } catch {
    stored = null;
  }
  applyTheme({ ...DEFAULT_THEME, ...(stored || {}) });

  if (typeof window !== "undefined" && window.matchMedia) {
    mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      if (state.config.mode === "system") applyTheme(state.config);
    };
    if (mediaQuery.addEventListener) mediaQuery.addEventListener("change", onChange);
    else if (mediaQuery.addListener) mediaQuery.addListener(onChange);
  }
}

export function useThemeStore() {
  return state;
}
