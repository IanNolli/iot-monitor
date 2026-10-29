<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import Grafico from '../components/Grafico.vue'
import { Casa3D } from '../cena/casa3d'
import { enviar } from '../api'
import { hora, numero } from '../formatacao'
import { ehOperador } from '../sessao'
import { dispositivo, ROTULO_STATUS, semDados, statusDe, tempoReal } from '../tempoReal'

const recipiente = ref<HTMLElement | null>(null)
const cena = shallowRef<Casa3D | null>(null)
const selecionado = ref<string | null>(null)
const erro = ref('')
const enviando = ref(false)
const suporteWebGL = ref(true)

onMounted(() => {
  try {
    cena.value = new Casa3D(recipiente.value!, (id) => (selecionado.value = id))
  } catch {
    suporteWebGL.value = false
  }
})
onBeforeUnmount(() => cena.value?.destruir())

const item = computed(() => (selecionado.value ? dispositivo(selecionado.value) : undefined))
const leitura = computed(() => (selecionado.value ? tempoReal.leituras[selecionado.value] : undefined))
const previsao = computed(() => (selecionado.value ? tempoReal.previsoes[selecionado.value] : undefined))

const camposLeitura = computed(() =>
  Object.entries(leitura.value?.conteudo ?? {}).filter(([k, v]) => !['zona', 'classe', 'unidade'].includes(k) && v !== null),
)

const CORES = ['#2a7a8c', '#c98a12', '#d1453a']
const miniGrafico = computed(() => {
  const series = selecionado.value ? tempoReal.series[selecionado.value] ?? {} : {}
  const campos = Object.keys(series)
  const base = series[campos[0]] ?? []
  return {
    labels: base.map((p) => hora(p.t)),
    datasets: campos.map((c, i) => ({
      label: c,
      data: series[c].map((p) => p.v),
      borderColor: CORES[i % 3],
      borderWidth: 2,
      pointRadius: 0,
      stepped: c === 'ligado',
    })),
  }
})

async function comandar(ligado: boolean) {
  if (!selecionado.value) return
  enviando.value = true
  erro.value = ''
  try {
    await enviar('POST', `/api/dispositivos/${selecionado.value}/comando`, { ligado })
  } catch (e) {
    erro.value = (e as Error).message
  } finally {
    enviando.value = false
  }
}

function formatar(campo: string, valor: unknown): string {
  if (typeof valor === 'boolean') return valor ? 'ligado' : 'desligado'
  if (campo === 'valor' && item.value?.grandeza === 'presenca') return valor ? 'alguém presente' : 'ninguém'
  const unidades: Record<string, string> = { vibracao: 'mm/s', corrente: 'A', temperatura: '°C' }
  return `${numero(valor, campo === 'valor' && item.value?.grandeza === 'luminosidade' ? 0 : 2)} ${unidades[campo] ?? item.value?.unidade ?? ''}`
}
</script>

