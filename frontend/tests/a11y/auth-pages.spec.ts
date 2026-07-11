import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

test.describe('accessibility — auth pages', () => {
  test('login page has no detectable a11y violations', async ({ page }) => {
    await page.goto('/login');
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });

  test('register page has no detectable a11y violations', async ({ page }) => {
    await page.goto('/register');
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });
});
