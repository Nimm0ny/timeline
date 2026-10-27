import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";

function manualChunks(id) {
  if (!id.includes("node_modules")) return undefined;
  if (id.includes("@codemirror/")) return "markdown-vendor";
  if (id.includes("@lucide/vue")) return "icons-vendor";
  if (id.includes("vue-router")) return "vue-vendor";
  if (id.includes("/vue/")) return "vue-vendor";
  return "vendor";
}

const OPTIONAL_PRELOAD_CHUNKS = [
  "CommandPalette-",
  "SettingsModal-",
  "MarkdownLiveEditor-",
  "markdown-vendor-",
];

const apiTarget = process.env.CHRONICLE_API_TARGET || "http://127.0.0.1:8000";

export default defineConfig({
  root: fileURLToPath(new URL(".", import.meta.url)),
  plugins: [vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    host: "0.0.0.0",
    port: Number(process.env.PORT) || 5173,
    proxy: {
      "/api": apiTarget,
      "/theme": apiTarget,
      "/images": apiTarget,
    },
  },
  build: {
    outDir: "../frontend",
    emptyOutDir: true,
    modulePreload: {
      resolveDependencies(_url, deps) {
        return deps.filter((dep) => !OPTIONAL_PRELOAD_CHUNKS.some((needle) => dep.includes(needle)));
      },
    },
    rollupOptions: {
      output: {
        manualChunks,
      },
    },
  },
});