<template>
  <div class="pagina">
    <header class="cabecalho-pagina">
      <div>
        <h1>Gêmeo digital 3D</h1>
        <p>A cena se move só com os dados que chegam pelo WebSocket. Clique em um item para ver detalhes.</p>
      </div>
      <div class="legenda" aria-label="Legenda de cores">
        <span class="selo normal">Normal</span>
        <span class="selo atencao">Atenção</span>
        <span class="selo critico">Crítico</span>
        <span class="selo sem_dados">Sem dados</span>
      </div>
    </header>

    <div class="layout">
      <div class="palco painel">
        <div ref="recipiente" class="tela3d"></div>
        <div v-if="semDados()" class="sobreposicao" role="status">
          <strong>Sem dados em tempo real</strong>
          <span>A cena está parada até o simulador voltar a enviar telemetria.</span>
        </div>
        <p v-if="!suporteWebGL" class="aviso erro">Este navegador não suporta WebGL.</p>
        <p class="dica suave">Arraste para girar · role para aproximar</p>
      </div>

      <aside class="painel detalhe">
        <template v-if="item">
          <h2>{{ item.nome }}</h2>
          <p>
            <span class="selo" :class="statusDe(item.id)">{{ ROTULO_STATUS[statusDe(item.id)] }}</span>
            <span class="suave"> · {{ item.classe }} · {{ item.zona }}</span>
          </p>
          <dl>
            <template v-for="[campo, valor] in camposLeitura" :key="campo">
              <dt>{{ campo === 'valor' ? item.grandeza : campo }}</dt>
              <dd>{{ formatar(campo, valor) }}</dd>
            </template>
            <template v-if="leitura">
              <dt>última leitura</dt>
              <dd>{{ hora(leitura.instante) }}</dd>
            </template>
          </dl>
          <p v-if="!leitura" class="suave">Nenhuma leitura recebida deste dispositivo.</p>

          <div v-if="item.classe === 'equipamento'" class="ia">
            <h3>Saúde prevista pela IA</h3>
            <template v-if="previsao">
              <p class="grande">{{ numero(previsao.saude, 0) }}<small>/100</small></p>
              <p class="suave">
                Vida útil restante ~{{ numero(previsao.vida_util_h, 0) }} h · tendência {{ numero(previsao.tendencia_saude_h, 1) }} pts/h ·
                modelo v{{ previsao.versao_modelo }}
              </p>
            </template>
            <p v-else class="suave">Sem previsão: treine os modelos na página Treinamento.</p>
          </div>

          <Grafico v-if="miniGrafico.datasets.length" :dados="miniGrafico" :altura="150" rotulo="Mini gráfico das últimas leituras" />

          <div v-if="item.classe === 'atuador'" class="comandos">
            <template v-if="item.controlavel">
              <h3>Comando</h3>
              <div class="acoes">
                <button :disabled="!ehOperador || enviando" @click="comandar(true)">Ligar</button>
                <button class="secundario" :disabled="!ehOperador || enviando" @click="comandar(false)">Desligar</button>
              </div>
              <p v-if="!ehOperador" class="suave">Só operadores e administradores enviam comandos.</p>
            </template>
            <p v-else class="suave">Acionado automaticamente pela regra de temperatura.</p>
            <p v-if="erro" class="aviso erro">{{ erro }}</p>
          </div>
        </template>
        <template v-else>
          <h2>Nenhum item selecionado</h2>
          <p class="suave">Clique em um sensor, atuador ou no compressor da geladeira para ver a última leitura, um mini gráfico e os comandos.</p>
          <ul class="suave lista">
            <li>Janela e luz do ambiente seguem a luminosidade medida (dia e noite).</li>
            <li>A pessoa aparece quando o sensor de presença detecta alguém.</li>
            <li>O ventilador gira e a lâmpada acende quando ligados.</li>
            <li>O compressor treme mais quanto maior a vibração.</li>
          </ul>
        </template>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 1rem;
}

.palco {
  position: relative;
  padding: 0;
  overflow: hidden;
}

.tela3d {
  height: min(70vh, 640px);
  min-height: 360px;
}

.sobreposicao {
  position: absolute;
  inset: 0;
  display: grid;
  place-content: center;
  text-align: center;
  gap: 0.25rem;
  background: rgba(14, 31, 39, 0.55);
  color: #fff;
}

.dica {
  position: absolute;
  bottom: 0.4rem;
  left: 0.75rem;
  margin: 0;
  color: #dbe7ec;
}

.legenda {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.detalhe {
  display: grid;
  gap: 0.6rem;
  align-content: start;
}

.detalhe h2,
.detalhe p {
  margin: 0;
}

dl {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0.2rem 0.75rem;
  margin: 0;
  font-size: 0.9rem;
}

dt {
  color: var(--tinta-suave);
}

dd {
  margin: 0;
  font-variant-numeric: tabular-nums;
}

.grande {
  font-size: 2rem;
  font-weight: 300;
  line-height: 1;
}

.grande small {
  font-size: 0.5em;
  color: var(--tinta-suave);
}

.lista {
  margin: 0;
  padding-left: 1.1rem;
}

@media (max-width: 1000px) {
  .layout {
    grid-template-columns: 1fr;
  }
}
</style>
