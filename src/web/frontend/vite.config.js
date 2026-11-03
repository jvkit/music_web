import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

// base 用相对路径，保证根路径与 /music 反代前缀下都能加载资源
export default defineConfig({
    plugins: [vue()],
    base: './',
    build: {
        outDir: '../static/dist',
        emptyOutDir: true,
    },
    server: {
        port: 5173,
        proxy: {
            '/api': { target: 'http://127.0.0.1:8001', changeOrigin: true },
            '/manifest.json': { target: 'http://127.0.0.1:8001', changeOrigin: true },
            '/icons': { target: 'http://127.0.0.1:8001', changeOrigin: true },
        },
    },
});
