import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/session': 'http://localhost:8000',
      '/cards':   'http://localhost:8000',
      '/crawl':   'http://localhost:8000',
      '/health':  'http://localhost:8000',
    }
  }
})
