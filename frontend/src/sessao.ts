import { computed, reactive } from 'vue'
import type { Papel, Usuario } from './tipos'

const CHAVE = 'aiot_sessao'
const NIVEL: Record<Papel, number> = { visualizador: 0, operador: 1, administrador: 2 }

function carregar(): { token: string | null; usuario: Usuario | null } {
  try {
    const salvo = JSON.parse(localStorage.getItem(CHAVE) || 'null')
    if (salvo?.token) {
      // descarta token já expirado
      const exp = JSON.parse(atob(salvo.token.split('.')[1])).exp * 1000
      if (exp > Date.now()) return salvo
    }
  } catch {
    /* sem sessão salva */
  }
  return { token: null, usuario: null }
}

export const sessao = reactive(carregar())

export function entrar(token: string, usuario: Usuario) {
  sessao.token = token
  sessao.usuario = usuario
  try {
    localStorage.setItem(CHAVE, JSON.stringify({ token, usuario }))
  } catch {
    /* navegador sem armazenamento: a sessão vale só nesta aba */
  }
}

export function sair() {
  sessao.token = null
  sessao.usuario = null
  try {
    localStorage.removeItem(CHAVE)
  } catch {
    /* ignore */
  }
}

export function pode(papel: Papel): boolean {
  return !!sessao.usuario && NIVEL[sessao.usuario.papel] >= NIVEL[papel]
}

export const ehOperador = computed(() => pode('operador'))
export const ehAdmin = computed(() => pode('administrador'))
