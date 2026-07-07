'use client';

import { useRouter } from 'next/navigation';
import { useEffect, type ReactNode } from 'react';

import { Button } from '@/components/ui/button';
import { ThemeToggle } from '@/components/theme-toggle';
import { useCurrentUser, useLogout } from '@/lib/hooks/use-auth';

export default function AppLayout({ children }: { children: ReactNode }): React.JSX.Element | null {
  const router = useRouter();
  const currentUser = useCurrentUser();
  const logout = useLogout();

  useEffect(() => {
    // Middleware only checks cookie presence; if the session is present but
    // no longer valid (expired/revoked), the /me call 401s here — fall back
    // to a client-side redirect rather than showing a broken authenticated page.
    if (currentUser.isError) {
      router.replace('/login');
    }
  }, [currentUser.isError, router]);

  if (currentUser.isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div
          className="h-8 w-8 animate-spin rounded-full border-2 border-muted border-t-primary"
          role="status"
          aria-label="Loading"
        />
      </div>
    );
  }

  if (currentUser.isError) {
    return null; // redirecting via the effect above
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="flex items-center justify-between border-b border-border px-6 py-4">
        <span className="text-lg font-semibold">Corveon</span>
        <div className="flex items-center gap-2">
          <span className="hidden text-sm text-muted-foreground sm:inline">
            {currentUser.data?.email}
          </span>
          <ThemeToggle />
          <Button
            variant="outline"
            size="sm"
            isLoading={logout.isPending}
            onClick={() => logout.mutate(undefined, { onSuccess: () => router.push('/login') })}
          >
            Sign out
          </Button>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-6 py-8">{children}</main>
    </div>
  );
}
