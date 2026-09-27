import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    // Encaminha /api para o backend Python (evita configurar CORS).
    // 127.0.0.1 em vez de localhost: o Node pode resolver localhost para IPv6.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
