'use client';

import { AnimatePresence } from 'framer-motion';
import { AlertCircle, MessageSquare, SearchX } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { ChatListItem } from '@/components/chats/chat-list-item';
import { EmptyState } from '@/components/chats/empty-state';
import type { ChatListFilters } from '@/lib/api/chats';
import { useChats } from '@/lib/hooks/use-chats';

function ChatListSkeleton(): React.JSX.Element {
  return (
    <ul className="flex flex-col gap-1.5" aria-hidden="true">
      {[0, 1, 2, 3, 4].map((i) => (
        <li key={i} className="flex items-center gap-3 rounded-lg px-3 py-2.5">
          <div className="h-4 w-1/3 animate-pulse rounded bg-muted" />
          <div className="ml-auto h-3 w-16 animate-pulse rounded bg-muted" />
        </li>
      ))}
    </ul>
  );
}

interface ChatListProps {
  filters: ChatListFilters;
  onCreateChat: () => void;
}

export function ChatList({ filters, onCreateChat }: ChatListProps): React.JSX.Element {
  const { data: chats, isLoading, isError, refetch } = useChats(filters);

  if (isLoading) {
    return <ChatListSkeleton />;
  }

  if (isError) {
    return (
      <EmptyState
        icon={AlertCircle}
        title="Couldn't load your chats"
        description="Something went wrong reaching the server. Check your connection and try again."
        action={
          <Button variant="outline" onClick={() => refetch()}>
            Try again
          </Button>
        }
      />
    );
  }

  if (chats && chats.length === 0) {
    if (filters.search) {
      return (
        <EmptyState
          icon={SearchX}
          title="No matching chats"
          description={`Nothing matches "${filters.search}". Try a different search term.`}
        />
      );
    }
    if (filters.archived) {
      return (
        <EmptyState
          icon={MessageSquare}
          title="No archived chats"
          description="Chats you archive will show up here."
        />
      );
    }
    return (
      <EmptyState
        icon={MessageSquare}
        title="Start your first chat"
        description="Ask a question, upload a document, or explore a clinical topic — every answer comes with transparent, sourced evidence."
        action={<Button onClick={onCreateChat}>New chat</Button>}
      />
    );
  }

  return (
    <ul className="flex flex-col gap-1">
      <AnimatePresence initial={false}>
        {chats?.map((chat) => (
          <ChatListItem key={chat.id} chat={chat} />
        ))}
      </AnimatePresence>
    </ul>
  );
}
