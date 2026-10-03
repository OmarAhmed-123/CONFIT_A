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
          // NOTE (Magic Navigation §5/§8): the old forced 'b2b-analytics'
          // manualChunks rule is intentionally GONE. Forcing the two
          // analytics views into a named chunk made the bundler hoist
          // shared modules (including the i18n catalogues) into it, which
          // turned the chunk into a STATIC dependency of the main bundle —
          // every shopper downloaded ~650KB of partner/governance
          // dashboards eagerly. The views are now React.lazy in
          // AppRoutes.tsx, so each gets its own naturally dynamic chunk
          // and the shared modules stay in the entry bundle.
        },
      },
    },
  },
})
