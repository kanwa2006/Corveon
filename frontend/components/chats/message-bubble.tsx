'use client';

import { motion } from 'framer-motion';
import { Download, FileText, Sparkles, User } from 'lucide-react';
import { useState } from 'react';

import { exportMessage, type ExportFormat, type MessagePublic } from '@/lib/api/messages';
import { cn } from '@/lib/utils';

interface MessageBubbleProps {
  message: MessagePublic;
}

export function MessageBubble({ message }: MessageBubbleProps): React.JSX.Element {
  const isUser = message.role === 'user';
  const citations = message.routing_trace?.retrieved_chunks ?? [];
  const [exportingFormat, setExportingFormat] = useState<ExportFormat | null>(null);

  const handleExport = (format: ExportFormat): void => {
    setExportingFormat(format);
    exportMessage(message.chat_id, message.id, format)
      .catch(() => {
        // A failed export is a minor, retryable inconvenience, not worth a
        // blocking error banner on top of the conversation itself.
      })
      .finally(() => setExportingFormat(null));
  };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn('flex gap-3', isUser ? 'flex-row-reverse' : 'flex-row')}
    >
      <div
        className={cn(
          'flex h-8 w-8 shrink-0 items-center justify-center rounded-full',
          isUser ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground',
        )}
        aria-hidden="true"
      >
        {isUser ? <User className="h-4 w-4" /> : <Sparkles className="h-4 w-4" />}
      </div>

      <div className={cn('flex max-w-[75%] flex-col gap-2', isUser ? 'items-end' : 'items-start')}>
        <div
          className={cn(
            'whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-relaxed',
            isUser
              ? 'rounded-tr-sm bg-primary text-primary-foreground'
              : 'rounded-tl-sm border border-border bg-card text-card-foreground',
          )}
        >
          {message.content}
        </div>

        {citations.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {citations.map((chunk) => (
              <span
                key={chunk.chunk_id}
                className="inline-flex items-center gap-1 rounded-full border border-evidence-uploaded/30 bg-evidence-uploaded/10 px-2 py-0.5 text-xs font-medium text-evidence-uploaded"
                title={`${Math.round(chunk.similarity * 100)}% match — excerpt ${chunk.ordinal + 1}`}
              >
                <FileText className="h-3 w-3" aria-hidden="true" />
                {chunk.document_filename}
              </span>
            ))}
          </div>
        )}

        {message.routing_trace?.status === 'provider_unavailable' && (
          <p className="text-xs text-muted-foreground">
            No AI provider was reachable — a known degraded state, not an error in your request.
          </p>
        )}

        {!isUser && message.content && (
          <div className="flex gap-1">
            <button
              type="button"
              onClick={() => handleExport('md')}
              disabled={exportingFormat !== null}
              aria-label="Export as Markdown"
              title="Export as Markdown"
              className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
            >
              <Download className="h-3 w-3" aria-hidden="true" />
              Markdown
            </button>
            <button
              type="button"
              onClick={() => handleExport('pdf')}
              disabled={exportingFormat !== null}
              aria-label="Export as PDF"
              title="Export as PDF"
              className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
            >
              <Download className="h-3 w-3" aria-hidden="true" />
              PDF
            </button>
          </div>
        )}
      </div>
    </motion.div>
  );
}
