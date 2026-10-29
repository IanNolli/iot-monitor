<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import Grafico from '../components/Grafico.vue'
import { enviar, get } from '../api'
import { dataHora, hora, inteiro } from '../formatacao'
import { ehAdmin } from '../sessao'
import { tempoReal } from '../tempoReal'
import type { Job } from '../tipos'

const LEITURAS_POR_DIA = 288 // uma leitura a cada 5 minutos simulados
const TETO = 20_000_000
const MINIMO = 1_000_000

const parametros = reactive({
  equipamentos: 60,
  dias: 60,
  sensores: { vibracao: 1, corrente: 1, temperatura: 1 },
  pct_falha: 50,
  modos_falha: ['rolamento', 'entupimento', 'superaquecimento', 'desbalanceamento'],
  falhas_sensor: ['deriva', 'travamento'],
  pct_falha_sensor: 10,
  ruido: 1,
  pct_faltantes: 1,
  pct_outliers: 0.5,
  semente: 42,
})

const MODOS = [
  { id: 'rolamento', texto: 'Desgaste de rolamento' },
  { id: 'entupimento', texto: 'Entupimento' },
  { id: 'superaquecimento', texto: 'Superaquecimento' },
  { id: 'desbalanceamento', texto: 'Desbalanceamento' },
]

const leiturasEstimadas = computed(
  () =>
    parametros.equipamentos *
    parametros.dias *
    LEITURAS_POR_DIA *
    (parametros.sensores.vibracao + parametros.sensores.corrente + parametros.sensores.temperatura),
)

const jobs = ref<Job[]>([])
const resumo = ref<{ dataset: any; pontos_bucket_lab: number } | null>(null)
const amostra = ref<{ equipamentos: string[]; equipamento: string | null; serie: Record<string, [string, number][]> }>({
  equipamentos: [],
  equipamento: null,
  serie: {},
})
const equipamentoAmostra = ref<string | null>(null)
const erro = ref('')
const enviando = ref(false)

async function carregar() {
  try {
    jobs.value = await get<Job[]>('/api/lab/jobs?tipo=geracao')
    resumo.value = await get('/api/lab/resumo')
  } catch (e) {
    erro.value = (e as Error).message
  }
}

async function carregarAmostra() {
  const q = equipamentoAmostra.value ? `?equipamento=${equipamentoAmostra.value}` : ''
  amostra.value = await get(`/api/lab/amostra${q}`)
  equipamentoAmostra.value = amostra.value.equipamento
}

async function gerar() {
  enviando.value = true
  erro.value = ''
  try {
    await enviar('POST', '/api/lab/gerar', parametros)
    await carregar()
  } catch (e) {
    erro.value = (e as Error).message
  } finally {
    enviando.value = false
  }
}

// progresso ao vivo pelo WebSocket sobrepõe o que veio da API
function progressoDe(job: Job) {
  const vivo = tempoReal.jobs[job.id]
  return vivo ? { status: vivo.status, progresso: vivo.progresso, mensagem: vivo.mensagem } : job
}

const ROTULO: Record<string, string> = { na_fila: 'Na fila', executando: 'Executando', concluido: 'Concluído', erro: 'Erro' }

// quando um job termina, recarrega a lista e a amostra
watch(
  () => Object.values(tempoReal.jobs).filter((j) => j.tipo === 'geracao' && j.status === 'concluido').length,
  () => {
    carregar()
    carregarAmostra()
  },
)

const dadosAmostra = computed(() => {
  const s = amostra.value.serie
  const base = s.vibracao ?? []
  const cores: Record<string, string> = { vibracao: '#d1453a', corrente: '#c98a12', temperatura: '#2a7a8c', saude: '#2f9e6e' }
  return {
    labels: base.map(([t]) => new Date(t).toLocaleDateString('pt-BR')),
    datasets: Object.entries(s).map(([campo, pontos]) => ({
      label: campo === 'saude' ? 'saúde (rótulo)' : campo,
      data: pontos.map(([, v]) => v),
      borderColor: cores[campo],
      backgroundColor: cores[campo],
      borderWidth: 1.5,
      pointRadius: 0,
      yAxisID: campo === 'saude' || campo === 'temperatura' ? 'y1' : 'y',
    })),
  }
})
const opcoesAmostra = {
  plugins: { legend: { display: true, position: 'bottom' as const } },
  scales: {
    y: { title: { display: true, text: 'vibração · corrente' }, grid: { color: '#e4ebef' } },
    y1: { position: 'right' as const, title: { display: true, text: 'temperatura · saúde' }, grid: { display: false } },
  },
}

