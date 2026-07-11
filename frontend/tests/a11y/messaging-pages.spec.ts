import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

function uniqueEmail(): string {
  return `messaging-a11y-${Date.now()}-${Math.floor(Math.random() * 10_000)}@example.com`;
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

test.describe('accessibility — chat detail page (messages + documents)', () => {
  test('chat detail page has no detectable a11y violations', async ({ page }) => {
    await registerAndLogin(page, uniqueEmail());

    await page.goto('/chats');
    await page.getByRole('button', { name: 'New chat' }).click();
    await expect(page).toHaveURL(/\/chats\/[0-9a-f-]+/);

    const emptyStateResults = await new AxeBuilder({ page }).analyze();
    expect(emptyStateResults.violations).toEqual([]);

    // Send a message (degraded mode in the test env — no AI provider
    // configured) so the a11y check also covers the message-thread state.
    await page.getByPlaceholder(/Ask about this chat's/).fill('What treats a headache?');
    await page.getByRole('button', { name: 'Send message' }).click();
    const providerNotice = page.getByText('No AI provider is currently reachable.');
    await expect(providerNotice).toBeVisible({ timeout: 15_000 });

    // The message bubble fades in (Framer Motion animates the wrapping
    // motion.div's inline `opacity` 0 -> 1); wait for that transition to
    // settle before scanning, otherwise axe can sample a mid-transition
    // frame and report a false-positive color-contrast violation.
    await expect(async () => {
      const opacity = await providerNotice.evaluate((el) => {
        let ancestor: HTMLElement | null = el as HTMLElement;
        while (ancestor && ancestor.style.opacity === '') {
          ancestor = ancestor.parentElement;
        }
        return ancestor?.style.opacity ?? '1';
      });
      expect(opacity).toBe('1');
    }).toPass({ timeout: 2_000 });

    const threadResults = await new AxeBuilder({ page }).analyze();
    expect(threadResults.violations).toEqual([]);
  });
});
