import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue(), react()],
  server: {
    proxy: {
      // Proxy /api requests to your FastAPI backend
      '/api': {
        target: 'http://localhost:8010',
        changeOrigin: true,
        secure: false, // Uncomment if your backend is http and you get SSL errors
        // rewrite: (path) => path.replace(/^\/api/, '') // Use if your backend doesn't expect /api prefix
      },
    },
  },
})
