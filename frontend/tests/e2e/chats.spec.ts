import { expect, test } from '@playwright/test';

/** Requires a live backend (FastAPI + Postgres + Redis) — see playwright.config.ts. */

function uniqueEmail(): string {
  return `chats-e2e-${Date.now()}-${Math.floor(Math.random() * 10_000)}@example.com`;
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

test.describe('chats', () => {
  test('create, rename, pin, archive, and delete a chat', async ({ page }) => {
    await registerAndLogin(page, uniqueEmail());

    await page.goto('/chats');
    await expect(page.getByText('Start your first chat')).toBeVisible();

    await page.getByRole('button', { name: 'New chat' }).click();
    await expect(page).toHaveURL(/\/chats\/[0-9a-f-]+/);
    await expect(page.getByRole('button', { name: 'Rename chat' })).toHaveText('New chat');

    // Rename
    await page.getByRole('button', { name: 'Rename chat' }).click();
    const titleInput = page.getByLabel('Chat title');
    await titleInput.fill('Renal dosing question');
    await titleInput.press('Enter');
    // Not getByText — the (hidden, closed) delete-confirmation dialog further
    // down the DOM also contains this title in its description text.
    await expect(page.getByRole('button', { name: 'Rename chat' })).toHaveText(
      'Renal dosing question',
    );

    // Pin
    await page.getByRole('button', { name: 'Pin chat' }).click();
    await expect(page.getByRole('button', { name: 'Unpin chat' })).toBeVisible();

    // Archive
    await page.getByRole('button', { name: 'Archive chat' }).click();
    await expect(page.getByRole('button', { name: 'Unarchive chat' })).toBeVisible();

    // Back to list — archived chat hidden from the default view
    await page.getByRole('link', { name: 'Back to chats' }).click();
    await expect(page.getByText('Start your first chat')).toBeVisible();

    // Archived tab shows it, pinned. Scoped to the list-item link — its own
    // (hidden, closed) delete-confirmation dialog also contains this title.
    await page.getByRole('tab', { name: 'Archived' }).click();
    await expect(page.getByRole('link', { name: 'Renal dosing question' })).toBeVisible();

    // Delete via the list item's menu
    await page.getByRole('button', { name: /Actions for/ }).click();
    await page.getByRole('menuitem', { name: 'Delete' }).click();
    await page.getByRole('button', { name: 'Delete' }).last().click();
    await expect(page.getByText('No archived chats')).toBeVisible();
  });

  test('search filters the chat list by title', async ({ page }) => {
    await registerAndLogin(page, uniqueEmail());

    await page.goto('/chats');
    await page.getByRole('button', { name: 'New chat' }).click();
    await page.getByRole('button', { name: 'Rename chat' }).click();
    await page.getByLabel('Chat title').fill('Renal dosing question');
    await page.getByLabel('Chat title').press('Enter');

    await page.getByRole('link', { name: 'Back to chats' }).click();
    await page.getByRole('button', { name: 'New chat' }).click();
    await page.getByRole('link', { name: 'Back to chats' }).click();

    // Scoped to the list-item link (not getByText) — the page header also has
    // a persistent "New chat" button with the same text, and each list item's
    // own (hidden, closed) delete-confirmation dialog repeats its title in
    // its description text, both of which would otherwise make a plain
    // getByText(...) locator ambiguous.
    await expect(page.getByRole('link', { name: 'Renal dosing question' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'New chat' })).toBeVisible();

    await page.getByPlaceholder('Search chats…').fill('renal');
    await expect(page.getByRole('link', { name: 'Renal dosing question' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'New chat' })).not.toBeVisible();
  });

  test('a chat is not visible to a different user', async ({ page, context }) => {
    const ownerEmail = uniqueEmail();
    await registerAndLogin(page, ownerEmail);
    await page.goto('/chats');
    await page.getByRole('button', { name: 'New chat' }).click();
    // Wait for the client-side navigation to actually land on the new
    // chat's URL before capturing it — reading page.url() immediately after
    // the click can still show the list page's URL.
    await expect(page).toHaveURL(/\/chats\/[0-9a-f-]+/);
    const chatUrl = page.url();

    // Fresh, unauthenticated context — a different user.
    const otherPage = await context.browser()!.newPage();
    await registerAndLogin(otherPage, uniqueEmail());
    await otherPage.goto(chatUrl);
    await expect(otherPage.getByText('Chat not found')).toBeVisible();
    await otherPage.close();
  });
});
