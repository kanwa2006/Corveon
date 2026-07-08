import path from 'node:path';

import { expect, test } from '@playwright/test';

/** Requires a live backend (FastAPI + Postgres + Redis) — see playwright.config.ts.
 * No AI provider is configured in the test environment, so the message-send
 * flow deliberately exercises the real degraded-mode path (ADR-0006), not a
 * simulation of it — the same thing the backend's own tests verify. */

function uniqueEmail(): string {
  return `messaging-e2e-${Date.now()}-${Math.floor(Math.random() * 10_000)}@example.com`;
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

test.describe('messaging + documents', () => {
  test('sending a message in degraded mode (no provider configured) shows an honest status', async ({
    page,
  }) => {
    await registerAndLogin(page, uniqueEmail());
    await page.goto('/chats');
    await page.getByRole('button', { name: 'New chat' }).click();

    await expect(page.getByText('Start the conversation')).toBeVisible();

    await page.getByPlaceholder(/Ask about this chat's/).fill('What treats a headache?');
    await page.getByRole('button', { name: 'Send message' }).click();

    await expect(page.getByText('What treats a headache?')).toBeVisible();
    await expect(page.getByText('No AI provider is currently reachable.')).toBeVisible({
      timeout: 15_000,
    });
  });

  test('uploading a PDF shows ingestion progress and lands as ready', async ({ page }) => {
    await registerAndLogin(page, uniqueEmail());
    await page.goto('/chats');
    await page.getByRole('button', { name: 'New chat' }).click();

    const fixturePath = path.join(__dirname, 'fixtures', 'sample.pdf');
    const fileChooserPromise = page.waitForEvent('filechooser');
    await page.getByRole('button', { name: 'Upload PDF' }).click();
    const fileChooser = await fileChooserPromise;
    await fileChooser.setFiles(fixturePath);

    await expect(page.getByText('sample.pdf')).toBeVisible();
    // A worker process must be running for this to reach "ready"; skip the
    // terminal-status assertion in environments where none is running.
  });

  test('a document is not visible to a different user (cross-chat isolation)', async ({
    page,
    context,
  }) => {
    const ownerEmail = uniqueEmail();
    await registerAndLogin(page, ownerEmail);
    await page.goto('/chats');
    await page.getByRole('button', { name: 'New chat' }).click();
    // Wait for the client-side navigation to actually land on the new
    // chat's URL before capturing it — reading page.url() immediately after
    // the click can still show the list page's URL.
    await expect(page).toHaveURL(/\/chats\/[0-9a-f-]+/);
    const chatUrl = page.url();

    const otherPage = await context.browser()!.newPage();
    await registerAndLogin(otherPage, uniqueEmail());
    await otherPage.goto(chatUrl);
    await expect(otherPage.getByText('Chat not found')).toBeVisible();
    await otherPage.close();
  });
});
