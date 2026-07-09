'use client';

import { AnimatePresence, motion } from 'framer-motion';
import { Sparkles } from 'lucide-react';
import { useEffect, useRef } from 'react';

import { MessageBubble } from '@/components/chats/message-bubble';
import type { MessagePublic } from '@/lib/api/messages';
import type { SendStatus } from '@/lib/hooks/use-messages';

interface MessageThreadProps {
  messages: MessagePublic[];
  status: SendStatus;
  draftText: string;
}

export function MessageThread({
  messages,
  status,
  draftText,
}: MessageThreadProps): React.JSX.Element {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages.length, draftText]);

  return (
    <div className="flex flex-col gap-4">
      <AnimatePresence initial={false}>
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
      </AnimatePresence>

      {(status === 'sending' || status === 'streaming') && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex gap-3"
        >
          <div
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground"
            aria-hidden="true"
          >
            <Sparkles className="h-4 w-4" />
          </div>
          <div className="max-w-[75%] rounded-2xl rounded-tl-sm border border-border bg-card px-4 py-2.5 text-sm leading-relaxed text-card-foreground">
            {draftText ? (
              <span className="whitespace-pre-wrap">
                {draftText}
                <span className="ml-0.5 inline-block h-4 w-[2px] animate-pulse bg-current align-middle" />
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-muted-foreground">
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current [animation-delay:-0.3s]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current [animation-delay:-0.15s]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current" />
              </span>
            )}
          </div>
        </motion.div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}
