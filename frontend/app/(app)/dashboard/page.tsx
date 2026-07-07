'use client';

import { MessageSquare } from 'lucide-react';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useCurrentUser } from '@/lib/hooks/use-auth';

export default function DashboardPage(): React.JSX.Element {
  const currentUser = useCurrentUser();
  const user = currentUser.data;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Welcome{user ? `, ${user.email}` : ''}
        </h1>
        {user && (
          <p className="text-sm text-muted-foreground">
            Signed in as <span className="font-medium">{user.role}</span> · account created{' '}
            {new Date(user.created_at).toLocaleDateString()}
          </p>
        )}
      </div>

      <Card>
        <CardHeader className="items-center text-center">
          <div className="mb-2 flex h-12 w-12 items-center justify-center rounded-full bg-muted">
            <MessageSquare className="h-6 w-6 text-muted-foreground" aria-hidden="true" />
          </div>
          <CardTitle>Chats are coming soon</CardTitle>
          <CardDescription>
            Evidence-grounded conversations, document upload, and medication safety checks land in
            the next build phase. Your account is ready.
          </CardDescription>
        </CardHeader>
        <CardContent />
      </Card>
    </div>
  );
}
