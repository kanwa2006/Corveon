'use client';

import { motion } from 'framer-motion';
import { Download, ExternalLink, FileText, Sparkles, User } from 'lucide-react';
import { useState } from 'react';

import { EvidenceVerificationPanel } from '@/components/chats/evidence-verification-panel';
import { useEvidenceVerification } from '@/lib/hooks/use-evidence-verification';
import { exportMessage, type ExportFormat, type MessagePublic } from '@/lib/api/messages';
import { cn } from '@/lib/utils';

const PUBLIC_EVIDENCE_SOURCE_LABEL: Record<string, string> = {
  pubmed: 'PubMed',
  dailymed: 'DailyMed',
  openfda: 'openFDA',
  clinicaltrials: 'ClinicalTrials.gov',
  mesh: 'MeSH',
  rxnorm: 'RxNorm',
};

interface MessageBubbleProps {
  message: MessagePublic;
}

export function MessageBubble({ message }: MessageBubbleProps): React.JSX.Element {
  const isUser = message.role === 'user';
  const citations = message.routing_trace?.retrieved_chunks ?? [];
  const publicEvidence = message.routing_trace?.public_evidence ?? [];
  const [exportingFormat, setExportingFormat] = useState<ExportFormat | null>(null);
  const verification = useEvidenceVerification(message.chat_id);

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

        {publicEvidence.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {publicEvidence.map((item, index) => {
              const label = PUBLIC_EVIDENCE_SOURCE_LABEL[item.source] ?? item.source;
              const chip = (
                <span
                  className="inline-flex items-center gap-1 rounded-full border border-evidence-verified/30 bg-evidence-verified/10 px-2 py-0.5 text-xs font-medium text-evidence-verified"
                  title={item.title}
                >
                  {label}
                  {item.url && <ExternalLink className="h-3 w-3" aria-hidden="true" />}
                </span>
              );
              return item.url ? (
                <a
                  key={`${item.source}-${item.identifier ?? index}`}
                  href={item.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={`${label}: ${item.title}`}
                >
                  {chip}
                </a>
              ) : (
                <span key={`${item.source}-${item.identifier ?? index}`}>{chip}</span>
              );
            })}
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

        {!isUser && message.content && (
          <EvidenceVerificationPanel
            status={verification.status}
            claims={verification.claims}
            errorMessage={verification.errorMessage}
            onVerify={() => void verification.verify(message.id)}
            onDismiss={verification.reset}
          />
        )}
      </div>
    </motion.div>
  );
}
