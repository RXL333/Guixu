import { createRouter, createWebHistory } from 'vue-router'
import NewTaskPage from './pages/NewTaskPage.vue'
import TaskScanPage from './pages/TaskScanPage.vue'
import ModelsPage from './pages/ModelsPage.vue'
import TaskTaxonomyPage from './pages/TaskTaxonomyPage.vue'
import TaskReviewPage from './pages/TaskReviewPage.vue'
import TaskRunPage from './pages/TaskRunPage.vue'
import TaskReportPage from './pages/TaskReportPage.vue'
import HistoryPage from './pages/HistoryPage.vue'
import SettingsPage from './pages/SettingsPage.vue'
import ConversationWorkspacePage from './pages/ConversationWorkspacePage.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    ...(import.meta.env.DEV ? [{ path: '/__ui-review', component: () => import('./dev/UiReviewPage.vue') }] : []),
    { path: '/', component: ConversationWorkspacePage },
    { path: '/conversations/:id', component: ConversationWorkspacePage },
    { path: '/tasks/new', component: NewTaskPage },
    { path: '/tasks/:id/analyze', component: TaskScanPage },
    { path: '/tasks/:id/taxonomy', component: TaskTaxonomyPage },
    { path: '/tasks/:id/review', component: TaskReviewPage },
    { path: '/tasks/:id/run', component: TaskRunPage },
    { path: '/tasks/:id/report', component: TaskReportPage },
    { path: '/templates', redirect: '/' },
    { path: '/history', component: HistoryPage },
    { path: '/trash', component: HistoryPage },
    { path: '/models', component: ModelsPage },
    { path: '/settings', component: SettingsPage },
  ],
})
