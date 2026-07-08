'use client';

import { ArrowRight, MessageSquare, Plus } from 'lucide-react';
import { useRouter } from 'next/navigation';

import { ChatListItem } from '@/components/chats/chat-list-item';
import { EmptyState } from '@/components/chats/empty-state';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useCurrentUser } from '@/lib/hooks/use-auth';
import { useChats, useCreateChat } from '@/lib/hooks/use-chats';

export default function DashboardPage(): React.JSX.Element {
  const router = useRouter();
  const currentUser = useCurrentUser();
  const user = currentUser.data;
  const recentChats = useChats();
  const createChat = useCreateChat();

  const handleCreateChat = (): void => {
    createChat.mutate(undefined, {
      onSuccess: (chat) => router.push(`/chats/${chat.id}`),
    });
  };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">
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
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle className="font-display">Recent chats</CardTitle>
          <Button variant="outline" size="sm" onClick={() => router.push('/chats')}>
            View all
            <ArrowRight className="h-3.5 w-3.5" />
          </Button>
        </CardHeader>
        <CardContent>
          {recentChats.data && recentChats.data.length > 0 ? (
            <ul className="flex flex-col gap-1">
              {recentChats.data.slice(0, 5).map((chat) => (
                <ChatListItem key={chat.id} chat={chat} />
              ))}
            </ul>
          ) : (
            <EmptyState
              as="h3"
              icon={MessageSquare}
              title="Start your first chat"
              description="Ask a question, upload a document, or explore a clinical topic — every answer comes with transparent, sourced evidence."
              action={
                <Button onClick={handleCreateChat} isLoading={createChat.isPending}>
                  <Plus className="h-4 w-4" />
                  New chat
                </Button>
              }
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
