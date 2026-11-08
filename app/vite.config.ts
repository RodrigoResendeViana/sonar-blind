import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      injectRegister: 'script-defer',
      includeAssets: ['icone.svg', 'icone-192.png'],
      manifest: {
        name: 'Sonar',
        short_name: 'Sonar',
        description: 'Pegue o ônibus certo sem depender de um desconhecido.',
        lang: 'pt-BR',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        background_color: '#0b1020',
        theme_color: '#0b1020',
        icons: [
          { src: '/icone-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icone-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/icone-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        navigateFallback: '/index.html',
        // a API, o SSE e as métricas nunca passam pelo cache do service worker
        navigateFallbackDenylist: [/^\/api\//, /^\/healthz/, /^\/metrics/, /^\/node-metrics/],
      },
    }),
  ],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        rewrite: (caminho) => caminho.replace(/^\/api/, ''),
      },
    },
  },
})
