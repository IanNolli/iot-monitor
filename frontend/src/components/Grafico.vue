<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  Filler,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  ScatterController,
  Tooltip,
  type ChartData,
  type ChartOptions,
  type ChartType,
} from 'chart.js'

Chart.register(
  LineController, LineElement, PointElement, BarController, BarElement, ScatterController,
  LinearScale, CategoryScale, Tooltip, Legend, Filler,
)
Chart.defaults.font.family = getComputedStyle(document.documentElement).fontFamily
Chart.defaults.color = '#587180'

const props = withDefaults(
  defineProps<{ tipo?: ChartType; dados: ChartData; opcoes?: ChartOptions; altura?: number; rotulo: string }>(),
  { tipo: 'line', altura: 240 },
)

const canvas = ref<HTMLCanvasElement | null>(null)
let grafico: Chart | null = null

const PADRAO: ChartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  animation: false,
  interaction: { mode: 'nearest', intersect: false },
  plugins: { legend: { display: false } },
  scales: {
    x: { ticks: { maxTicksLimit: 6, maxRotation: 0 }, grid: { display: false } },
    y: { grid: { color: '#e4ebef' } },
  },
}

onMounted(() => {
  grafico = new Chart(canvas.value!, {
    type: props.tipo,
    data: props.dados,
    options: { ...PADRAO, ...props.opcoes, scales: { ...PADRAO.scales, ...(props.opcoes?.scales ?? {}) } } as ChartOptions,
  })
})

watch(
  () => props.dados,
  (dados) => {
    if (!grafico) return
    grafico.data = dados
    grafico.update('none')
  },
  { deep: true },
)

onBeforeUnmount(() => grafico?.destroy())
</script>

<template>
  <div class="area" :style="{ height: `${altura}px` }">
    <canvas ref="canvas" role="img" :aria-label="rotulo"></canvas>
  </div>
</template>

<style scoped>
.area {
  position: relative;
}
</style>
