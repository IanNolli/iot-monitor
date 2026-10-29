<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import Grafico from '../components/Grafico.vue'
import { enviar, get } from '../api'
import { dataHora, inteiro, numero } from '../formatacao'
import { ehAdmin } from '../sessao'
import { tempoReal } from '../tempoReal'
import type { Job } from '../tipos'

interface MetricasModelo {
  descricao: string
  algoritmo: string
  teste: { mae: number; rmse: number; r2: number }
  validacao: { mae: number; rmse: number; r2: number }
  base_media: { mae: number; rmse: number; r2: number }
  vence_base: boolean
  importancia: { atributo: string; importancia: number }[]
  previsto_vs_real: [number, number][]
}
interface Resultado {
  versao: number
  em_uso: boolean
  segundos: number
  amostras_treino: number
  equipamentos: Record<string, number>
  modelos: Record<string, MetricasModelo>
}

const parametros = reactive({ amostras_treino: 200_000, semente: 7 })
const jobs = ref<Job[]>([])
const versaoEmUso = ref<number | null>(null)
const versaoSelecionada = ref<number | null>(null)
const erro = ref('')
const enviando = ref(false)

const ROTULO: Record<string, string> = { na_fila: 'Na fila', executando: 'Executando', concluido: 'Concluído', erro: 'Erro' }

async function carregar() {
  try {
    jobs.value = await get<Job[]>('/api/lab/jobs?tipo=treino')
    const modelos = await get<{ versao: number; em_uso: boolean }[]>('/api/modelos')
    versaoEmUso.value = modelos.find((m) => m.em_uso)?.versao ?? null
    if (versaoSelecionada.value === null) versaoSelecionada.value = resultados.value[0]?.versao ?? null
  } catch (e) {
    erro.value = (e as Error).message
  }
}

const resultados = computed<Resultado[]>(() =>
  jobs.value.filter((j) => j.status === 'concluido' && j.resultado?.modelos).map((j) => j.resultado as Resultado),
)
const resultado = computed(() => resultados.value.find((r) => r.versao === versaoSelecionada.value) ?? resultados.value[0])

async function treinar() {
  enviando.value = true
  erro.value = ''
  try {
    await enviar('POST', '/api/modelos/treinar', parametros)
    await carregar()
  } catch (e) {
    erro.value = (e as Error).message
  } finally {
    enviando.value = false
  }
}

function progressoDe(job: Job) {
  const vivo = tempoReal.jobs[job.id]
  return vivo ? { status: vivo.status, progresso: vivo.progresso, mensagem: vivo.mensagem } : job
}

watch(
  () => Object.values(tempoReal.jobs).filter((j) => j.tipo === 'treino' && (j.status === 'concluido' || j.status === 'erro')).length,
  async () => {
    versaoSelecionada.value = null
    await carregar()
  },
)

function dispersao(m: MetricasModelo) {
  const pontos = m.previsto_vs_real.map(([real, prev]) => ({ x: real, y: prev }))
  const max = Math.max(1, ...m.previsto_vs_real.flat())
  return {
    datasets: [
      { label: 'previsões', data: pontos, backgroundColor: 'rgba(42,122,140,.45)', pointRadius: 2.5 },
      { label: 'ideal (previsto = real)', data: [{ x: 0, y: 0 }, { x: max, y: max }], type: 'line' as const, showLine: true, borderColor: '#d1453a', borderDash: [5, 4], borderWidth: 1.5, pointRadius: 0 },
    ],
  }
}
const opcoesDispersao = {
  plugins: { legend: { display: true, position: 'bottom' as const } },
  scales: {
    x: { type: 'linear' as const, title: { display: true, text: 'valor real' }, grid: { display: false } },
    y: { title: { display: true, text: 'valor previsto' }, grid: { color: '#e4ebef' } },
  },
}

function importancia(m: MetricasModelo) {
  return {
    labels: m.importancia.map((i) => i.atributo),
    datasets: [{ label: 'importância (aumento do MAE ao embaralhar)', data: m.importancia.map((i) => i.importancia), backgroundColor: '#2a7a8c' }],
  }
}
const opcoesImportancia = { indexAxis: 'y' as const, scales: { x: { grid: { color: '#e4ebef' } }, y: { grid: { display: false } } } }

let temporizador: number | undefined
onMounted(() => {
  carregar()
  temporizador = window.setInterval(carregar, 6000)
})
onUnmounted(() => window.clearInterval(temporizador))
</script>

