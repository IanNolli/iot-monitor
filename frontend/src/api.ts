import { sair, sessao } from './sessao'
import router from './router'

export class ErroApi extends Error {
  constructor(public status: number, mensagem: string) {
    super(mensagem)
  }
}

function cabecalhos(extra: Record<string, string> = {}): Record<string, string> {
  const h: Record<string, string> = { ...extra }
  if (sessao.token) h.Authorization = `Bearer ${sessao.token}`
  return h
}

async function tratar(resposta: Response): Promise<Response> {
  if (resposta.ok) return resposta
  let mensagem = `Erro ${resposta.status}`
  try {
    const corpo = await resposta.json()
    if (typeof corpo.detail === 'string') mensagem = corpo.detail
    else if (Array.isArray(corpo.detail)) mensagem = corpo.detail.map((d: any) => d.msg).join('; ')
  } catch {
    /* corpo não é JSON */
  }
  if (resposta.status === 401 && sessao.token) {
    sair()
    router.push({ name: 'login', query: { expirou: '1' } })
  }
  throw new ErroApi(resposta.status, mensagem)
}

export async function get<T>(url: string): Promise<T> {
  const r = await tratar(await fetch(url, { headers: cabecalhos() }))
  return (await r.json()) as T
}

export async function enviar<T>(metodo: 'POST' | 'PUT' | 'DELETE', url: string, corpo?: unknown): Promise<T> {
  const r = await tratar(
    await fetch(url, {
      method: metodo,
      headers: cabecalhos({ 'Content-Type': 'application/json' }),
      body: corpo === undefined ? undefined : JSON.stringify(corpo),
    }),
  )
  return (r.status === 204 ? null : await r.json()) as T
}

/** POST que devolve o corpo em streaming (resposta do assistente). */
export async function enviarStream(url: string, corpo: unknown, aoReceber: (parte: string) => void): Promise<void> {
  const r = await tratar(
    await fetch(url, {
      method: 'POST',
      headers: cabecalhos({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(corpo),
    }),
  )
  const leitor = r.body!.getReader()
  const decodificador = new TextDecoder()
  for (;;) {
    const { done, value } = await leitor.read()
    if (done) break
    aoReceber(decodificador.decode(value, { stream: true }))
  }
}
