<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import Grafico from '../components/Grafico.vue'
import { enviar, get } from '../api'
import { hora, numero } from '../formatacao'
import { ehOperador } from '../sessao'
import { ROTULO_STATUS, semDados, statusDe, tempoReal } from '../tempoReal'
import type { Alerta } from '../tipos'

const COMPRESSOR = 'comp-geladeira'

// ---------- indicadores ----------
function valor(id: string, campo = 'valor'): unknown {
  return tempoReal.leituras[id]?.conteudo[campo]
}
const previsao = computed(() => tempoReal.previsoes[COMPRESSOR])
const alertasAbertos = ref<Alerta[]>([])
const regras = ref<any[]>([])

async function carregarAlertas() {
  try {
    alertasAbertos.value = (await get<Alerta[]>('/api/alertas?limite=20')).filter((a) => !a.fechado_em)
  } catch {
    /* mantém a lista anterior */
  }
}

// ---------- atuadores ----------
const enviando = ref<string | null>(null)
const erroComando = ref('')
const atuadores = computed(() => tempoReal.dispositivos.filter((d) => d.classe === 'atuador'))

async function alternar(id: string) {
  enviando.value = id
  erroComando.value = ''
  try {
    await enviar('POST', `/api/dispositivos/${id}/comando`, { ligado: !valor(id, 'ligado') })
  } catch (e) {
    erroComando.value = (e as Error).message
  } finally {
    enviando.value = null
  }
}

function regraDe(atuador: string) {
  return regras.value.find((r) => r.atuador_id === atuador)
}

// ---------- histórico (InfluxDB) ----------
const OPCOES_HISTORICO = [
  { id: 'temp-sala', campos: 'valor', texto: 'Temperatura da sala (°C)' },
  { id: 'lum-sala', campos: 'valor', texto: 'Luminosidade da sala (lux)' },
  { id: 'pres-sala', campos: 'valor', texto: 'Presença na sala' },
  { id: COMPRESSOR, campos: 'vibracao,corrente,temperatura', texto: 'Compressor da geladeira' },
  { id: 'vent-sala', campos: 'ligado', texto: 'Ventilador ligado (1) / desligado (0)' },
  { id: 'lamp-sala', campos: 'ligado', texto: 'Lâmpada ligada (1) / desligada (0)' },
]
const selecionado = ref(OPCOES_HISTORICO[0])
const minutos = ref(30)
const historico = ref<Record<string, [string, number][]>>({})
const erroHistorico = ref('')
const CORES = ['#2a7a8c', '#c98a12', '#d1453a']

async function carregarHistorico() {
  try {
    historico.value = await get(
      `/api/telemetria/historico?dispositivo=${selecionado.value.id}&campos=${selecionado.value.campos}&minutos=${minutos.value}`,
    )
    erroHistorico.value = ''
  } catch (e) {
    erroHistorico.value = (e as Error).message
  }
}

const dadosHistorico = computed(() => {
  const campos = Object.keys(historico.value)
  const base = historico.value[campos[0]] ?? []
  return {
    labels: base.map(([t]) => hora(t)),
    datasets: campos.map((campo, i) => ({
      label: campo,
      data: (historico.value[campo] ?? []).map(([, v]) => v),
      borderColor: CORES[i],
      backgroundColor: CORES[i],
      borderWidth: 2,
      pointRadius: 0,
      tension: 0.25,
      stepped: campo === 'ligado',
    })),
  }
})

