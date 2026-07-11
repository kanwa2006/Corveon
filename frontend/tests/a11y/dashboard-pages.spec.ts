import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

function uniqueEmail(): string {
  return `dashboard-a11y-${Date.now()}-${Math.floor(Math.random() * 10_000)}@example.com`;
}

const PASSWORD = 'correcthorsebattery';

test.describe('accessibility — dashboard page', () => {
  test('dashboard page has no detectable a11y violations', async ({ page }) => {
    const email = uniqueEmail();
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
    // Wait for the authenticated app shell to actually mount before running
    // axe — otherwise it can catch the brief unauthenticated-check loading
    // state, which has no <main> landmark or h1 yet (same note as
    // tests/a11y/chats-pages.spec.ts).
    await expect(page.getByRole('heading', { name: /welcome/i })).toBeVisible();

    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });
});
