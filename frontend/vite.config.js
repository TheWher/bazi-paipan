import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../static/ziwei',
    lib: {
      entry: './src/main.jsx',
      name: 'DestinyZiwei',
      formats: ['iife'],
      fileName: () => 'ziwei-chart.js',
    },
    rollupOptions: {
      external: [],
      output: {
        globals: {},
        assetFileNames: 'ziwei-chart.[ext]',
      },
    },
  },
});