// ---------- compressor ao vivo (WebSocket) ----------
const dadosCompressor = computed(() => {
  const s = tempoReal.series[COMPRESSOR] ?? {}
  const base = s.temperatura ?? []
  const linha = (campo: string, cor: string, eixo: string) => ({
    label: campo,
    data: (s[campo] ?? []).map((p) => p.v),
    borderColor: cor,
    backgroundColor: cor,
    borderWidth: 2,
    pointRadius: 0,
    yAxisID: eixo,
  })
  return {
    labels: base.map((p) => hora(p.t)),
    datasets: [linha('vibracao', '#d1453a', 'y'), linha('corrente', '#c98a12', 'y'), linha('temperatura', '#2a7a8c', 'y1')],
  }
})
const opcoesCompressor = {
  plugins: { legend: { display: true, position: 'bottom' as const } },
  scales: {
    y: { title: { display: true, text: 'vibração (mm/s) · corrente (A)' }, grid: { color: '#e4ebef' } },
    y1: { position: 'right' as const, title: { display: true, text: 'temperatura (°C)' }, grid: { display: false } },
  },
}

let temporizador: number | undefined
onMounted(async () => {
  carregarHistorico()
  carregarAlertas()
  try {
    regras.value = await get('/api/regras')
  } catch {
    /* sem regras */
  }
  temporizador = window.setInterval(() => {
    carregarHistorico()
    carregarAlertas()
  }, 10_000)
})
onUnmounted(() => window.clearInterval(temporizador))
watch([selecionado, minutos], carregarHistorico)

const ROTULO_EVENTO: Record<string, string> = { alerta: 'Alerta', comando: 'Comando' }
function descreverEvento(m: any): string {
  if (m.tipo === 'alerta') return m.conteudo.mensagem
  const origem = m.conteudo.origem === 'regra' ? `regra "${m.conteudo.regra}"` : m.conteudo.usuario ? `usuário ${m.conteudo.usuario}` : 'aplicação'
  if (m.dispositivo === 'simulador') return `Simulador: ${m.conteudo.acao === 'reparar' ? 'reparar compressor' : `injetar falha (${m.conteudo.modo})`} por ${origem}`
  return `${m.dispositivo} → ${m.conteudo.ligado ? 'ligar' : 'desligar'} (${origem})`
}
</script>

