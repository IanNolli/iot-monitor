/** Uma leitura de temperatura como retornada pela API. */
export interface Leitura {
  temperatura: number
  /** Data/hora ISO 8601 (UTC) em que a leitura foi gravada. */
  timestamp: string
}
