import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/tests/setup.js',
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      exclude: [
        'dist/**',
        'vite.config.js',
        'vitest.config.js',
        'extension/**',
        'src/tests/**',
        'node_modules/**',
        'src/main.jsx',
        'src/pages/Nebula.jsx',
        'src/pages/BranchingPOC.jsx',
        'src/canvas/NebulaCanvas.jsx',
        'src/canvas/GraphCanvas.jsx',
        'src/canvas/Graph3DScene.jsx',
        'src/canvas/GraphEdge3D.jsx',
        'src/canvas/GraphNode3D.jsx',
        'src/components/GraphCanvas.jsx',
        'src/components/GraphControls.jsx',
        'src/hooks/useGraphSocket.js'
      ],
      thresholds: {
        statements: 70,
        branches: 70,
        functions: 45,
        lines: 70
      }
    }
  }
});
