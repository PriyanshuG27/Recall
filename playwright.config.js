import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 30000,
  expect: {
    timeout: 5000,
  },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: 'line',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'Mobile Safari',
      use: { ...devices['iPhone 12'] },
    },
  ],
  webServer: [
    {
      command: 'npm run dev --prefix frontend',
      port: 5173,
      reuseExistingServer: !process.env.CI,
      timeout: 120000,
    },
    {
      command: '.venv\\Scripts\\python -m uvicorn backend.main:app --port 8000',
      port: 8000,
      reuseExistingServer: !process.env.CI,
      timeout: 120000,
    }
  ],
});
