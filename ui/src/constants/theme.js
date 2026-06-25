// Appearance/theme baseline. Presets carry a COMPLETE :root token set so a pure
// preset reproduces the hand-tuned values exactly (no derivation drift); custom
// knobs (accent/background/foreground/contrast/fonts) overlay recomputed groups
// on top of the chosen base. See docs/appearance-system-design.md.

// Light = the exact current timeline-notes.css :root values (zero-drift default).
export const LIGHT_TOKENS = {
  "--accent": "#7b68d9",
  "--accent-hover": "#6a56cf",
  "--accent-contrast": "#ffffff",
  "--accent-soft": "rgba(123, 104, 217, 0.1)",
  "--accent-soft-2": "rgba(123, 104, 217, 0.16)",
  "--accent-line": "rgba(123, 104, 217, 0.34)",
  "--bg-app": "#efeeec",
  "--bg-sidebar": "#f3f2f0",
  "--bg-timeline": "#faf9f8",
  "--bg-detail": "#ffffff",
  "--bg-surface": "#ffffff",
  "--bg-surface-2": "#f5f4f2",
  "--bg-hover": "rgba(20, 18, 14, 0.045)",
  "--border": "#e5e2dc",
  "--border-soft": "#edeae4",
  "--border-strong": "#d8d4cc",
  "--text": "#2b2824",
  "--text-strong": "#1d1b18",
  "--text-muted": "#6f6a62",
  "--text-faint": "#a59f95",
  "--rail": "#d8d2c8",
  "--scrim": "rgba(40, 34, 24, 0.34)",
  "--shadow-pop": "0 10px 34px rgba(30, 24, 14, 0.14), 0 1px 0 rgba(0, 0, 0, 0.02)",
};

// Dark token group (design §3.1) — independently tuned, not a light inversion.
export const DARK_TOKENS = {
  "--accent": "#8c7ae6",
  "--accent-hover": "#7d6ad9",
  "--accent-contrast": "#ffffff",
  "--accent-soft": "rgba(140, 122, 230, 0.16)",
  "--accent-soft-2": "rgba(140, 122, 230, 0.24)",
  "--accent-line": "rgba(140, 122, 230, 0.4)",
  "--bg-app": "#1a1917",
  "--bg-sidebar": "#1e1d1b",
  "--bg-timeline": "#201f1d",
  "--bg-detail": "#242220",
  "--bg-surface": "#242220",
  "--bg-surface-2": "#2b2926",
  "--bg-hover": "rgba(255, 252, 245, 0.05)",
  "--border": "#332f2a",
  "--border-soft": "#2a2723",
  "--border-strong": "#403b34",
  "--text": "#e8e4dc",
  "--text-strong": "#f5f1e9",
  "--text-muted": "#a59f94",
  "--text-faint": "#736d63",
  "--rail": "#3a352e",
  "--scrim": "rgba(0, 0, 0, 0.5)",
  "--shadow-pop": "0 10px 34px rgba(0, 0, 0, 0.4)",
};

// Knob defaults per resolved mode; defaults equal the base tokens so an
// uncustomized preset triggers no recomputation (and thus no drift).
export const PRESET_KNOBS = {
  light: {
    accent: "#7b68d9",
    background: "#efeeec",
    foreground: "#2b2824",
    contrast: 85,
    uiFont: "Noto Sans SC",
    bodyFont: "Noto Sans SC",
    markdown: "default",
  },
  dark: {
    accent: "#8c7ae6",
    background: "#1a1917",
    foreground: "#e8e4dc",
    contrast: 85,
    uiFont: "Noto Sans SC",
    bodyFont: "Noto Sans SC",
    markdown: "default",
  },
};

export const PRESETS = [
  { id: "system", label: "系统", hint: "跟随系统浅/深" },
  { id: "light", label: "浅色", hint: "默认亮色" },
  { id: "dark", label: "深色", hint: "暗色令牌组" },
];

export const FONT_OPTIONS = [
  { value: "Noto Sans SC", label: "Noto Sans SC（默认）" },
  { value: "PingFang SC", label: "PingFang SC" },
  { value: "Microsoft YaHei", label: "微软雅黑" },
  { value: "Segoe UI", label: "Segoe UI" },
  { value: "system-ui", label: "系统默认" },
];

export const MARKDOWN_OPTIONS = [
  { value: "default", label: "编年默认" },
  { value: "clown", label: "clown（Typora 风）" },
  { value: "custom", label: "自定义（导入）" },
];

export const DEFAULT_THEME = {
  mode: "system",
  accent: "#7b68d9",
  background: "#efeeec",
  foreground: "#2b2824",
  contrast: 85,
  uiFont: "Noto Sans SC",
  bodyFont: "Noto Sans SC",
  markdown: "default",
};

export const THEME_STORAGE_KEY = "chronicle-theme";
export const MARKDOWN_CUSTOM_KEY = "chronicle-md-custom";
