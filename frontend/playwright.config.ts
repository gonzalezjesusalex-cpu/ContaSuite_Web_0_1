import { randomBytes } from 'node:crypto';
import { defineConfig } from '@playwright/test';

// Synthetic credentials, generated once per run in the main process; workers inherit them through the
// environment. They only ever exist for the throwaway server started below.
process.env.E2E_APP_TOKEN ||= randomBytes(24).toString('base64url');
process.env.E2E_PASSWORD ||= randomBytes(18).toString('base64url');
const port = process.env.E2E_PORT || '8097';
process.env.E2E_PORT = port;

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:' + port,
    // Use the browser already installed on the machine (Edge on Windows) instead of downloading one.
    // Set E2E_CHANNEL=chromium (after `npx playwright install chromium`) or chrome to change it.
    channel: process.env.E2E_CHANNEL || 'msedge',
    acceptDownloads: true,
    trace: 'retain-on-failure',
  },
  // The smoke test creates the administrator and the synthetic company through the UI; the other
  // flows log in with that account and run after it on the same throwaway server.
  projects: [
    { name: 'humo', testMatch: /smoke\.spec\.ts/ },
    { name: 'flujos', testIgnore: /smoke\.spec\.ts/, dependencies: ['humo'] },
  ],
  webServer: {
    // E2E_PYTHON: interpreter with backend/requirements-dev.txt installed (default: python).
    command: (process.env.E2E_PYTHON || 'python') + ' ../scripts/e2e_server.py',
    url: 'http://127.0.0.1:' + port + '/api/auth/status',
    reuseExistingServer: false,
    timeout: 120_000,
    env: { ...process.env } as Record<string, string>,
  },
});
