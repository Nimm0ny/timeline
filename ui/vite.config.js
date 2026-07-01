import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";

function manualChunks(id) {
  if (!id.includes("node_modules")) return undefined;
  if (id.includes("@codemirror/")) return "markdown-vendor";
  if (id.includes("@antv/x6")) return "mindmap-vendor";
  if (id.includes("@antv/x6-plugin-history") || id.includes("@antv/x6-plugin-selection")) return "mindmap-vendor";
  if (id.includes("@lucide/vue")) return "icons-vendor";
  if (id.includes("vue-router")) return "vue-vendor";
  if (id.includes("/vue/")) return "vue-vendor";
  return "vendor";
}

const OPTIONAL_PRELOAD_CHUNKS = [
  "CommandPalette-",
  "SettingsModal-",
  "MarkdownLiveEditor-",
  "MindmapSurface-",
  "markdown-vendor-",
  "mindmap-vendor-",
];

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
      "/api": "http://localhost:8000",
      "/theme": "http://localhost:8000",
      "/images": "http://localhost:8000",
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
