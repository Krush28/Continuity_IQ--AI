import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In dev, API calls are proxied to FastAPI on :8000. In production FastAPI serves dist/.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { '/api': 'http://127.0.0.1:8000' } },
})
