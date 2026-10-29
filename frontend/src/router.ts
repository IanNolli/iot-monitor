import { createRouter, createWebHistory } from 'vue-router'
import { pode, sessao } from './sessao'
import type { Papel } from './tipos'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('./views/Login.vue'), meta: { publica: true } },
    { path: '/', name: 'dashboard', component: () => import('./views/Dashboard.vue'), meta: { titulo: 'Dashboard' } },
    { path: '/gemeo', name: 'gemeo', component: () => import('./views/Gemeo3D.vue'), meta: { titulo: 'Gêmeo digital 3D' } },
    { path: '/insights', name: 'insights', component: () => import('./views/Insights.vue'), meta: { titulo: 'Insights' } },
    { path: '/assistente', name: 'assistente', component: () => import('./views/Assistente.vue'), meta: { titulo: 'Assistente' } },
    { path: '/laboratorio', name: 'laboratorio', component: () => import('./views/Laboratorio.vue'), meta: { titulo: 'Laboratório de Dados' } },
    { path: '/treinamento', name: 'treinamento', component: () => import('./views/Treinamento.vue'), meta: { titulo: 'Treinamento' } },
    { path: '/mensageria', name: 'mensageria', component: () => import('./views/Mensageria.vue'), meta: { titulo: 'Mensageria' } },
    { path: '/dispositivos', name: 'dispositivos', component: () => import('./views/Dispositivos.vue'), meta: { titulo: 'Dispositivos e regras' } },
    {
      path: '/administracao',
      name: 'administracao',
      component: () => import('./views/Administracao.vue'),
      meta: { titulo: 'Administração', papel: 'administrador' },
    },
    { path: '/:caminho(.*)*', redirect: '/' },
  ],
})

router.beforeEach((destino) => {
  if (destino.meta.publica) return true
  if (!sessao.token) return { name: 'login', query: { volta: destino.fullPath } }
  const papel = destino.meta.papel as Papel | undefined
  if (papel && !pode(papel)) return { name: 'dashboard' }
  return true
})

router.afterEach((destino) => {
  document.title = destino.meta.titulo ? `${destino.meta.titulo} · Smart Home AIoT` : 'Smart Home AIoT'
})

export default router
