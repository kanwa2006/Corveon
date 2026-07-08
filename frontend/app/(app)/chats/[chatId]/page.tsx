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

import { DocumentPanel } from '@/components/chats/document-panel';
import { EmptyState } from '@/components/chats/empty-state';
import { MessageComposer } from '@/components/chats/message-composer';
import { MessageThread } from '@/components/chats/message-thread';
import { Button, buttonVariants } from '@/components/ui/button';
import { Dialog, type DialogHandle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { useChat, useDeleteChat, useUpdateChat } from '@/lib/hooks/use-chats';
import { useDeleteDocument, useDocuments, useUploadDocument } from '@/lib/hooks/use-documents';
import { useMessages, useSendMessage } from '@/lib/hooks/use-messages';
import { cn } from '@/lib/utils';

export default function ChatDetailPage(): React.JSX.Element {
  const params = useParams<{ chatId: string }>();
  const router = useRouter();
  const chatQuery = useChat(params.chatId);
  const updateChat = useUpdateChat();
  const deleteChat = useDeleteChat();
  const deleteDialogRef = useRef<DialogHandle>(null);

  const messagesQuery = useMessages(params.chatId);
  const sendMessage = useSendMessage(params.chatId);
  const documentsQuery = useDocuments(params.chatId);
  const uploadDocument = useUploadDocument(params.chatId);
  const deleteDocument = useDeleteDocument(params.chatId);

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
  const messages = messagesQuery.data ?? [];
  const hasContent = messages.length > 0 || sendMessage.status !== 'idle';

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
    <div className="flex h-full flex-col gap-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <Link
            href="/chats"
            aria-label="Back to chats"
            className={cn(buttonVariants({ variant: 'ghost', size: 'icon' }))}
          >
            <ArrowLeft className="h-4 w-4" />
          </Link>

          <h1 className="min-w-0 flex-1">
            {isEditingTitle ? (
              <Input
                autoFocus
                aria-label="Chat title"
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
                className="w-full truncate rounded px-1 text-left font-display text-xl font-semibold hover:bg-muted"
                aria-label="Rename chat"
              >
                {chat.title}
              </button>
            )}
          </h1>
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

      <DocumentPanel
        documents={documentsQuery.data ?? []}
        uploads={uploadDocument.uploads}
        onUpload={(file) => void uploadDocument.upload(file)}
        onDelete={(documentId) => deleteDocument.mutate(documentId)}
        onDismissUpload={uploadDocument.dismissUpload}
      />

      <div className="flex flex-1 flex-col justify-between gap-4">
        {hasContent ? (
          <MessageThread
            messages={messages}
            status={sendMessage.status}
            draftText={sendMessage.draftText}
          />
        ) : (
          <EmptyState
            icon={MessageSquare}
            title="Start the conversation"
            description="Ask a question below. If you've uploaded documents to this chat, answers are grounded in them automatically."
          />
        )}

        {sendMessage.status === 'error' && sendMessage.errorMessage && (
          // Solid destructive/destructive-foreground (not the tinted
          // /10-opacity combo AlertError uses) — that pairing falls short of
          // WCAG AA contrast for 14px text (verified via axe-core; tracked
          // as a follow-up for the shared component, see spawn_task).
          <div
            role="alert"
            className="flex items-center justify-between gap-3 rounded-md bg-destructive px-3 py-2 text-sm text-destructive-foreground"
          >
            <span>{sendMessage.errorMessage}</span>
            <button
              type="button"
              onClick={sendMessage.dismissError}
              className="shrink-0 font-medium underline underline-offset-2"
            >
              Dismiss
            </button>
          </div>
        )}

        <MessageComposer
          status={sendMessage.status}
          onSend={(content) => void sendMessage.send(content)}
          onCancel={sendMessage.cancel}
        />
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
    </div>
  );
}
