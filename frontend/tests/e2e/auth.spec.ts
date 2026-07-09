import { expect, test } from '@playwright/test';

/** Requires a live backend (FastAPI + Postgres + Redis) — see playwright.config.ts. */

function uniqueEmail(): string {
  return `e2e-${Date.now()}-${Math.floor(Math.random() * 10_000)}@example.com`;
}

const PASSWORD = 'correcthorsebattery';

test.describe('auth flow', () => {
  test('unauthenticated user visiting /dashboard is redirected to /login', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page).toHaveURL(/\/login/);
  });

  test('register -> redirected to login -> login -> lands on dashboard -> logout', async ({
    page,
  }) => {
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
    // Scoped to the welcome heading — the email also appears in the app-shell
    // nav, which would otherwise make a plain getByText(email) ambiguous.
    await expect(page.getByRole('heading', { name: new RegExp(`Welcome, ${email}`) })).toBeVisible();
    await expect(page.getByText('Start your first chat')).toBeVisible();

    await page.getByRole('button', { name: 'Sign out' }).click();
    await expect(page).toHaveURL(/\/login/);

    // Session is really gone, not just a client-side navigation.
    await page.goto('/dashboard');
    await expect(page).toHaveURL(/\/login/);
  });

  test('login with wrong password shows an inline error', async ({ page }) => {
    const email = uniqueEmail();

    await page.goto('/register');
    await page.getByLabel('Email').fill(email);
    await page.getByLabel('Password', { exact: true }).fill(PASSWORD);
    await page.getByLabel('Confirm password').fill(PASSWORD);
    await page.getByRole('button', { name: 'Create account' }).click();
    await expect(page).toHaveURL(/\/login/);

    await page.getByLabel('Email').fill(email);
    await page.getByLabel('Password').fill('the-wrong-password');
    await page.getByRole('button', { name: 'Sign in' }).click();

    // Scoped past Next.js's own route-announcer element, which also carries
    // role="alert" and would otherwise make this locator ambiguous.
    await expect(
      page.getByRole('alert').filter({ hasText: 'Incorrect email or password' }),
    ).toContainText('Incorrect email or password');
    await expect(page).toHaveURL(/\/login/);
  });

  test('authenticated user visiting /login is redirected to /dashboard', async ({ page }) => {
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
    await expect(page).toHaveURL(/\/dashboard/);

    await page.goto('/login');
    await expect(page).toHaveURL(/\/dashboard/);
  });
});
