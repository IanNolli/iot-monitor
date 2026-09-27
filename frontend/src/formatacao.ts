export function formatarTemperatura(valor: number): string {
  return valor.toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
}

export function formatarHora(iso: string): string {
  return new Date(iso).toLocaleTimeString('pt-BR')
}
