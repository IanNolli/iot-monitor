export type Papel = 'visualizador' | 'operador' | 'administrador'

export interface Usuario {
  login: string
  nome: string
  papel: Papel
}

/** Formato único das mensagens que chegam pelo WebSocket (o mesmo do RabbitMQ). */
export interface Mensagem<T = Record<string, unknown>> {
  id: string
  instante: string
  tipo: 'telemetria' | 'previsao' | 'alerta' | 'progresso' | 'modelo' | 'comando' | 'job'
  dispositivo: string | null
  conteudo: T
}

export interface Dispositivo {
  id: string
  nome: string
  classe: 'sensor' | 'atuador' | 'equipamento'
  zona: string
  grandeza: string
  unidade: string
  faixa_min: number | null
  faixa_max: number | null
  controlavel: boolean
  ativo: boolean
}

export interface Previsao {
  saude: number
  vida_util_h: number
  tendencia_saude_h: number
  nivel: 'normal' | 'atencao' | 'critico'
  versao_modelo: number
}

export interface Progresso {
  job_id: string
  tipo: 'geracao' | 'treino'
  status: 'na_fila' | 'executando' | 'concluido' | 'erro'
  progresso: number
  mensagem: string
  resultado?: Record<string, unknown>
}

export interface Job {
  id: string
  tipo: 'geracao' | 'treino'
  status: string
  progresso: number
  mensagem: string
  parametros: Record<string, unknown>
  resultado: Record<string, any> | null
  criado_por: string
  criado_em: string
  atualizado_em: string
}

export interface Alerta {
  id: number
  dispositivo_id: string
  nivel: string
  mensagem: string
  saude: number | null
  vida_util_h: number | null
  aberto_em: string
  fechado_em: string | null
}

export type Status = 'normal' | 'atencao' | 'critico' | 'sem_dados'
