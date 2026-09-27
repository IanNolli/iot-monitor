<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import TemperaturaAtual from './components/TemperaturaAtual.vue'
import GraficoHistorico from './components/GraficoHistorico.vue'
import { buscarAtual, buscarHistorico } from './services/api'
import type { Leitura } from './types'

const INTERVALO_MS = 5000 // mesmo intervalo de publicação do sensor

const atual = ref<Leitura | null>(null)
const historico = ref<Leitura[]>([])
const carregando = ref(true)
const erro = ref<string | null>(null)
let temporizador: number | undefined

async function atualizar() {
  try {
    const [leituraAtual, leituras] = await Promise.all([buscarAtual(), buscarHistorico()])
    atual.value = leituraAtual
    historico.value = leituras
    erro.value = null
  } catch {
    erro.value = 'Não foi possível consultar a API. Verifique se o backend Python está em execução.'
  } finally {
    carregando.value = false
  }
}

onMounted(() => {
  atualizar()
  temporizador = window.setInterval(atualizar, INTERVALO_MS)
})

onUnmounted(() => window.clearInterval(temporizador))
</script>

<template>
  <main class="pagina">
    <header>
      <h1>Monitoramento Residencial</h1>
      <p class="subtitulo">Temperatura do ambiente medida pelo sensor DHT22</p>
    </header>

    <p v-if="erro" class="alerta" role="alert">{{ erro }}</p>

    <TemperaturaAtual :leitura="atual" :carregando="carregando" />
    <GraficoHistorico :leituras="historico" />
  </main>
</template>

<style scoped>
.pagina {
  max-width: 760px;
  margin: 0 auto;
  padding: 2.5rem 1.25rem 3rem;
  display: grid;
  gap: 1.5rem;
}

h1 {
  margin: 0;
  font-size: 1.75rem;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.subtitulo {
  margin: 0.25rem 0 0;
  color: var(--tinta-suave);
}

.alerta {
  margin: 0;
  padding: 0.75rem 1rem;
  border-radius: 6px;
  background: var(--alerta-fundo);
  color: var(--alerta-tinta);
}
</style>
