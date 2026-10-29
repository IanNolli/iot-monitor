<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ehAdmin, sair, sessao } from './sessao'
import { iniciarTempoReal, pararTempoReal, semDados, tempoReal } from './tempoReal'

const route = useRoute()
const router = useRouter()

const itens = computed(() => [
  { nome: 'dashboard', texto: 'Dashboard' },
  { nome: 'gemeo', texto: 'Gêmeo 3D' },
  { nome: 'insights', texto: 'Insights' },
  { nome: 'assistente', texto: 'Assistente' },
  { nome: 'laboratorio', texto: 'Laboratório' },
  { nome: 'treinamento', texto: 'Treinamento' },
  { nome: 'mensageria', texto: 'Mensageria' },
  { nome: 'dispositivos', texto: 'Dispositivos' },
  ...(ehAdmin.value ? [{ nome: 'administracao', texto: 'Administração' }] : []),
])

const ROTULO_PAPEL = { visualizador: 'Visualizador', operador: 'Operador', administrador: 'Administrador' }

// Liga o WebSocket enquanto houver sessão
watch(
  () => sessao.token,
  (token) => (token ? iniciarTempoReal() : pararTempoReal()),
  { immediate: true },
)

function encerrar() {
  sair()
  router.push({ name: 'login' })
}
</script>

<template>
  <RouterView v-if="route.meta.publica" />
  <div v-else class="moldura">
    <aside class="barra">
      <div class="marca">
        <strong>Smart Home AIoT</strong>
        <span>Monitoramento e manutenção preditiva</span>
      </div>
      <nav aria-label="Páginas">
        <RouterLink v-for="item in itens" :key="item.nome" :to="{ name: item.nome }">{{ item.texto }}</RouterLink>
      </nav>
      <div class="rodape-barra">
        <p class="conexao">
          <span class="selo" :class="!tempoReal.conectado ? 'critico' : semDados() ? 'sem_dados' : 'normal'">
            {{ !tempoReal.conectado ? 'WebSocket desconectado' : semDados() ? 'Sem dados do simulador' : 'Ao vivo' }}
          </span>
        </p>
        <p v-if="tempoReal.horaSimulada">Hora simulada: {{ tempoReal.horaSimulada }}</p>
        <p v-if="sessao.usuario">
          {{ sessao.usuario.nome }} · {{ ROTULO_PAPEL[sessao.usuario.papel] }}
        </p>
        <button class="secundario" @click="encerrar">Sair</button>
      </div>
    </aside>
    <main>
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.moldura {
  display: grid;
  grid-template-columns: 220px 1fr;
  min-height: 100vh;
}

.barra {
  background: var(--barra);
  color: var(--barra-tinta);
  padding: 1.25rem 0.9rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  position: sticky;
  top: 0;
  height: 100vh;
}

.marca {
  display: grid;
  padding: 0 0.35rem;
}

.marca strong {
  color: #fff;
  font-size: 1.05rem;
}

.marca span {
  font-size: 0.78rem;
  opacity: 0.75;
}

nav {
  display: grid;
  gap: 2px;
}

nav a {
  color: var(--barra-tinta);
  text-decoration: none;
  padding: 0.45rem 0.6rem;
  border-radius: 6px;
  font-size: 0.92rem;
}

nav a:hover {
  background: rgba(255, 255, 255, 0.06);
}

nav a.router-link-exact-active {
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
  font-weight: 600;
}

.rodape-barra {
  margin-top: auto;
  font-size: 0.8rem;
  display: grid;
  gap: 0.35rem;
}

.rodape-barra p {
  margin: 0;
}

.conexao .selo {
  background: rgba(255, 255, 255, 0.08);
}

.rodape-barra button {
  background: transparent;
  color: var(--barra-tinta);
  border-color: rgba(255, 255, 255, 0.25);
}

main {
  min-width: 0;
}

@media (max-width: 860px) {
  .moldura {
    grid-template-columns: 1fr;
  }

  .barra {
    position: static;
    height: auto;
    gap: 0.75rem;
  }

  nav {
    grid-auto-flow: column;
    overflow-x: auto;
  }

  nav a {
    white-space: nowrap;
  }

  .rodape-barra {
    grid-auto-flow: column;
    align-items: center;
    justify-content: start;
    gap: 0.75rem;
  }
}
</style>
