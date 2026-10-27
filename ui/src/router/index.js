import { createRouter, createWebHistory } from "vue-router";
import NotesPage from "@/pages/NotesPage.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "notes",
      component: NotesPage,
    },
  ],
});

export default router;
