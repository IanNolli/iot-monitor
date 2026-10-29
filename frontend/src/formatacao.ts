export function numero(valor: unknown, casas = 1): string {
  if (typeof valor !== 'number' || Number.isNaN(valor)) return '—'
  return valor.toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas })
}

export function inteiro(valor: unknown): string {
  return typeof valor === 'number' ? Math.round(valor).toLocaleString('pt-BR') : '—'
}

export function hora(iso: string | number): string {
  return new Date(iso).toLocaleTimeString('pt-BR')
}

export function dataHora(iso: string): string {
  return new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'medium' })
}

const ESCAPES: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }

/**
 * Markdown mínimo para a resposta do LLM, tratada como texto NÃO confiável:
 * todo HTML é escapado antes; só negrito, itálico, código e listas viram tags. Sem imagens nem links.
 */
export function markdownSeguro(texto: string): string {
  const escapado = texto.replace(/[&<>"']/g, (c) => ESCAPES[c])
  const inline = (s: string) =>
    s
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
  const html: string[] = []
  let lista: 'ul' | 'ol' | null = null
  for (const linha of escapado.split('\n')) {
    const item = linha.match(/^\s*(?:[-*•]|(\d+)[.)])\s+(.*)$/)
    if (item) {
      const tipo = item[1] ? 'ol' : 'ul'
      if (lista !== tipo) {
        if (lista) html.push(`</${lista}>`)
        html.push(`<${tipo}>`)
        lista = tipo
      }
      html.push(`<li>${inline(item[2])}</li>`)
      continue
    }
    if (lista) {
      html.push(`</${lista}>`)
      lista = null
    }
    const titulo = linha.match(/^#{1,4}\s+(.*)$/)
    if (titulo) html.push(`<p><strong>${inline(titulo[1])}</strong></p>`)
    else if (linha.trim()) html.push(`<p>${inline(linha)}</p>`)
  }
  if (lista) html.push(`</${lista}>`)
  return html.join('')
}
