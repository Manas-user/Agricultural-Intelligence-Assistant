import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    tailwindcss(),
    react()
  ],

  server: {
    proxy: {
      '/query': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },

      '/ingest': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      }
    }
  }
})