'use client';

import { Plus, Search } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { ChatList } from '@/components/chats/chat-list';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useCreateChat } from '@/lib/hooks/use-chats';
import { useDebouncedValue } from '@/lib/hooks/use-debounced-value';
import { cn } from '@/lib/utils';

type FilterTab = 'all' | 'pinned' | 'archived';

const TABS: Array<{ id: FilterTab; label: string }> = [
  { id: 'all', label: 'All' },
  { id: 'pinned', label: 'Pinned' },
  { id: 'archived', label: 'Archived' },
];

export default function ChatsPage(): React.JSX.Element {
  const router = useRouter();
  const [searchInput, setSearchInput] = useState('');
  const [tab, setTab] = useState<FilterTab>('all');
  const search = useDebouncedValue(searchInput, 250);
  const createChat = useCreateChat();

  const handleCreateChat = (): void => {
    createChat.mutate(undefined, {
      onSuccess: (chat) => router.push(`/chats/${chat.id}`),
    });
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-4">
        <h1 className="font-display text-2xl font-semibold tracking-tight">Chats</h1>
        <Button onClick={handleCreateChat} isLoading={createChat.isPending}>
          <Plus className="h-4 w-4" />
          New chat
        </Button>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative w-full sm:max-w-xs">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            type="search"
            placeholder="Search chats…"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="pl-9"
            aria-label="Search chats"
          />
        </div>

        <div
          role="tablist"
          aria-label="Filter chats"
          className="flex gap-1 rounded-lg bg-muted p-1"
        >
          {TABS.map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={tab === t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                tab === t.id
                  ? 'bg-card text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <ChatList
        filters={{
          search: search || undefined,
          pinned: tab === 'pinned' ? true : undefined,
          archived: tab === 'archived' ? true : undefined,
        }}
      />
    </div>
  );
}
