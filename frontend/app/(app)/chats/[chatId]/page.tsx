'use client';

import {
  Archive,
  ArchiveRestore,
  ArrowLeft,
  MessageSquare,
  Pin,
  PinOff,
  Trash2,
} from 'lucide-react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useRef, useState } from 'react';

import { EmptyState } from '@/components/chats/empty-state';
import { Button, buttonVariants } from '@/components/ui/button';
import { Dialog, type DialogHandle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { useChat, useDeleteChat, useUpdateChat } from '@/lib/hooks/use-chats';
import { cn } from '@/lib/utils';

export default function ChatDetailPage(): React.JSX.Element {
  const params = useParams<{ chatId: string }>();
  const router = useRouter();
  const chatQuery = useChat(params.chatId);
  const updateChat = useUpdateChat();
  const deleteChat = useDeleteChat();
  const deleteDialogRef = useRef<DialogHandle>(null);

  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState('');

  if (chatQuery.isLoading) {
    return (
      <div className="flex flex-col gap-4">
        <div className="h-8 w-1/3 animate-pulse rounded bg-muted" />
        <div className="h-64 animate-pulse rounded-xl bg-muted" />
      </div>
    );
  }

  if (chatQuery.isError || !chatQuery.data) {
    return (
      <EmptyState
        icon={MessageSquare}
        title="Chat not found"
        description="This chat doesn't exist, or you don't have access to it."
        action={
          <Button variant="outline" onClick={() => router.push('/chats')}>
            Back to chats
          </Button>
        }
      />
    );
  }

  const chat = chatQuery.data;

  const submitTitle = (): void => {
    setIsEditingTitle(false);
    const trimmed = titleDraft.trim();
    if (trimmed && trimmed !== chat.title) {
      updateChat.mutate({ chatId: chat.id, payload: { title: trimmed } });
    } else {
      setTitleDraft(chat.title);
    }
  };

  const confirmDelete = (): void => {
    deleteChat.mutate(chat.id, { onSuccess: () => router.push('/chats') });
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <Link
            href="/chats"
            aria-label="Back to chats"
            className={cn(buttonVariants({ variant: 'ghost', size: 'icon' }))}
          >
            <ArrowLeft className="h-4 w-4" />
          </Link>

          {isEditingTitle ? (
            <Input
              autoFocus
              value={titleDraft}
              onChange={(e) => setTitleDraft(e.target.value)}
              onBlur={submitTitle}
              onKeyDown={(e) => {
                if (e.key === 'Enter') submitTitle();
                if (e.key === 'Escape') {
                  setTitleDraft(chat.title);
                  setIsEditingTitle(false);
                }
              }}
              className="font-display text-xl font-semibold"
            />
          ) : (
            <button
              onClick={() => {
                setTitleDraft(chat.title);
                setIsEditingTitle(true);
              }}
              className="truncate rounded px-1 text-left font-display text-xl font-semibold hover:bg-muted"
              aria-label="Rename chat"
            >
              {chat.title}
            </button>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            aria-label={chat.is_pinned ? 'Unpin chat' : 'Pin chat'}
            onClick={() =>
              updateChat.mutate({ chatId: chat.id, payload: { is_pinned: !chat.is_pinned } })
            }
          >
            {chat.is_pinned ? <PinOff className="h-4 w-4" /> : <Pin className="h-4 w-4" />}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label={chat.is_archived ? 'Unarchive chat' : 'Archive chat'}
            onClick={() =>
              updateChat.mutate({ chatId: chat.id, payload: { is_archived: !chat.is_archived } })
            }
          >
            {chat.is_archived ? (
              <ArchiveRestore className="h-4 w-4" />
            ) : (
              <Archive className="h-4 w-4" />
            )}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Delete chat"
            onClick={() => deleteDialogRef.current?.showModal()}
          >
            <Trash2 className="h-4 w-4 text-destructive" />
          </Button>
        </div>
      </div>

      <EmptyState
        icon={MessageSquare}
        title="Messaging is coming soon"
        description="Evidence-grounded conversation, document upload, and medication safety checks land in the next build phase. Your chat is created and ready."
      />

      <Dialog
        ref={deleteDialogRef}
        title="Delete this chat?"
        description={`"${chat.title}" will be permanently deleted. This can't be undone.`}
      >
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => deleteDialogRef.current?.close()}>
            Cancel
          </Button>
          <Button variant="destructive" isLoading={deleteChat.isPending} onClick={confirmDelete}>
            Delete
          </Button>
        </div>
      </Dialog>
    </div>
  );
}
