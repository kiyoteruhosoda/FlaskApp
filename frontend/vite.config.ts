import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 3000,
    host: true, // 外部からのアクセスを許可
    strictPort: true, // ポートが使用中の場合エラーにする
    open: false, // ブラウザを自動的に開かない
    cors: true, // CORSを有効化
    proxy: {
      // Flask APIサーバーへのプロキシ
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true,
        secure: false,
        ws: true, // WebSocketサポート
        configure: (proxy, options) => {
          // プロキシのリクエスト/レスポンスをログ出力
          proxy.on('proxyReq', (proxyReq, req, res) => {
            console.log(`[Proxy] ${req.method} ${req.url} -> ${options.target}${req.url}`);
          });
          proxy.on('proxyRes', (proxyRes, req, res) => {
            console.log(`[Proxy] ${req.method} ${req.url} <- ${proxyRes.statusCode}`);
          });
          proxy.on('error', (err, req, res) => {
            console.error(`[Proxy Error] ${req.method} ${req.url}:`, err.message);
          });
        },
      },
      // 認証関連のルートもプロキシ
      '/auth': {
        target: 'http://localhost:5000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
  build: {
    outDir: 'build',
    sourcemap: true,
    // チャンクサイズの警告を抑制
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
          redux: ['@reduxjs/toolkit', 'react-redux'],
          bootstrap: ['react-bootstrap', 'bootstrap'],
          utils: ['axios', 'i18next', 'react-i18next'],
        },
      },
    },
  },
  define: {
    global: 'globalThis',
  },
  // 依存関係の最適化
  optimizeDeps: {
    include: [
      'react',
      'react-dom',
      'react-router-dom',
      '@reduxjs/toolkit',
      'react-redux',
      'axios',
      'i18next',
      'react-i18next',
    ],
  },
})