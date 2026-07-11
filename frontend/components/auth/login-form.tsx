'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useState, type FormEvent } from 'react';

import { AlertError } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useLogin } from '@/lib/hooks/use-auth';
import { useStartSso } from '@/lib/hooks/use-sso';
import { cn } from '@/lib/utils';

type LoginMode = 'password' | 'sso';

export function LoginForm(): React.JSX.Element {
  const [mode, setMode] = useState<LoginMode>('password');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [ssoEmail, setSsoEmail] = useState('');
  const router = useRouter();
  const searchParams = useSearchParams();
  const login = useLogin();
  const startSso = useStartSso();

  const ssoFailed = searchParams.get('error') === 'sso_failed';

  const handleSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    login.mutate(
      { email, password },
      {
        onSuccess: () => {
          const next = searchParams.get('next') ?? '/dashboard';
          router.push(next);
          router.refresh();
        },
      },
    );
  };

  const handleSsoSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    startSso.mutate(ssoEmail, {
      onSuccess: ({ redirect_url }) => {
        window.location.href = redirect_url;
      },
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle as="h1">Sign in to Corveon</CardTitle>
        <CardDescription>
          Evidence-grounded clinical intelligence, one workspace at a time.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div
          role="tablist"
          aria-label="Sign-in method"
          className="mb-4 grid grid-cols-2 gap-1 rounded-md bg-muted p-1"
        >
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'password'}
            className={cn(
              'rounded px-3 py-1.5 text-sm font-medium transition-colors',
              mode === 'password'
                ? 'bg-card text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground',
            )}
            onClick={() => setMode('password')}
          >
            Password
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'sso'}
            className={cn(
              'rounded px-3 py-1.5 text-sm font-medium transition-colors',
              mode === 'sso'
                ? 'bg-card text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground',
            )}
            onClick={() => setMode('sso')}
          >
            Sign in with SSO
          </button>
        </div>

        {ssoFailed && (
          <div className="mb-4">
            <AlertError>
              Your organization&apos;s SSO sign-in didn&apos;t complete. Please try again.
            </AlertError>
          </div>
        )}

        {mode === 'password' ? (
          <form className="flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
            {login.isError && <AlertError>{login.error.message}</AlertError>}

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                aria-invalid={login.isError}
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-invalid={login.isError}
              />
            </div>

            <Button type="submit" isLoading={login.isPending} className="mt-2">
              Sign in
            </Button>
          </form>
        ) : (
          <form className="flex flex-col gap-4" onSubmit={handleSsoSubmit} noValidate>
            {startSso.isError && <AlertError>{startSso.error.message}</AlertError>}

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="sso-email">Work email</Label>
              <Input
                id="sso-email"
                name="ssoEmail"
                type="email"
                autoComplete="email"
                required
                value={ssoEmail}
                onChange={(e) => setSsoEmail(e.target.value)}
                aria-invalid={startSso.isError}
                aria-describedby="sso-email-hint"
              />
              <p id="sso-email-hint" className="text-xs text-muted-foreground">
                We&apos;ll redirect you to your organization&apos;s identity provider.
              </p>
            </div>

            <Button type="submit" isLoading={startSso.isPending} className="mt-2">
              Continue
            </Button>
          </form>
        )}

        <p className="mt-4 text-center text-sm text-muted-foreground">
          Don&apos;t have an account?{' '}
          <Link href="/register" className="font-medium text-primary hover:underline">
            Create one
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}
