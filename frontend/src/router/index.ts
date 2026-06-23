import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'templates', component: () => import('../views/TemplateList.vue'), props: true },
    { path: '/annotate/:id', name: 'annotate', component: () => import('../views/AnnotationWorkbench.vue'), props: true },
    { path: '/review', name: 'review', component: () => import('../views/ReviewWorkbench.vue') },
  ]
})

export default router
