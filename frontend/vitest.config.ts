import { defineConfig, mergeConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import viteConfig from './vite.config';

export default mergeConfig(
  viteConfig,
  defineConfig({
    plugins: [react({ jsxRuntime: 'automatic' })],
    esbuild: {
      jsx: 'automatic',
    },
    test: {
      environment: 'node',
      include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
      setupFiles: ['./src/test/setup.ts'],
    },
  }),
);
