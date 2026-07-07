import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

import { ACCESS_COOKIE, REFRESH_COOKIE } from '@/lib/session';

export default async function RootPage() {
  const cookieStore = await cookies();
  const hasSession = Boolean(
    cookieStore.get(ACCESS_COOKIE)?.value ?? cookieStore.get(REFRESH_COOKIE)?.value,
  );
  redirect(hasSession ? '/dashboard' : '/login');
}
