import { expect, test } from '@playwright/test';

import { INTERACTING_MEDICATION_LIST } from './fixtures/medications';

/** Requires a live backend (FastAPI + Postgres + Redis) — see playwright.config.ts.
 * No AI provider is configured in the test environment, so this exercises
 * the real degraded-mode path (ADR-0006) for the medication-safety
 * analyzer's free-text parsing step, matching messaging.spec.ts's own
 * degraded-mode convention. */

function uniqueEmail(): string {
  return `medication-e2e-${Date.now()}-${Math.floor(Math.random() * 10_000)}@example.com`;
}

const PASSWORD = 'correcthorsebattery';

async function registerAndLogin(
  page: import('@playwright/test').Page,
  email: string,
): Promise<void> {
  await page.goto('/register');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD);
  await page.getByLabel('Confirm password').fill(PASSWORD);
  await page.getByRole('button', { name: 'Create account' }).click();
  await expect(page).toHaveURL(/\/login/);

  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/dashboard/);
}

test.describe('medication safety', () => {
  test('checking for interactions in degraded mode (no provider configured) shows an honest status', async ({
    page,
  }) => {
    await registerAndLogin(page, uniqueEmail());
    await page.goto('/chats');
    await page.getByRole('button', { name: 'New chat' }).click();
    await expect(page).toHaveURL(/\/chats\/[0-9a-f-]+/);

    await page.getByPlaceholder(/List medications, one per line/).fill(INTERACTING_MEDICATION_LIST);
    await page.getByRole('button', { name: 'Check for interactions' }).click();

    await expect(page.getByText('No AI provider is currently reachable.')).toBeVisible({
      timeout: 15_000,
    });
  });

  test('the trigger is disabled until a medication list is entered', async ({ page }) => {
    await registerAndLogin(page, uniqueEmail());
    await page.goto('/chats');
    await page.getByRole('button', { name: 'New chat' }).click();
    await expect(page).toHaveURL(/\/chats\/[0-9a-f-]+/);

    await expect(page.getByRole('button', { name: 'Check for interactions' })).toBeDisabled();
    await page.getByPlaceholder(/List medications, one per line/).fill('metformin');
    await expect(page.getByRole('button', { name: 'Check for interactions' })).toBeEnabled();
  });
});
