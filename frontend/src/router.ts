import { createRouter, createWebHistory } from 'vue-router'
import { refreshSession, session } from './session'
import CalendarView from './views/CalendarView.vue'
import CourseView from './views/CourseView.vue'
import HomeView from './views/HomeView.vue'
import LoginView from './views/LoginView.vue'
import RegisterView from './views/RegisterView.vue'
import SettingsView from './views/SettingsView.vue'
import SetupView from './views/SetupView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: LoginView,
      meta: { public: true, title: '登录' },
    },
    {
      path: '/register',
      name: 'register',
      component: RegisterView,
      meta: { public: true, title: '注册' },
    },
    { path: '/setup', name: 'setup', component: SetupView, meta: { title: '家庭' } },
    {
      path: '/',
      name: 'home',
      component: HomeView,
      meta: { title: '首页', tabs: true },
    },
    {
      path: '/calendar',
      name: 'calendar',
      component: CalendarView,
      meta: { title: '日历', tabs: true },
    },
    {
      path: '/settings',
      name: 'settings',
      component: SettingsView,
      meta: { title: '设置', tabs: true },
    },
    {
      path: '/courses/new',
      name: 'course-new',
      component: CourseView,
      meta: { title: '添加课程', tabs: true },
    },
    {
      path: '/courses/:id',
      name: 'course',
      component: CourseView,
      meta: { title: '课程', tabs: true },
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  if (!session.ready) {
    await refreshSession()
  }
  const loggedIn = session.user !== null
  const hasFamily = session.family !== null
  if (to.meta.public && loggedIn && hasFamily) {
    return { name: 'home' }
  }
  if (!to.meta.public && !loggedIn) {
    return { name: 'login' }
  }
  if (!to.meta.public && loggedIn && !hasFamily && to.name !== 'setup') {
    return { name: 'setup' }
  }
  if (to.name === 'setup' && hasFamily) {
    return { name: 'home' }
  }
  return true
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${String(to.meta.title)} · 悠悠课程本` : '悠悠课程本'
})

export default router
