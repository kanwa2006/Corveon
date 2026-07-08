'use client';

import { AlertTriangle, CheckCircle2, FileText, Loader2, Paperclip, X } from 'lucide-react';
import { useRef, type ChangeEvent } from 'react';

import { Button } from '@/components/ui/button';
import type { DocumentPublic } from '@/lib/api/documents';
import type { UploadProgress } from '@/lib/hooks/use-documents';
import { cn } from '@/lib/utils';

const STAGE_LABELS: Record<string, string> = {
  validating: 'Validating',
  extracting: 'Extracting text',
  chunking: 'Chunking',
  embedding: 'Embedding',
  indexing: 'Indexing',
  complete: 'Complete',
};

interface DocumentPanelProps {
  documents: DocumentPublic[];
  uploads: Record<string, UploadProgress>;
  onUpload: (file: File) => void;
  onDelete: (documentId: string) => void;
  onDismissUpload: (key: string) => void;
}

export function DocumentPanel({
  documents,
  uploads,
  onUpload,
  onDelete,
  onDismissUpload,
}: DocumentPanelProps): React.JSX.Element {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>): void => {
    const file = event.target.files?.[0];
    if (file) onUpload(file);
    event.target.value = '';
  };

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-sm font-semibold text-card-foreground">Documents</h2>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => fileInputRef.current?.click()}
        >
          <Paperclip className="h-3.5 w-3.5" />
          Upload PDF
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={handleFileChange}
        />
      </div>

      {documents.length === 0 && Object.keys(uploads).length === 0 && (
        <p className="text-xs text-muted-foreground">
          Upload a PDF to ground answers in your own documents.
        </p>
      )}

      <ul className="flex flex-col gap-1.5">
        {Object.entries(uploads).map(([key, progress]) => (
          <li
            key={key}
            className="flex items-center gap-2 rounded-md border border-border bg-muted/50 px-2.5 py-1.5 text-xs"
          >
            {progress.status === 'failed' ? (
              <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-destructive" aria-hidden="true" />
            ) : progress.status === 'succeeded' ? (
              <CheckCircle2
                className="h-3.5 w-3.5 shrink-0 text-evidence-verified"
                aria-hidden="true"
              />
            ) : (
              <Loader2
                className="h-3.5 w-3.5 shrink-0 animate-spin text-muted-foreground"
                aria-hidden="true"
              />
            )}
            <span className="min-w-0 flex-1 truncate">{progress.fileName}</span>
            <span className="shrink-0 text-muted-foreground">
              {progress.status === 'failed'
                ? (progress.error ?? 'Failed')
                : (STAGE_LABELS[progress.stage ?? ''] ?? 'Uploading')}
            </span>
            {(progress.status === 'failed' || progress.status === 'succeeded') && (
              <button
                type="button"
                onClick={() => onDismissUpload(key)}
                aria-label="Dismiss"
                className="shrink-0 rounded p-0.5 hover:bg-muted"
              >
                <X className="h-3 w-3" />
              </button>
            )}
          </li>
        ))}

        {documents.map((document) => (
          <li
            key={document.id}
            className="flex items-center gap-2 rounded-md px-2.5 py-1.5 text-xs hover:bg-muted/50"
          >
            <FileText className="h-3.5 w-3.5 shrink-0 text-evidence-uploaded" aria-hidden="true" />
            <span className="min-w-0 flex-1 truncate">{document.filename}</span>
            <span
              className={cn(
                'shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium',
                document.status === 'ready' && 'bg-evidence-verified/10 text-evidence-verified',
                document.status === 'failed' && 'bg-destructive/10 text-destructive',
                (document.status === 'pending' || document.status === 'processing') &&
                  'bg-muted text-muted-foreground',
              )}
            >
              {document.status}
            </span>
            <button
              type="button"
              onClick={() => onDelete(document.id)}
              aria-label={`Delete ${document.filename}`}
              className="shrink-0 rounded p-0.5 hover:bg-muted"
            >
              <X className="h-3 w-3" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
