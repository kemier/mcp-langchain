import { createRouter, createWebHistory } from 'vue-router';
import ServerManagementView from '../views/ServerManagementView.vue';
import ServerControlsDashboard from '../views/ServerControlsDashboard.vue';
import ServerConfigDashboard from '../views/ServerConfigDashboard.vue';
import ServerConfigFormView from '../views/ServerConfigFormView.vue';
import LLMManagementView from '../views/LLMManagementView.vue';

const routes = [
  {
    path: '/',
    redirect: '/chat' // Redirect to chat page
  },
  {
    path: '/chat',    // Changed path from /servers
    name: 'ChatView', // Changed name from ServerManagement
    component: ServerManagementView,
  },
  {
    path: '/server-controls',
    name: 'ServerControlsDashboard',
    component: ServerControlsDashboard,
  },
  {
    path: '/server-configs',
    name: 'ServerConfigDashboard',
    component: ServerConfigDashboard,
  },
  {
    path: '/server-configs/new',
    name: 'CreateServerConfig',
    component: ServerConfigFormView,
  },
  {
    path: '/server-configs/edit/:serverName',
    name: 'EditServerConfig',
    component: ServerConfigFormView,
    props: true
  },
  {
    path: '/settings/llm-management',
    name: 'LLMManagement',
    component: LLMManagementView,
  }
];

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
});

export default router; 