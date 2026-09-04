import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': new URL('./src', import.meta.url).pathname,
    },
  },
  // vitest config lives here so CI (`npm run build && npm test`) exercises the
  // same toolchain as the build; environment jsdom for DOM/hook tests.
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
  server: {
    host: '0.0.0.0',
    port: 43123,
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
      '/uploads': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      }
    }
  },
  build: {
    // Fix chunk size warning (655KB > 500KB) - code splitting for luxury mobile performance
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        manualChunks: (id: string) => {
          // Vendor chunks for better caching
          if (id.includes('node_modules/react') || id.includes('node_modules/react-dom') || id.includes('node_modules/react-router')) {
            return 'vendor-react';
          }
          if (id.includes('node_modules/framer-motion') || id.includes('node_modules/zustand') || id.includes('node_modules/@tanstack')) {
            return 'vendor-ui';
          }
          if (id.includes('node_modules/lucide-react')) {
            return 'vendor-icons';
          }
          // B2B heavy views - separate chunk
          if (id.includes('BrandAnalyticsView') || id.includes('AdminAnalyticsView')) {
            return 'b2b-analytics';
          }
        },
      },
    },
  },
})
