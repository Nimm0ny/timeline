import { createApp } from "vue";
import App from "./App.vue";
import router from "./router";
import "./styles/main.css";
import "./styles/timeline-notes.css";
import { restoreAuth } from "./composables/useAuth";
import { initPretextSupport } from "./composables/usePretextSupport";
import { initTheme } from "./composables/useTheme";

initPretextSupport();
initTheme();
restoreAuth();

createApp(App).use(router).mount("#app");
