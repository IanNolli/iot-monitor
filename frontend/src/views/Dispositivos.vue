<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { enviar, get } from '../api'
import { ehAdmin } from '../sessao'
import { recarregarDispositivos, ROTULO_STATUS, statusDe, tempoReal } from '../tempoReal'
import type { Dispositivo } from '../tipos'

interface Regra {
  id: number
  nome: string
  sensor_id: string
  atuador_id: string
  limite_liga: number
  limite_desliga: number
  ativa: boolean
}

const VAZIO: Dispositivo = {
  id: '', nome: '', classe: 'sensor', zona: 'sala', grandeza: '', unidade: '',
  faixa_min: null, faixa_max: null, controlavel: false, ativo: true,
}
const formulario = reactive<Dispositivo>({ ...VAZIO })
const editando = ref<string | null>(null)
const mostrarFormulario = ref(false)
const erro = ref('')
const regras = ref<Regra[]>([])
const mensagemRegra = ref('')

async function carregarRegras() {
  regras.value = await get<Regra[]>('/api/regras')
}

function novo() {
  Object.assign(formulario, VAZIO)
  editando.value = null
  mostrarFormulario.value = true
  erro.value = ''
}

function editar(d: Dispositivo) {
  Object.assign(formulario, d)
  editando.value = d.id
  mostrarFormulario.value = true
  erro.value = ''
}

async function salvar() {
  erro.value = ''
  try {
    const corpo = { ...formulario, faixa_min: formulario.faixa_min ?? null, faixa_max: formulario.faixa_max ?? null }
    if (editando.value) await enviar('PUT', `/api/dispositivos/${editando.value}`, corpo)
    else await enviar('POST', '/api/dispositivos', corpo)
    mostrarFormulario.value = false
    await recarregarDispositivos()
  } catch (e) {
    erro.value = (e as Error).message
  }
}

async function remover(d: Dispositivo) {
  if (!window.confirm(`Remover o dispositivo ${d.nome}? As regras ligadas a ele também serão removidas.`)) return
  try {
    await enviar('DELETE', `/api/dispositivos/${d.id}`)
    await recarregarDispositivos()
    await carregarRegras()
  } catch (e) {
    erro.value = (e as Error).message
  }
}

async function salvarRegra(r: Regra) {
  mensagemRegra.value = ''
  try {
    await enviar('PUT', `/api/regras/${r.id}`, { limite_liga: r.limite_liga, limite_desliga: r.limite_desliga, ativa: r.ativa })
    mensagemRegra.value = 'Regra salva e aplicada imediatamente.'
  } catch (e) {
    mensagemRegra.value = (e as Error).message
  }
}

function ultimaLeitura(id: string): string {
  const c = tempoReal.leituras[id]?.conteudo
  if (!c) return '—'
  if ('ligado' in c) return c.ligado ? 'ligado' : 'desligado'
  if ('valor' in c) return `${c.valor} ${c.unidade ?? ''}`
  return ['vibracao', 'corrente', 'temperatura'].map((k) => `${k} ${c[k] ?? '—'}`).join(' · ')
}

onMounted(async () => {
  await recarregarDispositivos()
  await carregarRegras()
})
</script>

