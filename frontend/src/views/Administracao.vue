<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { get } from '../api'
import { dataHora } from '../formatacao'

interface Link {
  nome: string
  url: string
  usuario: string | null
}
interface Registro {
  id: number
  instante: string
  usuario: string | null
  acao: string
  detalhe: Record<string, unknown>
}

const links = ref<Link[]>([])
const auditoria = ref<Registro[]>([])
const filtro = ref('')
const erro = ref('')

const ACOES: Record<string, string> = {
  login: 'Login',
  login_falhou: 'Login recusado',
  login_bloqueado: 'Login bloqueado',
  comando: 'Comando',
  comando_simulador: 'Comando ao simulador',
  job_geracao: 'Job de geração',
  job_treino: 'Job de treino',
  pergunta_assistente: 'Pergunta ao assistente',
  dispositivo_criado: 'Dispositivo criado',
  dispositivo_alterado: 'Dispositivo alterado',
  dispositivo_removido: 'Dispositivo removido',
  regra_alterada: 'Regra alterada',
  teste_dlq: 'Teste da DLQ',
}

async function carregar() {
  try {
    links.value = await get<Link[]>('/api/infra')
    auditoria.value = await get<Registro[]>('/api/auditoria?limite=300')
  } catch (e) {
    erro.value = (e as Error).message
  }
}

function filtrados() {
  const f = filtro.value.toLowerCase()
  return auditoria.value.filter((r) => !f || `${r.usuario} ${r.acao} ${JSON.stringify(r.detalhe)}`.toLowerCase().includes(f))
}

onMounted(carregar)
</script>

<template>
  <div class="pagina">
    <header class="cabecalho-pagina">
      <div>
        <h1>Administração</h1>
        <p>Interfaces de estudo da infraestrutura e log de auditoria do PostgreSQL.</p>
      </div>
    </header>
    <p v-if="erro" class="aviso erro">{{ erro }}</p>

    <section class="painel">
      <h2>Interfaces da infraestrutura</h2>
      <p class="suave">Publicadas só em 127.0.0.1: abrem apenas no computador que roda o Docker. As senhas estão no arquivo <code>.env</code>.</p>
      <table>
        <tbody>
          <tr v-for="l in links" :key="l.url">
            <td>{{ l.nome }}</td>
            <td><a :href="l.url" target="_blank" rel="noopener">{{ l.url }}</a></td>
            <td class="suave">{{ l.usuario ? `usuário ${l.usuario}` : 'login da aplicação' }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="painel">
      <div class="cabecalho-pagina">
        <h2>Auditoria</h2>
        <div class="acoes">
          <input v-model="filtro" placeholder="Filtrar por usuário, ação ou detalhe" aria-label="Filtrar auditoria" />
          <button class="secundario" @click="carregar">Atualizar</button>
        </div>
      </div>
      <div class="tabela-rolavel">
        <table>
          <thead>
            <tr><th>Quando</th><th>Usuário</th><th>Ação</th><th>Detalhe</th></tr>
          </thead>
          <tbody>
            <tr v-for="r in filtrados()" :key="r.id">
              <td class="suave">{{ dataHora(r.instante) }}</td>
              <td>{{ r.usuario ?? '—' }}</td>
              <td>{{ ACOES[r.acao] ?? r.acao }}</td>
              <td><code class="detalhe">{{ JSON.stringify(r.detalhe) }}</code></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<style scoped>
.acoes input {
  width: 280px;
}

.detalhe {
  display: inline-block;
  max-width: 520px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: bottom;
}
</style>