<template>
  <div class="pagina">
    <header class="cabecalho-pagina">
      <div>
        <h1>Treinamento</h1>
        <p>Dois modelos de regressão treinados com os dados sintéticos e comparados com uma base simples (prever sempre a média).</p>
      </div>
      <span class="selo" :class="versaoEmUso ? 'normal' : 'atencao'">{{ versaoEmUso ? `Versão em uso: v${versaoEmUso}` : 'Nenhum modelo em uso' }}</span>
    </header>

    <section class="painel">
      <h2>Novo treino</h2>
      <div class="campos">
        <label>Amostras de treino <input v-model.number="parametros.amostras_treino" type="number" min="10000" max="1000000" step="10000" /></label>
        <label>Semente aleatória <input v-model.number="parametros.semente" type="number" /></label>
      </div>
      <p class="suave" style="margin-top: 0.75rem">
        Divisão em treino, validação e teste por equipamento (70/15/15). As features vêm do mesmo código usado na inferência ao vivo. O modelo novo
        só entra em uso se vencer a base, e a troca acontece sem reiniciar o serviço de inferência.
      </p>
      <div class="acoes">
        <button :disabled="!ehAdmin || enviando" @click="treinar">Treinar modelos</button>
        <span v-if="!ehAdmin" class="suave">Só administradores treinam modelos.</span>
      </div>
      <p v-if="erro" class="aviso erro" style="margin-top: 0.75rem">{{ erro }}</p>
      <div v-for="j in jobs.filter((x) => progressoDe(x).status !== 'concluido').slice(0, 3)" :key="j.id" class="job">
        <span class="selo" :class="progressoDe(j).status">{{ ROTULO[progressoDe(j).status] ?? progressoDe(j).status }}</span>
        <div class="barra-progresso"><div :style="{ width: `${progressoDe(j).progresso}%` }"></div></div>
        <span class="suave">{{ progressoDe(j).mensagem }}</span>
      </div>
    </section>

    <section v-if="resultado" class="painel">
      <div class="cabecalho-pagina">
        <h2>Métricas no conjunto de teste</h2>
        <label class="versao">
          Versão
          <select v-model.number="versaoSelecionada">
            <option v-for="r in resultados" :key="r.versao" :value="r.versao">
              v{{ r.versao }}{{ r.versao === versaoEmUso ? ' (em uso)' : '' }}
            </option>
          </select>
        </label>
      </div>
      <p class="suave">
        {{ inteiro(resultado.amostras_treino) }} janelas de treino · equipamentos: {{ resultado.equipamentos.treino }} treino,
        {{ resultado.equipamentos.validacao }} validação, {{ resultado.equipamentos.teste }} teste · {{ resultado.segundos }} s de treino
      </p>
      <div class="tabela-rolavel">
        <table>
          <thead>
            <tr>
              <th>Modelo</th>
              <th class="num">MAE</th>
              <th class="num">RMSE</th>
              <th class="num">R²</th>
              <th class="num">MAE da base</th>
              <th class="num">RMSE da base</th>
              <th class="num">R² da base</th>
              <th>Resultado</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(m, alvo) in resultado.modelos" :key="alvo">
              <td>{{ m.descricao }}<br /><span class="suave">{{ m.algoritmo }}</span></td>
              <td class="num"><strong>{{ numero(m.teste.mae, 2) }}</strong></td>
              <td class="num">{{ numero(m.teste.rmse, 2) }}</td>
              <td class="num">{{ numero(m.teste.r2, 3) }}</td>
              <td class="num">{{ numero(m.base_media.mae, 2) }}</td>
              <td class="num">{{ numero(m.base_media.rmse, 2) }}</td>
              <td class="num">{{ numero(m.base_media.r2, 3) }}</td>
              <td>
                <span class="selo" :class="m.vence_base ? 'normal' : 'critico'">{{ m.vence_base ? 'Vence a base' : 'Não vence a base' }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="suave">
        MAE é o erro médio absoluto (na unidade do alvo), RMSE pune mais os erros grandes e R² mede quanto da variação o modelo explica (1 é perfeito,
        0 é igual à média).
      </p>
    </section>
    <p v-else class="aviso info">Nenhum treino concluído. Gere dados no Laboratório e clique em Treinar modelos.</p>

    <template v-if="resultado">
      <div v-for="(m, alvo) in resultado.modelos" :key="alvo" class="grade-2">
        <section class="painel">
          <h2>{{ m.descricao }}: previsto contra real</h2>
          <Grafico tipo="scatter" :dados="dispersao(m)" :opcoes="opcoesDispersao" :altura="280" :rotulo="`Dispersão previsto contra real: ${m.descricao}`" />
        </section>
        <section class="painel">
          <h2>{{ m.descricao }}: importância dos atributos</h2>
          <Grafico tipo="bar" :dados="importancia(m)" :opcoes="opcoesImportancia" :altura="280" :rotulo="`Importância dos atributos: ${m.descricao}`" />
        </section>
      </div>
    </template>

    <section class="painel">
      <h2>Histórico de treinos</h2>
      <p v-if="!jobs.length" class="suave">Nenhum treino ainda.</p>
      <table v-else>
        <thead>
          <tr><th>Quando</th><th>Por</th><th>Status</th><th>Mensagem</th></tr>
        </thead>
        <tbody>
          <tr v-for="j in jobs" :key="j.id">
            <td class="suave">{{ dataHora(j.criado_em) }}</td>
            <td>{{ j.criado_por }}</td>
            <td><span class="selo" :class="progressoDe(j).status">{{ ROTULO[progressoDe(j).status] ?? progressoDe(j).status }}</span></td>
            <td>{{ progressoDe(j).mensagem }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
.job {
  display: grid;
  gap: 0.3rem;
  margin-top: 0.75rem;
  justify-items: start;
}

.job .barra-progresso {
  width: 100%;
}

.versao {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.versao select {
  width: auto;
}

.acoes {
  margin-top: 0.75rem;
}
</style>
