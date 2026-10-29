/**
 * Estado ao vivo da aplicação, alimentado SOMENTE pelo WebSocket da API.
 * Dashboard, gêmeo 3D, Insights e Laboratório leem daqui. A cena 3D lê dentro do seu
 * loop de animação, sem ser redesenhada a cada mensagem.
 */
import { reactive } from 'vue'
import { enviar, get } from './api'
import type { Dispositivo, Mensagem, Previsao, Progresso, Status } from './tipos'

const MAX_PONTOS = 90 // ~3 minutos com uma leitura a cada 2 s
export const SEM_DADOS_APOS_MS = 10_000

interface Ponto {
  t: number
  v: number
}

export const tempoReal = reactive({
  conectado: false,
  ultimaTelemetriaEm: 0, // Date.now() da última telemetria recebida
  agora: Date.now(),
  horaSimulada: '',
  leituras: {} as Record<string, Mensagem>,
  series: {} as Record<string, Record<string, Ponto[]>>,
  previsoes: {} as Record<string, Previsao>,
  jobs: {} as Record<string, Progresso>,
  eventos: [] as Mensagem[], // alertas e comandos recentes
  mensagensPorSegundo: 0,
  dispositivos: [] as Dispositivo[],
})

let ws: WebSocket | null = null
let ativo = false
let contadorMensagens = 0
let tentativa = 0
const ouvintes = new Set<(m: Mensagem) => void>()

export function aoReceber(f: (m: Mensagem) => void): () => void {
  ouvintes.add(f)
  return () => ouvintes.delete(f)
}

export function semDados(): boolean {
  return !tempoReal.ultimaTelemetriaEm || tempoReal.agora - tempoReal.ultimaTelemetriaEm > SEM_DADOS_APOS_MS
}

function registrarSerie(id: string, conteudo: Record<string, unknown>, t: number) {
  const series = (tempoReal.series[id] ??= {})
  for (const [campo, valor] of Object.entries(conteudo)) {
    if (typeof valor !== 'number' && typeof valor !== 'boolean') continue
    const lista = (series[campo] ??= [])
    lista.push({ t, v: typeof valor === 'boolean' ? Number(valor) : valor })
    if (lista.length > MAX_PONTOS) lista.splice(0, lista.length - MAX_PONTOS)
  }
}

function processar(m: Mensagem) {
  contadorMensagens++
  const t = Date.parse(m.instante) || Date.now()
  if (m.tipo === 'telemetria' && m.dispositivo) {
    if (m.dispositivo === 'simulador') {
      tempoReal.horaSimulada = String(m.conteudo.hora_simulada ?? '')
    } else {
      tempoReal.leituras[m.dispositivo] = m
      registrarSerie(m.dispositivo, m.conteudo, t)
    }
    tempoReal.ultimaTelemetriaEm = Date.now()
  } else if (m.tipo === 'previsao' && m.dispositivo) {
    tempoReal.previsoes[m.dispositivo] = m.conteudo as unknown as Previsao
    registrarSerie(`${m.dispositivo}#ia`, { saude: (m.conteudo as any).saude }, t)
  } else if (m.tipo === 'progresso') {
    const p = m.conteudo as unknown as Progresso
    tempoReal.jobs[p.job_id] = p
  } else if (m.tipo === 'alerta' || m.tipo === 'comando') {
    tempoReal.eventos.unshift(m)
    if (tempoReal.eventos.length > 30) tempoReal.eventos.pop()
  }
  ouvintes.forEach((f) => f(m))
}

async function abrir() {
  if (!ativo) return
  try {
    // O JWT não vai na URL: pedimos um ticket curto, de uso único
    const { ticket } = await enviar<{ ticket: string }>('POST', '/api/ws/ticket')
    const protocolo = location.protocol === 'https:' ? 'wss' : 'ws'
    ws = new WebSocket(`${protocolo}://${location.host}/ws?ticket=${encodeURIComponent(ticket)}`)
  } catch {
    agendarReconexao()
    return
  }
  ws.onopen = () => {
    tempoReal.conectado = true
    tentativa = 0
  }
  ws.onmessage = (evento) => {
    const m = JSON.parse(evento.data)
    if (m.tipo === 'estado_inicial') {
      for (const leitura of Object.values(m.conteudo.leituras || {}) as Mensagem[]) {
        if (leitura.dispositivo) tempoReal.leituras[leitura.dispositivo] = leitura
      }
      for (const [id, p] of Object.entries(m.conteudo.previsoes || {}) as [string, Mensagem][]) {
        tempoReal.previsoes[id] = p.conteudo as unknown as Previsao
      }
      // a última telemetria conhecida pelo servidor decide se há dados ao vivo
      const ultima = m.conteudo.ultima_telemetria_em
      tempoReal.ultimaTelemetriaEm = ultima ? Date.now() - Math.max(0, Date.now() / 1000 - ultima) * 1000 : 0
      return
    }
    processar(m as Mensagem)
  }
  ws.onclose = () => {
    tempoReal.conectado = false
    ws = null
    agendarReconexao()
  }
}

function agendarReconexao() {
  if (!ativo) return
  tentativa++
  setTimeout(abrir, Math.min(10_000, 1000 * tentativa))
}

let relogio: number | undefined

export async function iniciarTempoReal() {
  if (ativo) return
  ativo = true
  relogio = window.setInterval(() => {
    tempoReal.agora = Date.now()
    tempoReal.mensagensPorSegundo = contadorMensagens
    contadorMensagens = 0
  }, 1000)
  await recarregarDispositivos()
  abrir()
}

export function pararTempoReal() {
  ativo = false
  window.clearInterval(relogio)
  ws?.close()
}

export async function recarregarDispositivos() {
  try {
    tempoReal.dispositivos = await get<Dispositivo[]>('/api/dispositivos')
  } catch {
    /* tratado pela tela que precisar */
  }
}

export function dispositivo(id: string): Dispositivo | undefined {
  return tempoReal.dispositivos.find((d) => d.id === id)
}

/** Estado por cor: faixa normal do cadastro para sensores; previsão da IA para equipamentos. */
export function statusDe(id: string): Status {
  const leitura = tempoReal.leituras[id]
  if (!leitura || semDados()) return 'sem_dados'
  const d = dispositivo(id)
  if (!d) return 'normal'
  if (d.classe === 'equipamento') return tempoReal.previsoes[id]?.nivel ?? 'normal'
  const valor = leitura.conteudo.valor
  if (d.classe !== 'sensor' || typeof valor !== 'number' || d.faixa_min === null || d.faixa_max === null) return 'normal'
  const margem = (d.faixa_max - d.faixa_min) * 0.1
  if (valor >= d.faixa_min && valor <= d.faixa_max) return 'normal'
  if (valor >= d.faixa_min - margem && valor <= d.faixa_max + margem) return 'atencao'
  return 'critico'
}

export const ROTULO_STATUS: Record<Status, string> = {
  normal: 'Normal',
  atencao: 'Atenção',
  critico: 'Crítico',
  sem_dados: 'Sem dados',
}
