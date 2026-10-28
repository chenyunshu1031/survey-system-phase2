import { createRouter, createWebHistory } from 'vue-router'
import { readToken } from './api/client'
import AuthPage from './pages/AuthPage.vue'
import SurveysPage from './pages/SurveysPage.vue'
import SurveyEditorPage from './pages/SurveyEditorPage.vue'
import PublicSurveyPage from './pages/PublicSurveyPage.vue'
import SurveyResultsPage from './pages/SurveyResultsPage.vue'
import LibraryPage from './pages/LibraryPage.vue'
import LibraryQuestionPage from './pages/LibraryQuestionPage.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/surveys' },
    { path: '/login', component: AuthPage },
    { path: '/surveys', component: SurveysPage, meta: { requiresAuth: true } },
    { path: '/library', component: LibraryPage, meta: { requiresAuth: true } },
    { path: '/library/questions/:id', component: LibraryQuestionPage, meta: { requiresAuth: true } },
    { path: '/surveys/:id/edit', component: SurveyEditorPage, meta: { requiresAuth: true } },
    { path: '/surveys/:id/results', component: SurveyResultsPage, meta: { requiresAuth: true } },
    { path: '/survey/:slug', component: PublicSurveyPage, meta: { requiresAuth: true } },
  ],
})

router.beforeEach((to) => {
  if (to.meta.requiresAuth && !readToken()) return { path: '/login', query: { next: to.fullPath } }
  if (to.path === '/login' && readToken()) return '/surveys'
})

export default router
