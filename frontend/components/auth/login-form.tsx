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

export function LoginForm(): React.JSX.Element {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const router = useRouter();
  const searchParams = useSearchParams();
  const login = useLogin();

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

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sign in to Corveon</CardTitle>
        <CardDescription>
          Evidence-grounded clinical intelligence, one workspace at a time.
        </CardDescription>
      </CardHeader>
      <CardContent>
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

          <p className="text-center text-sm text-muted-foreground">
            Don&apos;t have an account?{' '}
            <Link href="/register" className="font-medium text-primary hover:underline">
              Create one
            </Link>
          </p>
        </form>
      </CardContent>
    </Card>
  );
}
