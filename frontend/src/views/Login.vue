<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { enviar } from '../api'
import { entrar } from '../sessao'
import type { Usuario } from '../tipos'

const route = useRoute()
const router = useRouter()
const login = ref('')
const senha = ref('')
const erro = ref(route.query.expirou ? 'Sua sessão expirou. Entre novamente.' : '')
const enviando = ref(false)

async function acessar() {
  enviando.value = true
  erro.value = ''
  try {
    const r = await enviar<{ token: string; usuario: Usuario }>('POST', '/api/auth/login', { login: login.value, senha: senha.value })
    entrar(r.token, r.usuario)
    router.push(typeof route.query.volta === 'string' ? route.query.volta : '/')
  } catch (e) {
    erro.value = (e as Error).message
  } finally {
    enviando.value = false
  }
}
</script>

<template>
  <div class="tela">
    <form class="painel" @submit.prevent="acessar">
      <h1>Smart Home AIoT</h1>
      <p class="suave">Monitoramento residencial com manutenção preditiva do compressor da geladeira.</p>
      <label>
        Usuário
        <input v-model="login" autocomplete="username" required autofocus />
      </label>
      <label>
        Senha
        <input v-model="senha" type="password" autocomplete="current-password" required />
      </label>
      <p v-if="erro" class="aviso erro" role="alert">{{ erro }}</p>
      <button type="submit" :disabled="enviando">{{ enviando ? 'Entrando…' : 'Entrar' }}</button>
      <p class="suave">
        Usuários de demonstração: <code>administrador</code>, <code>operador</code> e <code>visualizador</code>. As senhas são
        geradas pelo script de segredos e ficam no arquivo <code>.env</code>.
      </p>
    </form>
  </div>
</template>

<style scoped>
.tela {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 1rem;
  background: var(--barra);
}

form {
  width: min(380px, 100%);
  display: grid;
  gap: 0.9rem;
  padding: 1.75rem;
}

form p {
  margin: 0;
}
</style>
