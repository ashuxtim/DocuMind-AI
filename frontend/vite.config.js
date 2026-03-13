import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://documind.local',  // Your Ingress host
        changeOrigin: true,
        // ⚠️ DO NOT use rewrite here!
        // Ingress already strips /api → FastAPI gets /health etc.
        // Double-rewriting would break it.
      },
    },
  },
})
