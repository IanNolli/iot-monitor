<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  CategoryScale,
  Chart,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  Tooltip,
} from 'chart.js'
import type { Leitura } from '../types'
import { formatarHora } from '../formatacao'

Chart.register(LineController, LineElement, PointElement, LinearScale, CategoryScale, Tooltip)

const props = defineProps<{ leituras: Leitura[] }>()

const canvas = ref<HTMLCanvasElement | null>(null)
// Fora do sistema reativo do Vue: o Chart.js não funciona bem com objetos proxy
let grafico: Chart<'line', number[], string> | null = null

function rotulos(leituras: Leitura[]): string[] {
  return leituras.map((l) => formatarHora(l.timestamp))
}

function valores(leituras: Leitura[]): number[] {
  return leituras.map((l) => l.temperatura)
}

onMounted(() => {
  if (!canvas.value) return
  grafico = new Chart(canvas.value, {
    type: 'line',
    data: {
      labels: rotulos(props.leituras),
      datasets: [
        {
          label: 'Temperatura (°C)',
          data: valores(props.leituras),
          borderColor: '#2a7a8c',
          backgroundColor: '#2a7a8c',
          borderWidth: 2,
          pointRadius: 2,
          tension: 0.3,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { maxTicksLimit: 6, color: '#587180' }, grid: { display: false } },
        y: {
          title: { display: true, text: '°C', color: '#587180' },
          ticks: { color: '#587180' },
          grid: { color: '#e4ebef' },
        },
      },
    },
  })
})

watch(
  () => props.leituras,
  (leituras) => {
    if (!grafico) return
    grafico.data.labels = rotulos(leituras)
    grafico.data.datasets[0]!.data = valores(leituras)
    grafico.update()
  },
)

onBeforeUnmount(() => grafico?.destroy())
</script>

<template>
  <section class="painel" aria-labelledby="titulo-historico">
    <h2 id="titulo-historico">Histórico da última hora</h2>
    <p v-if="leituras.length === 0" class="vazio">
      O gráfico aparece assim que houver leituras gravadas na última hora.
    </p>
    <!-- v-show mantém o canvas montado para o Chart.js -->
    <div v-show="leituras.length > 0" class="area-grafico">
      <canvas ref="canvas" role="img" aria-label="Gráfico de linha com o histórico de temperatura"></canvas>
    </div>
  </section>
</template>

<style scoped>
.painel {
  background: var(--superficie);
  border: 1px solid var(--borda);
  border-radius: 10px;
  padding: 1.5rem;
}

h2 {
  margin: 0 0 1rem;
  font-size: 1rem;
  font-weight: 600;
  color: var(--tinta-suave);
}

.area-grafico {
  position: relative;
  height: 280px;
}

.vazio {
  margin: 0;
  color: var(--tinta-suave);
}
</style>
