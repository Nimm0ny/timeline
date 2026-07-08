import { createApp } from "vue";
import App from "./App.vue";
import router from "./router";
import "./styles/main.css";
import "./styles/notes.css";
import { initPretextSupport } from "./composables/usePretextSupport";
import { initTheme } from "./composables/useTheme";

initPretextSupport();
initTheme();

createApp(App).use(router).mount("#app");
