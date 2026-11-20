import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

const backend = process.env.ATTENDFLOW_VITE_PROXY

export default defineConfig({
  plugins: [react()],
  server: { strictPort: true, proxy: backend ? { '/api': { target: backend, changeOrigin: false } } : undefined },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
  },
})
