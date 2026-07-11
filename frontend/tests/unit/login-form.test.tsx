import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const push = vi.fn();
const refresh = vi.fn();
let searchParams = new URLSearchParams();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, refresh }),
  useSearchParams: () => searchParams,
}));

import { LoginForm } from '@/components/auth/login-form';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function renderLoginForm(): void {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  render(<LoginForm />, { wrapper });
}

describe('LoginForm', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    searchParams = new URLSearchParams();
    push.mockClear();
    refresh.mockClear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('defaults to the password tab', () => {
    renderLoginForm();
    expect(screen.getByRole('tab', { name: 'Password' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.getByLabelText('Email')).toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toBeInTheDocument();
  });

  it('switches to the SSO tab and shows the work-email form instead of a password field', () => {
    renderLoginForm();
    fireEvent.click(screen.getByRole('tab', { name: 'Sign in with SSO' }));

    expect(screen.getByRole('tab', { name: 'Sign in with SSO' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.getByLabelText('Work email')).toBeInTheDocument();
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Continue' })).toBeInTheDocument();
  });

  it('redirects the browser to the IdP authorization URL on a successful SSO start', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({ redirect_url: 'https://idp.example.com/authorize?state=abc' }),
    );
    const originalLocation = window.location;
    // jsdom's window.location isn't directly assignable — replace it for
    // this test only, restored in the finally block below.
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { ...originalLocation, href: '' },
    });

    try {
      renderLoginForm();
      fireEvent.click(screen.getByRole('tab', { name: 'Sign in with SSO' }));
      fireEvent.change(screen.getByLabelText('Work email'), {
        target: { value: 'user@acme.example.com' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'Continue' }));

      await waitFor(() => {
        expect(window.location.href).toBe('https://idp.example.com/authorize?state=abc');
      });
      expect(fetch).toHaveBeenCalledWith(
        '/api/auth/sso/start',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ email: 'user@acme.example.com' }),
        }),
      );
    } finally {
      Object.defineProperty(window, 'location', { writable: true, value: originalLocation });
    }
  });

  it('shows an error when SSO is not configured for the entered email domain', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(
        { error_code: 'not_found', message: 'SSO is not configured for this email domain.' },
        404,
      ),
    );

    renderLoginForm();
    fireEvent.click(screen.getByRole('tab', { name: 'Sign in with SSO' }));
    fireEvent.change(screen.getByLabelText('Work email'), {
      target: { value: 'user@no-sso.example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));

    expect(
      await screen.findByText('SSO is not configured for this email domain.'),
    ).toBeInTheDocument();
  });

  it('shows the sso_failed banner when redirected back with ?error=sso_failed', () => {
    searchParams = new URLSearchParams('error=sso_failed');
    renderLoginForm();
    expect(
      screen.getByText(/your organization's sso sign-in didn't complete/i),
    ).toBeInTheDocument();
  });
});