<template>
  <div class="pagina">
    <header class="cabecalho-pagina">
      <div>
        <h1>Dashboard</h1>
        <p>Leituras chegando em tempo real pelo WebSocket · {{ tempoReal.mensagensPorSegundo }} mensagens/s</p>
      </div>
    </header>

    <p v-if="semDados()" class="aviso">
      Nenhuma telemetria nos últimos 10 segundos. Verifique se o serviço <code>simulador</code> está em execução.
    </p>

    <section class="grade" aria-label="Indicadores">
      <article class="painel indicador">
        <h2>Temperatura da sala</h2>
        <p class="valor">{{ numero(valor('temp-sala')) }}<small>°C</small></p>
        <span class="selo" :class="statusDe('temp-sala')">{{ ROTULO_STATUS[statusDe('temp-sala')] }}</span>
      </article>
      <article class="painel indicador">
        <h2>Luminosidade da sala</h2>
        <p class="valor">{{ numero(valor('lum-sala'), 0) }}<small>lux</small></p>
        <span class="selo" :class="statusDe('lum-sala')">{{ ROTULO_STATUS[statusDe('lum-sala')] }}</span>
      </article>
      <article class="painel indicador">
        <h2>Presença na sala</h2>
        <p class="valor">{{ valor('pres-sala') === undefined ? '—' : valor('pres-sala') ? 'Alguém' : 'Vazia' }}</p>
        <span class="selo" :class="statusDe('pres-sala')">{{ ROTULO_STATUS[statusDe('pres-sala')] }}</span>
      </article>
      <article class="painel indicador">
        <h2>Saúde do compressor (IA)</h2>
        <p class="valor">{{ previsao ? numero(previsao.saude, 0) : '—' }}<small v-if="previsao">/100</small></p>
        <span class="selo" :class="statusDe(COMPRESSOR)">{{ ROTULO_STATUS[statusDe(COMPRESSOR)] }}</span>
        <p v-if="previsao" class="suave">Vida útil restante: ~{{ numero(previsao.vida_util_h, 0) }} h</p>
        <p v-else class="suave">Treine os modelos para ver a previsão.</p>
      </article>
      <article class="painel indicador">
        <h2>Alertas abertos</h2>
        <p class="valor">{{ alertasAbertos.length }}</p>
        <p class="suave">{{ alertasAbertos[0]?.mensagem ?? 'Nenhum alerta da IA no momento.' }}</p>
      </article>
    </section>

    <section class="painel">
      <h2>Atuadores</h2>
      <p v-if="erroComando" class="aviso erro">{{ erroComando }}</p>
      <div class="grade">
        <article v-for="a in atuadores" :key="a.id" class="atuador">
          <h3>{{ a.nome }}</h3>
          <p>
            <span class="selo" :class="valor(a.id, 'ligado') ? 'normal' : 'sem_dados'">
              {{ valor(a.id, 'ligado') === undefined ? 'Sem dados' : valor(a.id, 'ligado') ? 'Ligado' : 'Desligado' }}
            </span>
          </p>
          <template v-if="a.controlavel">
            <button :disabled="!ehOperador || enviando === a.id || valor(a.id, 'ligado') === undefined" @click="alternar(a.id)">
              {{ valor(a.id, 'ligado') ? 'Desligar' : 'Ligar' }}
            </button>
            <p v-if="!ehOperador" class="suave">Só operadores e administradores enviam comandos.</p>
          </template>
          <p v-else-if="regraDe(a.id)" class="suave">
            Automático: liga acima de {{ regraDe(a.id).limite_liga }} °C e desliga abaixo de {{ regraDe(a.id).limite_desliga }} °C.
          </p>
        </article>
      </div>
    </section>

    <div class="grade-2">
      <section class="painel">
        <div class="cabecalho-grafico">
          <h2>Histórico (InfluxDB)</h2>
          <div class="filtros">
            <select v-model="selecionado" aria-label="Dispositivo">
              <option v-for="o in OPCOES_HISTORICO" :key="o.id" :value="o">{{ o.texto }}</option>
            </select>
            <select v-model.number="minutos" aria-label="Período">
              <option :value="15">15 min</option>
              <option :value="30">30 min</option>
              <option :value="60">1 h</option>
              <option :value="360">6 h</option>
              <option :value="1440">24 h</option>
            </select>
          </div>
        </div>
        <p v-if="erroHistorico" class="aviso erro">{{ erroHistorico }}</p>
        <Grafico
          :dados="dadosHistorico"
          :opcoes="{ plugins: { legend: { display: dadosHistorico.datasets.length > 1, position: 'bottom' } } }"
          rotulo="Gráfico de linha com o histórico do dispositivo selecionado"
        />
      </section>

      <section class="painel">
        <h2>Compressor da geladeira ao vivo</h2>
        <Grafico :dados="dadosCompressor" :opcoes="opcoesCompressor" rotulo="Vibração, corrente e temperatura do compressor ao vivo" />
      </section>
    </div>

    <section class="painel">
      <h2>Eventos recentes</h2>
      <p v-if="!tempoReal.eventos.length" class="suave">Comandos e alertas aparecem aqui assim que acontecem.</p>
      <table v-else>
        <tbody>
          <tr v-for="e in tempoReal.eventos.slice(0, 8)" :key="e.id">
            <td class="suave">{{ hora(e.instante) }}</td>
            <td>{{ ROTULO_EVENTO[e.tipo] }}</td>
            <td>{{ descreverEvento(e) }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
.atuador {
  display: grid;
  gap: 0.4rem;
  align-content: start;
}

.atuador h3,
.atuador p {
  margin: 0;
}

.atuador button {
  justify-self: start;
}

.cabecalho-grafico {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.cabecalho-grafico h2 {
  margin: 0;
}

.filtros {
  display: flex;
  gap: 0.5rem;
}

.filtros select {
  width: auto;
}
</style>
