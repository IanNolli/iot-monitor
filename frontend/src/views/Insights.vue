<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import Grafico from '../components/Grafico.vue'
import { enviar, get } from '../api'
import { dataHora, hora, numero } from '../formatacao'
import { ehOperador } from '../sessao'
import { tempoReal } from '../tempoReal'
import type { Alerta } from '../tipos'

interface InsightEquipamento {
  id: string
  nome: string
  alertas: Alerta[]
  historico: Record<string, [string, number][]>
}

const modeloEmUso = ref<number | null>(null)
const equipamentos = ref<InsightEquipamento[]>([])
const alertas = ref<Alerta[]>([])
const erro = ref('')
const modo = ref('rolamento')
const mensagemComando = ref('')
const enviando = ref(false)

const MODOS = [
  { id: 'rolamento', texto: 'Desgaste de rolamento (vibração sobe)' },
  { id: 'superaquecimento', texto: 'Superaquecimento (temperatura sobe)' },
  { id: 'entupimento', texto: 'Entupimento (temperatura e corrente sobem)' },
  { id: 'desbalanceamento', texto: 'Desbalanceamento (vibração oscila)' },
]
const NIVEL = { normal: 'Normal', atencao: 'Atenção', critico: 'Crítico' } as const

async function carregar() {
  try {
    const r = await get<{ modelo_em_uso: number | null; equipamentos: InsightEquipamento[] }>('/api/insights')
    modeloEmUso.value = r.modelo_em_uso
    equipamentos.value = r.equipamentos
    alertas.value = await get<Alerta[]>('/api/alertas?limite=15')
    erro.value = ''
  } catch (e) {
    erro.value = (e as Error).message
  }
}

async function simulador(acao: 'injetar_falha' | 'reparar') {
  enviando.value = true
  mensagemComando.value = ''
  try {
    await enviar('POST', '/api/simulador/comando', { acao, modo: modo.value })
    mensagemComando.value =
      acao === 'reparar'
        ? 'Reparo enviado. A saúde volta a subir; o alerta só fecha depois de 10 previsões seguidas normais (histerese).'
        : 'Falha injetada. A degradação é progressiva: acompanhe a saúde caindo nos próximos minutos.'
  } catch (e) {
    mensagemComando.value = (e as Error).message
  } finally {
    enviando.value = false
  }
}

// gráfico da saúde: histórico do InfluxDB + previsões ao vivo
function grafico(id: string) {
  const vivo = tempoReal.series[`${id}#ia`]?.saude ?? []
  const historico = equipamentos.value.find((e) => e.id === id)?.historico?.saude ?? []
  const pontos = [
    ...historico.filter(([t]) => !vivo.length || Date.parse(t) < vivo[0].t).map(([t, v]) => ({ t: Date.parse(t), v })),
    ...vivo,
  ]
  return {
    labels: pontos.map((p) => hora(p.t)),
    datasets: [
      { label: 'saúde', data: pontos.map((p) => p.v), borderColor: '#2a7a8c', backgroundColor: 'rgba(42,122,140,.12)', fill: true, borderWidth: 2, pointRadius: 0 },
    ],
  }
}

const opcoesSaude = { scales: { y: { min: 0, max: 100, grid: { color: '#e4ebef' } } } }

const abertos = computed(() => alertas.value.filter((a) => !a.fechado_em))

let temporizador: number | undefined
onMounted(() => {
  carregar()
  temporizador = window.setInterval(carregar, 5000)
})
onUnmounted(() => window.clearInterval(temporizador))
</script>

