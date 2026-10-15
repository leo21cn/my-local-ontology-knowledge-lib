import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  build: { outDir: 'dist' },
  server: {
    port: 8100,
    proxy: { '/api': { target: 'http://127.0.0.1:8101', changeOrigin: true } }
  }
})