let temporizador: number | undefined
onMounted(() => {
  carregar()
  carregarAmostra()
  temporizador = window.setInterval(carregar, 5000)
})
onUnmounted(() => window.clearInterval(temporizador))
</script>

<template>
  <div class="pagina">
    <header class="cabecalho-pagina">
      <div>
        <h1>Laboratório de Dados</h1>
        <p>Simula a vida inteira de vários compressores para treinar a IA. O job roda em segundo plano, por fila do RabbitMQ.</p>
      </div>
    </header>

    <section class="painel">
      <h2>Configuração da geração</h2>
      <div class="campos">
        <label>Equipamentos <input v-model.number="parametros.equipamentos" type="number" min="1" max="500" /></label>
        <label>Período simulado (dias) <input v-model.number="parametros.dias" type="number" min="1" max="365" /></label>
        <label>Sensores de vibração por equipamento <input v-model.number="parametros.sensores.vibracao" type="number" min="1" max="3" /></label>
        <label>Sensores de corrente por equipamento <input v-model.number="parametros.sensores.corrente" type="number" min="1" max="3" /></label>
        <label>Sensores de temperatura por equipamento <input v-model.number="parametros.sensores.temperatura" type="number" min="1" max="3" /></label>
        <label>Equipamentos que falham (%) <input v-model.number="parametros.pct_falha" type="number" min="0" max="100" /></label>
        <label>Nível de ruído (0 a 3) <input v-model.number="parametros.ruido" type="number" min="0" max="3" step="0.1" /></label>
        <label>Leituras faltantes (%) <input v-model.number="parametros.pct_faltantes" type="number" min="0" max="20" step="0.1" /></label>
        <label>Valores absurdos (%) <input v-model.number="parametros.pct_outliers" type="number" min="0" max="10" step="0.1" /></label>
        <label>Sensores com defeito (%) <input v-model.number="parametros.pct_falha_sensor" type="number" min="0" max="100" /></label>
        <label>Semente aleatória <input v-model.number="parametros.semente" type="number" /></label>
      </div>
      <fieldset>
        <legend>Modos de falha do equipamento</legend>
        <label v-for="m in MODOS" :key="m.id" class="opcao">
          <input v-model="parametros.modos_falha" type="checkbox" :value="m.id" /> {{ m.texto }}
        </label>
      </fieldset>
      <fieldset>
        <legend>Defeitos de sensor</legend>
        <label class="opcao"><input v-model="parametros.falhas_sensor" type="checkbox" value="deriva" /> Deriva lenta</label>
        <label class="opcao"><input v-model="parametros.falhas_sensor" type="checkbox" value="travamento" /> Sensor travado</label>
      </fieldset>
      <p :class="leiturasEstimadas > TETO ? 'aviso erro' : leiturasEstimadas < MINIMO ? 'aviso' : 'suave'">
        {{ inteiro(leiturasEstimadas) }} leituras ({{ inteiro(parametros.equipamentos * parametros.dias * LEITURAS_POR_DIA) }} instantes de
        {{ inteiro(parametros.equipamentos) }} equipamentos).
        <template v-if="leiturasEstimadas > TETO"> Acima do teto de {{ inteiro(TETO) }}: reduza os parâmetros.</template>
        <template v-else-if="leiturasEstimadas < MINIMO"> O trabalho pede pelo menos 1 milhão de leituras.</template>
      </p>
      <div class="acoes">
        <button :disabled="!ehAdmin || enviando || leiturasEstimadas > TETO || !parametros.modos_falha.length" @click="gerar">
          Gerar dados sintéticos
        </button>
        <span v-if="!ehAdmin" class="suave">Só administradores geram dados.</span>
      </div>
      <p v-if="erro" class="aviso erro">{{ erro }}</p>
    </section>

    <div class="grade-2">
      <section class="painel">
        <h2>Jobs de geração</h2>
        <p v-if="!jobs.length" class="suave">Nenhum job ainda.</p>
        <div v-for="j in jobs" :key="j.id" class="job">
          <div class="linha-job">
            <span class="selo" :class="progressoDe(j).status">{{ ROTULO[progressoDe(j).status] ?? progressoDe(j).status }}</span>
            <span class="suave">{{ dataHora(j.criado_em) }} · {{ j.criado_por }}</span>
          </div>
          <div class="barra-progresso"><div :style="{ width: `${progressoDe(j).progresso}%` }"></div></div>
          <p class="suave">{{ progressoDe(j).mensagem }}</p>
        </div>
      </section>

      <section class="painel">
        <h2>Último dataset</h2>
        <template v-if="resumo?.dataset">
          <dl>
            <dt>Leituras</dt>
            <dd>{{ inteiro(resumo.dataset.leituras) }}</dd>
            <dt>Instantes por equipamento</dt>
            <dd>{{ inteiro(resumo.dataset.linhas / resumo.dataset.parametros.equipamentos) }}</dd>
            <dt>Equipamentos com falha</dt>
            <dd>{{ resumo.dataset.equipamentos_com_falha }} de {{ resumo.dataset.parametros.equipamentos }}</dd>
            <dt>Tempo de geração</dt>
            <dd>{{ resumo.dataset.segundos }} s</dd>
            <dt>Pontos no bucket <code>lab</code></dt>
            <dd>{{ inteiro(resumo.pontos_bucket_lab) }}</dd>
          </dl>
        </template>
        <p v-else class="suave">Gere um dataset para ver o resumo.</p>
      </section>
    </div>

    <section class="painel">
      <div class="cabecalho-grafico">
        <h2>Amostra no InfluxDB (bucket <code>lab</code>, separado dos dados ao vivo)</h2>
        <select v-if="amostra.equipamentos.length" v-model="equipamentoAmostra" aria-label="Equipamento da amostra" @change="carregarAmostra">
          <option v-for="e in amostra.equipamentos" :key="e" :value="e">{{ e }}</option>
        </select>
      </div>
      <p v-if="!amostra.equipamentos.length" class="suave">Sem amostra ainda.</p>
      <Grafico v-else :dados="dadosAmostra" :opcoes="opcoesAmostra" :altura="260" rotulo="Amostra dos dados sintéticos ao longo dos dias simulados" />
      <p class="suave">
        A degradação é progressiva: antes da falha, vibração, corrente e temperatura sobem aos poucos, com ruído. Os rótulos de saúde e vida útil
        existem só nestes dados de treino e nunca vão na telemetria ao vivo. Atualizado às {{ hora(tempoReal.agora) }}.
      </p>
    </section>
  </div>
</template>

<style scoped>
fieldset {
  border: 1px solid var(--borda);
  border-radius: 6px;
  margin: 0.9rem 0 0;
  padding: 0.5rem 0.8rem 0.7rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem 1.25rem;
}

legend {
  font-size: 0.85rem;
  color: var(--tinta-suave);
  padding: 0 0.3rem;
}

label.opcao {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  color: var(--tinta);
}

label.opcao input {
  width: auto;
}

section > p {
  margin-top: 0.9rem;
}

.job {
  display: grid;
  gap: 0.3rem;
  padding: 0.6rem 0;
  border-bottom: 1px solid var(--borda);
}

.job p {
  margin: 0;
}

.linha-job {
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
  flex-wrap: wrap;
}

dl {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0.3rem 1rem;
  margin: 0;
}

dt {
  color: var(--tinta-suave);
}

dd {
  margin: 0;
  font-variant-numeric: tabular-nums;
}

.cabecalho-grafico {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.5rem;
}

.cabecalho-grafico select {
  width: auto;
}
</style>
