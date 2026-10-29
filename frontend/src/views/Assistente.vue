<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import { enviarStream, get } from '../api'
import { markdownSeguro } from '../formatacao'

interface Mensagem {
  autor: 'voce' | 'assistente'
  texto: string
  erro?: boolean
}

const mensagens = ref<Mensagem[]>([])
const pergunta = ref('')
const respondendo = ref(false)
const status = ref<{ modelo: string; estado: 'pronto' | 'carregando' | 'baixando' | 'indisponivel' } | null>(null)
const historico = ref<HTMLElement | null>(null)

const SUGESTOES = [
  'Qual equipamento está com a pior saúde agora?',
  'O que significa o alerta aberto e o que devo fazer?',
  'Explique as métricas do último treino em palavras simples.',
  'Como os dados fluem pela arquitetura e por que usamos RabbitMQ e MQTT?',
]

const TEXTO_STATUS = {
  pronto: 'Modelo carregado',
  carregando: 'Carregando o modelo na memória…',
  baixando: 'Baixando o modelo (primeira vez)…',
  indisponivel: 'LLM local indisponível',
}

async function verificarStatus() {
  try {
    status.value = await get('/api/assistente/status')
  } catch {
    status.value = null
  }
}

async function rolar() {
  await nextTick()
  historico.value?.scrollTo({ top: historico.value.scrollHeight })
}

async function perguntar(texto = pergunta.value) {
  texto = texto.trim()
  if (!texto || respondendo.value) return
  pergunta.value = ''
  mensagens.value.push({ autor: 'voce', texto })
  const resposta: Mensagem = { autor: 'assistente', texto: '' }
  mensagens.value.push(resposta)
  const indice = mensagens.value.length - 1
  respondendo.value = true
  rolar()
  try {
    await enviarStream('/api/assistente/perguntar', { pergunta: texto }, (parte) => {
      mensagens.value[indice].texto += parte
      rolar()
    })
    if (!mensagens.value[indice].texto) mensagens.value[indice].texto = 'O modelo não devolveu resposta. Tente de novo.'
  } catch (e) {
    mensagens.value[indice] = { autor: 'assistente', texto: (e as Error).message, erro: true }
  } finally {
    respondendo.value = false
    verificarStatus()
  }
}

let temporizador: number | undefined
onMounted(() => {
  verificarStatus()
  temporizador = window.setInterval(verificarStatus, 8000)
})
onUnmounted(() => window.clearInterval(temporizador))
</script>

<template>
  <div class="pagina">
    <header class="cabecalho-pagina">
      <div>
        <h1>Assistente</h1>
        <p>Perguntas em linguagem natural sobre os dados da casa, respondidas por um LLM rodando localmente (Ollama), sem nuvem.</p>
      </div>
      <span v-if="status" class="selo" :class="status.estado">{{ TEXTO_STATUS[status.estado] }} · {{ status.modelo }}</span>
    </header>

    <section class="painel chat">
      <div ref="historico" class="historico" aria-live="polite">
        <div v-if="!mensagens.length" class="vazio">
          <p class="suave">A API monta um resumo dos dados atuais (leituras, saúde, alertas e métricas) e envia junto com a sua pergunta.</p>
          <div class="sugestoes">
            <button v-for="s in SUGESTOES" :key="s" class="secundario" :disabled="respondendo" @click="perguntar(s)">{{ s }}</button>
          </div>
        </div>
        <div v-for="(m, i) in mensagens" :key="i" class="mensagem" :class="m.autor">
          <span class="autor">{{ m.autor === 'voce' ? 'Você' : 'Assistente' }}</span>
          <p v-if="m.autor === 'voce'">{{ m.texto }}</p>
          <p v-else-if="m.erro" class="aviso erro">{{ m.texto }}</p>
          <div v-else-if="m.texto" class="resposta" v-html="markdownSeguro(m.texto)"></div>
          <p v-else class="suave">
            {{ status?.estado === 'pronto' ? 'Pensando…' : 'Aguardando o modelo local; a primeira resposta pode demorar.' }}
          </p>
        </div>
      </div>
      <form class="entrada" @submit.prevent="perguntar()">
        <label class="visualmente-oculto" for="pergunta">Pergunta</label>
        <input id="pergunta" v-model="pergunta" placeholder="Pergunte sobre leituras, alertas, previsões ou a arquitetura" maxlength="1000" :disabled="respondendo" />
        <button type="submit" :disabled="respondendo || !pergunta.trim()">Perguntar</button>
      </form>
      <p class="suave">Limite de perguntas por minuto por usuário; cada pergunta fica registrada na auditoria.</p>
    </section>
  </div>
</template>

<style scoped>
.chat {
  display: grid;
  gap: 0.75rem;
}

.historico {
  height: min(60vh, 560px);
  overflow-y: auto;
  display: grid;
  align-content: start;
  gap: 0.9rem;
  padding-right: 0.25rem;
}

.sugestoes {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.sugestoes button {
  font-weight: 500;
  text-align: left;
}

.mensagem {
  max-width: 78ch;
  display: grid;
  gap: 0.2rem;
}

.mensagem.voce {
  justify-self: end;
  background: #e6f1f4;
  padding: 0.5rem 0.8rem;
  border-radius: 10px 10px 2px 10px;
}

.mensagem p {
  margin: 0;
}

.autor {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--tinta-suave);
}

.resposta :deep(p) {
  margin: 0 0 0.45rem;
}

.resposta :deep(ul),
.resposta :deep(ol) {
  margin: 0 0 0.45rem;
  padding-left: 1.2rem;
}

.entrada {
  display: flex;
  gap: 0.5rem;
}

.visualmente-oculto {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}
</style>