<template>
  <div class="pagina">
    <header class="cabecalho-pagina">
      <div>
        <h1>Insights</h1>
        <p>Manutenção preditiva em tempo real: saúde, vida útil restante, tendência e alertas da IA.</p>
      </div>
      <span class="selo" :class="modeloEmUso ? 'normal' : 'atencao'">
        {{ modeloEmUso ? `Modelo v${modeloEmUso} em uso` : 'Nenhum modelo treinado' }}
      </span>
    </header>

    <p v-if="erro" class="aviso erro">{{ erro }}</p>
    <p v-if="!modeloEmUso" class="aviso info">
      Gere dados no Laboratório e treine os modelos na página Treinamento para a IA começar a prever.
    </p>

    <article v-for="e in equipamentos" :key="e.id" class="painel equipamento">
      <div class="resumo">
        <div>
          <h2>{{ e.nome }}</h2>
          <span v-if="tempoReal.previsoes[e.id]" class="selo" :class="tempoReal.previsoes[e.id].nivel">
            {{ NIVEL[tempoReal.previsoes[e.id].nivel] }}
          </span>
          <span v-else class="selo sem_dados">Sem previsão</span>
        </div>
        <div class="numeros">
          <div>
            <span class="suave">Índice de saúde</span>
            <strong>{{ numero(tempoReal.previsoes[e.id]?.saude, 0) }}<small>/100</small></strong>
          </div>
          <div>
            <span class="suave">Vida útil restante</span>
            <strong>{{ numero(tempoReal.previsoes[e.id]?.vida_util_h, 0) }}<small>h</small></strong>
          </div>
          <div>
            <span class="suave">Tendência</span>
            <strong>{{ numero(tempoReal.previsoes[e.id]?.tendencia_saude_h, 1) }}<small>pts/h</small></strong>
          </div>
        </div>
      </div>
      <p v-for="a in e.alertas" :key="a.id" class="aviso" :class="{ erro: a.nivel === 'critico' }">{{ a.mensagem }}</p>
      <Grafico :dados="grafico(e.id)" :opcoes="opcoesSaude" :altura="200" rotulo="Gráfico da saúde prevista do compressor" />
      <p class="suave">
        As horas são do tempo simulado: cada leitura do simulador representa 5 minutos de operação.
      </p>
    </article>

    <div class="grade-2">
      <section class="painel">
        <h2>Injetar falha no simulador</h2>
        <p class="suave">Para a demonstração: o simulador passa a degradar o compressor aos poucos, como uma máquina real.</p>
        <div class="campos">
          <label>
            Modo de falha
            <select v-model="modo">
              <option v-for="m in MODOS" :key="m.id" :value="m.id">{{ m.texto }}</option>
            </select>
          </label>
        </div>
        <div class="acoes" style="margin-top: 0.75rem">
          <button class="perigo" :disabled="!ehOperador || enviando" @click="simulador('injetar_falha')">Injetar falha</button>
          <button class="secundario" :disabled="!ehOperador || enviando" @click="simulador('reparar')">Reparar compressor</button>
        </div>
        <p v-if="!ehOperador" class="suave">Disponível para operadores e administradores.</p>
        <p v-if="mensagemComando" class="aviso info" style="margin-top: 0.75rem">{{ mensagemComando }}</p>
      </section>

      <section class="painel">
        <h2>Alertas ({{ abertos.length }} abertos)</h2>
        <p v-if="!alertas.length" class="suave">Nenhum alerta registrado.</p>
        <table v-else>
          <thead>
            <tr><th>Nível</th><th>Mensagem</th><th>Aberto</th><th>Fechado</th></tr>
          </thead>
          <tbody>
            <tr v-for="a in alertas" :key="a.id">
              <td><span class="selo" :class="a.nivel">{{ NIVEL[a.nivel as keyof typeof NIVEL] ?? a.nivel }}</span></td>
              <td>{{ a.mensagem }}</td>
              <td class="suave">{{ dataHora(a.aberto_em) }}</td>
              <td class="suave">{{ a.fechado_em ? dataHora(a.fechado_em) : 'aberto' }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </div>
  </div>
</template>

<style scoped>
.equipamento {
  display: grid;
  gap: 0.75rem;
}

.resumo {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 1rem;
}

.resumo h2 {
  margin-bottom: 0.3rem;
}

.numeros {
  display: flex;
  flex-wrap: wrap;
  gap: 1.75rem;
}

.numeros div {
  display: grid;
}

.numeros strong {
  font-size: 1.8rem;
  font-weight: 300;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}

.numeros small {
  font-size: 0.5em;
  color: var(--tinta-suave);
  margin-left: 0.15em;
}
</style>
