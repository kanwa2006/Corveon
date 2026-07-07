'use client';

import { motion } from 'framer-motion';
import { Archive, ArchiveRestore, MoreHorizontal, Pin, PinOff, Trash2 } from 'lucide-react';
import Link from 'next/link';
import { useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Dialog, type DialogHandle } from '@/components/ui/dialog';
import type { ChatPublic } from '@/lib/api/chats';
import { useDeleteChat, useUpdateChat } from '@/lib/hooks/use-chats';
import { formatRelativeTime } from '@/lib/utils';

export function ChatListItem({ chat }: { chat: ChatPublic }): React.JSX.Element {
  const [menuOpen, setMenuOpen] = useState(false);
  const deleteDialogRef = useRef<DialogHandle>(null);
  const updateChat = useUpdateChat();
  const deleteChat = useDeleteChat();

  const togglePin = (): void => {
    updateChat.mutate({ chatId: chat.id, payload: { is_pinned: !chat.is_pinned } });
    setMenuOpen(false);
  };

  const toggleArchive = (): void => {
    updateChat.mutate({ chatId: chat.id, payload: { is_archived: !chat.is_archived } });
    setMenuOpen(false);
  };

  const confirmDelete = (): void => {
    deleteChat.mutate(chat.id);
    deleteDialogRef.current?.close();
  };

  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.2 }}
      className="group relative flex items-center gap-2 rounded-lg border border-transparent px-3 py-2.5 hover:border-border hover:bg-muted/50"
    >
      <Link href={`/chats/${chat.id}`} className="flex min-w-0 flex-1 items-center gap-2.5">
        {chat.is_pinned && (
          <Pin className="h-3.5 w-3.5 shrink-0 fill-primary text-primary" aria-label="Pinned" />
        )}
        <span className="truncate text-sm font-medium">{chat.title}</span>
        <span className="ml-auto shrink-0 whitespace-nowrap text-xs text-muted-foreground">
          {formatRelativeTime(chat.updated_at)}
        </span>
      </Link>

      <div className="relative shrink-0">
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 opacity-0 group-focus-within:opacity-100 group-hover:opacity-100 data-[open=true]:opacity-100"
          data-open={menuOpen}
          aria-label={`Actions for ${chat.title}`}
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((open) => !open)}
        >
          <MoreHorizontal className="h-4 w-4" />
        </Button>

        {menuOpen && (
          <>
            <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
            <div
              role="menu"
              className="absolute right-0 top-full z-20 mt-1 w-40 overflow-hidden rounded-md border border-border bg-card py-1 shadow-lg"
            >
              <button
                role="menuitem"
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-muted"
                onClick={togglePin}
              >
                {chat.is_pinned ? (
                  <PinOff className="h-3.5 w-3.5" />
                ) : (
                  <Pin className="h-3.5 w-3.5" />
                )}
                {chat.is_pinned ? 'Unpin' : 'Pin'}
              </button>
              <button
                role="menuitem"
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-muted"
                onClick={toggleArchive}
              >
                {chat.is_archived ? (
                  <ArchiveRestore className="h-3.5 w-3.5" />
                ) : (
                  <Archive className="h-3.5 w-3.5" />
                )}
                {chat.is_archived ? 'Unarchive' : 'Archive'}
              </button>
              <button
                role="menuitem"
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-destructive hover:bg-destructive/10"
                onClick={() => {
                  setMenuOpen(false);
                  deleteDialogRef.current?.showModal();
                }}
              >
                <Trash2 className="h-3.5 w-3.5" />
                Delete
              </button>
            </div>
          </>
        )}
      </div>

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
    </motion.li>
  );
}
