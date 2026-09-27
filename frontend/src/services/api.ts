import type { Leitura } from '../types'

async function obterJson<T>(url: string): Promise<T> {
  const resposta = await fetch(url)
  if (!resposta.ok) throw new Error(`HTTP ${resposta.status} em ${url}`)
  return (await resposta.json()) as T
}

/** Temperatura atual. Retorna null quando ainda não há nenhuma leitura gravada. */
export async function buscarAtual(): Promise<Leitura | null> {
  const resposta = await fetch('/api/temperatura')
  if (resposta.status === 404) return null
  if (!resposta.ok) throw new Error(`HTTP ${resposta.status} em /api/temperatura`)
  return (await resposta.json()) as Leitura
}

/** Últimas leituras da última hora, em ordem cronológica. */
export function buscarHistorico(): Promise<Leitura[]> {
  return obterJson<Leitura[]>('/api/temperatura/historico')
}
