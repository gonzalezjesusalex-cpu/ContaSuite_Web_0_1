import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// API port for the development proxy: CS_PORT (set by scripts/dev.mjs) or 8090, a port reserved for
// development so it never reaches the pilot (8062), the local install (8072) or the old instance (8000).
const apiPort = process.env.CS_PORT || '8090';

export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: false } } },
});
