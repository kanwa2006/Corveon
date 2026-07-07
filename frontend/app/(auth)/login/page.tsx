import type { Metadata } from 'next';
import { Suspense } from 'react';

import { LoginForm } from '@/components/auth/login-form';

export const metadata: Metadata = { title: 'Sign in — Corveon' };

export default function LoginPage(): React.JSX.Element {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
