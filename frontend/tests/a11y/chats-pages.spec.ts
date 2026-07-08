import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

function uniqueEmail(): string {
  return `chats-a11y-${Date.now()}-${Math.floor(Math.random() * 10_000)}@example.com`;
}

const PASSWORD = 'correcthorsebattery';

test.describe('accessibility — chats pages', () => {
  test('chats list page has no detectable a11y violations', async ({ page }) => {
    const email = uniqueEmail();
    await page.goto('/register');
    await page.getByLabel('Email').fill(email);
    await page.getByLabel('Password', { exact: true }).fill(PASSWORD);
    await page.getByLabel('Confirm password').fill(PASSWORD);
    await page.getByRole('button', { name: 'Create account' }).click();
    // Wait for the redirect to actually land on /login before filling its
    // form — otherwise these fills can race the still-mounted register form
    // (which also has "Email"/"Password" fields) and hit the wrong inputs.
    await expect(page).toHaveURL(/\/login/);
    await page.getByLabel('Email').fill(email);
    await page.getByLabel('Password').fill(PASSWORD);
    await page.getByRole('button', { name: 'Sign in' }).click();

    await page.goto('/chats');
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });
});
