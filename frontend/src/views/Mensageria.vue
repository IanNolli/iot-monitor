<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { enviar, get } from '../api'
import { hora, numero } from '../formatacao'
import { ehAdmin } from '../sessao'

interface Fila {
  nome: string
  mensagens: number
  prontas: number
  nao_confirmadas: number
  consumidores: number
  entrada_por_s: number
  entrega_por_s: number
}

interface Resumo {
  filas: Fila[]
  consumidores: { fila: string; conexao: string; usuario: string }[]
  taxas_globais: { publicacao_por_s: number; entrega_por_s: number }
  recentes: any[]
  dlq: { motivo: string | null; origem: string; corpo: string }[]
}

const dados = ref<Resumo | null>(null)
const erro = ref('')
const avisoDlq = ref('')
const historicoFilas = ref<Record<string, number[]>>({})

const PAPEL: Record<string, string> = {
  'q.gravador': 'gravação no InfluxDB',
  'q.inferencia': 'inferência da IA',
  'q.websocket': 'entrega ao WebSocket',
  'q.regras': 'regras de negócio e persistência',
  'q.comandos': 'comandos para o dispositivo',
  'q.jobs.lab': 'job de geração de dados',
  'q.jobs.treino': 'job de treino',
  'aiot.dlq': 'mensagens mortas (DLQ)',
}

async function carregar() {
  try {
    dados.value = await get<Resumo>('/api/mensageria')
    for (const f of dados.value.filas) {
      const lista = (historicoFilas.value[f.nome] ??= [])
      lista.push(f.mensagens)
      if (lista.length > 30) lista.shift()
    }
    erro.value = ''
  } catch (e) {
    erro.value = (e as Error).message
  }
}

async function testarDlq() {
  avisoDlq.value = ''
  try {
    await enviar('POST', '/api/mensageria/teste-dlq')
    avisoDlq.value = 'Mensagem fora do formato publicada. Ela deve aparecer na DLQ em instantes.'
  } catch (e) {
    avisoDlq.value = (e as Error).message
  }
}

function linhaTendencia(valores: number[] = []): string {
  if (valores.length < 2) return ''
  const max = Math.max(1, ...valores)
  return valores.map((v, i) => `${(i / (valores.length - 1)) * 100},${20 - (v / max) * 18}`).join(' ')
}

let temporizador: number | undefined
onMounted(() => {
  carregar()
  temporizador = window.setInterval(carregar, 2000)
})
onUnmounted(() => window.clearInterval(temporizador))
</script>

<template>
  <div class="pagina">
    <header class="cabecalho-pagina">
      <div>
        <h1>Mensageria</h1>
        <p>RabbitMQ ao vivo (consultado pela API de gerenciamento; o navegador nunca fala com o broker).</p>
      </div>
      <p v-if="dados" class="suave">
        Publicação {{ numero(dados.taxas_globais.publicacao_por_s) }}/s · entrega {{ numero(dados.taxas_globais.entrega_por_s) }}/s
      </p>
    </header>

    <p v-if="erro" class="aviso erro">{{ erro }}</p>

    <section class="painel">
      <h2>Filas do exchange <code>aiot.eventos</code> (topic)</h2>
      <div class="tabela-rolavel">
        <table>
          <thead>
            <tr>
              <th>Fila</th>
              <th>Consumidor</th>
              <th class="num">Mensagens</th>
              <th class="num">Não confirmadas</th>
              <th class="num">Consumidores</th>
              <th class="num">Entrada/s</th>
              <th class="num">Entrega/s</th>
              <th>Últimos 60 s</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="f in dados?.filas ?? []" :key="f.nome" :class="{ parada: f.consumidores === 0 && f.nome !== 'aiot.dlq' }">
              <td><code>{{ f.nome }}</code></td>
              <td class="suave">{{ PAPEL[f.nome] ?? '' }}</td>
              <td class="num"><strong>{{ f.mensagens }}</strong></td>
              <td class="num">{{ f.nao_confirmadas }}</td>
              <td class="num">
                <span v-if="f.consumidores === 0 && f.nome !== 'aiot.dlq'" class="selo critico">0 · parado</span>
                <template v-else>{{ f.consumidores }}</template>
              </td>
              <td class="num">{{ numero(f.entrada_por_s) }}</td>
              <td class="num">{{ numero(f.entrega_por_s) }}</td>
              <td>
                <svg viewBox="0 0 100 20" class="tendencia" aria-hidden="true">
                  <polyline :points="linhaTendencia(historicoFilas[f.nome])" />
                </svg>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="suave">
        Para mostrar o efeito de um consumidor parado: <code>docker compose stop gravador</code> (a fila
        <code>q.gravador</code> cresce) e depois <code>docker compose start gravador</code> (ela esvazia).
      </p>
    </section>

    <div class="grade-2">
      <section class="painel">
        <h2>Consumidores conectados</h2>
        <table>
          <thead>
            <tr><th>Fila</th><th>Conexão</th><th>Usuário RabbitMQ</th></tr>
          </thead>
          <tbody>
            <tr v-for="(c, i) in dados?.consumidores ?? []" :key="i">
              <td><code>{{ c.fila }}</code></td>
              <td>{{ c.conexao }}</td>
              <td>{{ c.usuario }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section class="painel">
        <h2>Fila de mensagens mortas (DLQ)</h2>
        <div class="acoes">
          <button class="secundario" :disabled="!ehAdmin" @click="testarDlq">Publicar mensagem inválida</button>
          <span v-if="!ehAdmin" class="suave">Teste disponível para administradores.</span>
        </div>
        <p v-if="avisoDlq" class="aviso info" style="margin-top: 0.6rem">{{ avisoDlq }}</p>
        <p v-if="!dados?.dlq.length" class="suave" style="margin-top: 0.6rem">A DLQ está vazia.</p>
        <ul v-else class="dlq">
          <li v-for="(d, i) in dados.dlq" :key="i">
            <span class="selo critico">{{ d.motivo ?? 'rejeitada' }}</span>
            <code>{{ d.origem }}</code>
            <pre>{{ d.corpo }}</pre>
          </li>
        </ul>
      </section>
    </div>

    <section class="painel">
      <h2>Últimas mensagens (formato único)</h2>
      <div class="tabela-rolavel">
        <table>
          <thead>
            <tr><th>Instante</th><th>Routing key</th><th>Tipo</th><th>Dispositivo</th><th>Conteúdo</th></tr>
          </thead>
          <tbody>
            <tr v-for="m in dados?.recentes ?? []" :key="m.id">
              <td class="suave">{{ hora(m.instante) }}</td>
              <td><code>{{ m.routing_key }}</code></td>
              <td>{{ m.tipo }}</td>
              <td>{{ m.dispositivo ?? '—' }}</td>
              <td><code class="conteudo">{{ JSON.stringify(m.conteudo) }}</code></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<style scoped>
tr.parada td {
  background: #fdf3f2;
}

.tendencia {
  width: 100px;
  height: 20px;
}

.tendencia polyline {
  fill: none;
  stroke: var(--primaria);
  stroke-width: 1.5;
}

.dlq {
  list-style: none;
  padding: 0;
  margin: 0.6rem 0 0;
  display: grid;
  gap: 0.6rem;
}

.dlq li {
  display: grid;
  gap: 0.25rem;
  justify-items: start;
}

pre {
  margin: 0;
  max-width: 100%;
  overflow-x: auto;
  font-size: 0.78rem;
  background: var(--superficie-2);
  padding: 0.4rem 0.5rem;
  border-radius: 4px;
}

.conteudo {
  display: inline-block;
  max-width: 460px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: bottom;
}
</style>
