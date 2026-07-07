import type { Metadata } from 'next';

import { RegisterForm } from '@/components/auth/register-form';

export const metadata: Metadata = { title: 'Create account — Corveon' };

export default function RegisterPage(): React.JSX.Element {
  return <RegisterForm />;
}