<template>
  <div class="pagina">
    <header class="cabecalho-pagina">
      <div>
        <h1>Dispositivos e regras</h1>
        <p>Cadastro dos dispositivos IoT (PostgreSQL). O id é o mesmo usado nos tópicos MQTT, nas routing keys e na cena 3D.</p>
      </div>
      <button v-if="ehAdmin" @click="novo">Cadastrar dispositivo</button>
    </header>

    <p v-if="erro && !mostrarFormulario" class="aviso erro">{{ erro }}</p>

    <section v-if="mostrarFormulario" class="painel">
      <h2>{{ editando ? `Alterar ${editando}` : 'Novo dispositivo' }}</h2>
      <form @submit.prevent="salvar">
        <div class="campos">
          <label>Id <input v-model="formulario.id" :disabled="!!editando" required pattern="[a-z0-9-]{2,40}" title="letras minúsculas, números e hífen" /></label>
          <label>Nome <input v-model="formulario.nome" required minlength="2" /></label>
          <label>
            Classe
            <select v-model="formulario.classe">
              <option value="sensor">Sensor</option>
              <option value="atuador">Atuador</option>
              <option value="equipamento">Equipamento monitorado</option>
            </select>
          </label>
          <label>Zona <input v-model="formulario.zona" required pattern="[a-z0-9-]{2,30}" /></label>
          <label>Grandeza <input v-model="formulario.grandeza" required placeholder="temperatura, umidade…" /></label>
          <label>Unidade <input v-model="formulario.unidade" maxlength="10" /></label>
          <label>Faixa normal mínima <input v-model.number="formulario.faixa_min" type="number" step="any" /></label>
          <label>Faixa normal máxima <input v-model.number="formulario.faixa_max" type="number" step="any" /></label>
          <label class="opcao"><input v-model="formulario.controlavel" type="checkbox" /> Controlável pela Web</label>
          <label class="opcao"><input v-model="formulario.ativo" type="checkbox" /> Ativo</label>
        </div>
        <p v-if="erro" class="aviso erro" style="margin-top: 0.75rem">{{ erro }}</p>
        <div class="acoes" style="margin-top: 0.9rem">
          <button type="submit">Salvar</button>
          <button type="button" class="secundario" @click="mostrarFormulario = false">Cancelar</button>
        </div>
      </form>
    </section>

    <section class="painel">
      <h2>Dispositivos cadastrados</h2>
      <div class="tabela-rolavel">
        <table>
          <thead>
            <tr>
              <th>Id</th><th>Nome</th><th>Classe</th><th>Zona</th><th>Faixa normal</th><th>Estado</th><th>Última leitura</th>
              <th v-if="ehAdmin"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="d in tempoReal.dispositivos" :key="d.id">
              <td><code>{{ d.id }}</code></td>
              <td>{{ d.nome }}<span v-if="d.controlavel" class="suave"> · controlável</span><span v-if="!d.ativo" class="suave"> · inativo</span></td>
              <td>{{ d.classe }}</td>
              <td>{{ d.zona }}</td>
              <td>{{ d.faixa_min !== null && d.faixa_max !== null ? `${d.faixa_min} a ${d.faixa_max} ${d.unidade}` : '—' }}</td>
              <td><span class="selo" :class="statusDe(d.id)">{{ ROTULO_STATUS[statusDe(d.id)] }}</span></td>
              <td class="suave">{{ ultimaLeitura(d.id) }}</td>
              <td v-if="ehAdmin" class="acoes">
                <button class="secundario" @click="editar(d)">Alterar</button>
                <button class="secundario" @click="remover(d)">Remover</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="painel">
      <h2>Regras de negócio</h2>
      <p class="suave">A regra liga o atuador acima do limite e só desliga abaixo do limite inferior (histerese), para não ficar ligando e desligando.</p>
      <table>
        <thead>
          <tr><th>Regra</th><th>Sensor → atuador</th><th>Liga acima de</th><th>Desliga abaixo de</th><th>Ativa</th><th v-if="ehAdmin"></th></tr>
        </thead>
        <tbody>
          <tr v-for="r in regras" :key="r.id">
            <td>{{ r.nome }}</td>
            <td><code>{{ r.sensor_id }}</code> → <code>{{ r.atuador_id }}</code></td>
            <td><input v-model.number="r.limite_liga" type="number" step="0.5" :disabled="!ehAdmin" class="curto" /></td>
            <td><input v-model.number="r.limite_desliga" type="number" step="0.5" :disabled="!ehAdmin" class="curto" /></td>
            <td><input v-model="r.ativa" type="checkbox" :disabled="!ehAdmin" class="caixa" /></td>
            <td v-if="ehAdmin"><button class="secundario" @click="salvarRegra(r)">Salvar</button></td>
          </tr>
        </tbody>
      </table>
      <p v-if="mensagemRegra" class="aviso info" style="margin-top: 0.75rem">{{ mensagemRegra }}</p>
    </section>
  </div>
</template>

<style scoped>
label.opcao {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  color: var(--tinta);
}

label.opcao input,
input.caixa {
  width: auto;
}

input.curto {
  width: 6rem;
}

td.acoes {
  flex-wrap: nowrap;
}
</style>
