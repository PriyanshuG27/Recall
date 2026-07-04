import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'Recall',
        short_name: 'Recall',
        description: 'Your AI knowledge constellation',
        theme_color: '#030307',
        background_color: '#030307',
        display: 'standalone',
        orientation: 'any',
        icons: [
          {src: 'icons/icon-192.png', sizes: '192x192', type: 'image/png'},
          {src: 'icons/icon-512.png', sizes: '512x512', type: 'image/png'}
        ],
        share_target: {
          action: '/api/share-target',
          method: 'POST',
          enctype: 'multipart/form-data',
          params: {
            title: 'title',
            text: 'text',
            url: 'url'
          }
        }
      },
      workbox: {
        runtimeCaching: [
          {
            urlPattern: /\/api\/graph/,
            handler: 'StaleWhileRevalidate',
            options: {
              cacheName: 'graph-cache'
            }
          },
          {
            urlPattern: /\/api\/items/,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'items-cache'
            }
          }
        ]
      }
    })
  ],
  build: {
    target: 'esnext',
    minify: 'esbuild',
    modulePreload: {
      resolveDependencies(filename, deps, { hostId }) {
        return deps.filter(dep => !dep.includes('vendor-three'));
      }
    },
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/react') || id.includes('node_modules/react-dom')) {
            return 'vendor-react';
          }
          if (id.includes('node_modules/three') || id.includes('node_modules/@react-three')) {
            return 'vendor-three';
          }
          if (id.includes('node_modules/lucide-react') || id.includes('node_modules/canvas-confetti')) {
            return 'vendor-utils';
          }
        },
      },
    },
  },
  server: {
    port: 5173,
    host: true,
    proxy: {
      '/auth': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true
      }
    }
  }
});
