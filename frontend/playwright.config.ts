import { defineConfig, devices } from '@playwright/test';

const packageRunner = process.platform === 'win32' ? 'npx.cmd' : 'npx';
const host = '127.0.0.1';
const port = process.env.PLAYWRIGHT_PORT || '5173';
const baseURL = process.env.PLAYWRIGHT_BASE_URL || `http://${host}:${port}`;
const reuseExistingServer = process.env.PLAYWRIGHT_REUSE_EXISTING_SERVER === '1';

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: 'html',
  use: {
    baseURL,
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: `${packageRunner} vite --host ${host} --port ${port} --strictPort`,
    url: baseURL,
    reuseExistingServer,
    timeout: 30_000,
  },
});
