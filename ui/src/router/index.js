import { createRouter, createWebHistory } from "vue-router";
import TimelinePage from "@/pages/TimelinePage.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "timeline",
      component: TimelinePage,
    },
    {
      path: "/editor",
      redirect: "/",
    },
  ],
});

export default router;
