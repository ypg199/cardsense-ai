import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In Docker the API is reachable as http://api:8000, locally as localhost
const apiTarget = process.env.VITE_PROXY_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/session': apiTarget,
      '/cards': apiTarget,
      '/crawl': apiTarget,
      '/health': apiTarget,
    },
  },
})
