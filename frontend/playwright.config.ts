import { defineConfig, devices } from '@playwright/test';

/**
 * Requires the backend (FastAPI + Postgres + Redis) reachable at
 * NEXT_PUBLIC_API_BASE_URL, and starts the frontend dev server itself.
 * Not yet wired into CI — full-stack orchestration (backend + DB + Redis +
 * frontend together) is a separate, larger infra task tracked for follow-up.
 */
export default defineConfig({
  testDir: './tests',
  testMatch: ['e2e/**/*.spec.ts', 'a11y/**/*.spec.ts'],
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'pnpm build && pnpm start',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
