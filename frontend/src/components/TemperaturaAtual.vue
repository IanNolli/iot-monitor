<script setup lang="ts">
import { computed } from 'vue'
import type { Leitura } from '../types'
import { formatarHora, formatarTemperatura } from '../formatacao'

const props = defineProps<{ leitura: Leitura | null; carregando: boolean }>()

// Faixa de referência para ambiente residencial (o DHT22 mede de -40 a 80 °C)
const ESCALA_MIN = 0
const ESCALA_MAX = 40

const posicaoMarcador = computed(() => {
  if (!props.leitura) return 0
  const proporcao = (props.leitura.temperatura - ESCALA_MIN) / (ESCALA_MAX - ESCALA_MIN)
  return Math.min(Math.max(proporcao, 0), 1) * 100
})
</script>

<template>
  <section class="painel" aria-labelledby="titulo-atual">
    <h2 id="titulo-atual">Temperatura atual</h2>

    <template v-if="leitura">
      <p class="valor">
        {{ formatarTemperatura(leitura.temperatura) }}<span class="unidade">°C</span>
      </p>

      <div class="escala" aria-hidden="true">
        <div class="faixa">
          <span class="marcador" :style="{ left: `${posicaoMarcador}%` }"></span>
        </div>
        <div class="limites">
          <span>{{ ESCALA_MIN }} °C</span>
          <span>{{ ESCALA_MAX }} °C</span>
        </div>
      </div>

      <p class="horario">Última leitura às {{ formatarHora(leitura.timestamp) }}</p>
    </template>

    <p v-else class="vazio">
      {{ carregando ? 'Carregando…' : 'Aguardando a primeira leitura do sensor.' }}
    </p>
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
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  color: var(--tinta-suave);
}

.valor {
  margin: 0.25rem 0 1rem;
  font-size: clamp(3.5rem, 12vw, 5.5rem);
  font-weight: 300;
  line-height: 1;
  letter-spacing: -0.03em;
  font-variant-numeric: tabular-nums;
}

.unidade {
  font-size: 0.4em;
  font-weight: 400;
  margin-left: 0.15em;
  vertical-align: 0.9em;
  color: var(--tinta-suave);
}

.faixa {
  position: relative;
  height: 8px;
  border-radius: 4px;
  background: linear-gradient(90deg, #4f8fc7 0%, #7cc4b0 45%, #e3b64a 70%, #d9573b 100%);
}

.marcador {
  position: absolute;
  top: 50%;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--superficie);
  border: 3px solid var(--tinta);
  transform: translate(-50%, -50%);
  transition: left 0.6s ease;
}

.limites {
  display: flex;
  justify-content: space-between;
  margin-top: 0.4rem;
  font-size: 0.8rem;
  color: var(--tinta-suave);
}

.horario,
.vazio {
  margin: 1rem 0 0;
  color: var(--tinta-suave);
}

@media (prefers-reduced-motion: reduce) {
  .marcador {
    transition: none;
  }
}
</style>
