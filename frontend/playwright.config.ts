import { defineConfig, devices } from '@playwright/test';

/**
 * Requires the backend (FastAPI + Postgres + Redis) reachable at
 * NEXT_PUBLIC_API_BASE_URL. Wired into CI as the `e2e` job in
 * .github/workflows/ci.yml, which starts Postgres+Redis services, the
 * FastAPI backend, and the ARQ worker before this config's own `webServer`
 * builds and starts the frontend.
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
