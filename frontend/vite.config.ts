import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Em desenvolvimento (npm run dev) as chamadas vão para a API publicada pelo Compose na porta 8080.
// Em produção o nginx do container frontend faz esse papel.
export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8080',
      '/ws': { target: 'ws://127.0.0.1:8080', ws: true },
    },
  },
  build: { chunkSizeWarningLimit: 1200 },
})
