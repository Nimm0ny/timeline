import { createRouter, createWebHistory } from "vue-router";
import NotesPage from "@/pages/NotesPage.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "timeline",
      component: NotesPage,
    },
    {
      path: "/editor",
      redirect: "/",
    },
  ],
});

export default router;
