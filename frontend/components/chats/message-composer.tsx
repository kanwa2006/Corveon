'use client';

import { ArrowUp, Square } from 'lucide-react';
import { useState, type FormEvent, type KeyboardEvent } from 'react';

import { Button } from '@/components/ui/button';
import type { SendStatus } from '@/lib/hooks/use-messages';

interface MessageComposerProps {
  status: SendStatus;
  onSend: (content: string) => void;
  onCancel: () => void;
}

export function MessageComposer({
  status,
  onSend,
  onCancel,
}: MessageComposerProps): React.JSX.Element {
  const [value, setValue] = useState('');
  const isBusy = status === 'sending' || status === 'streaming';

  const submit = (): void => {
    const trimmed = value.trim();
    if (!trimmed || isBusy) return;
    setValue('');
    onSend(trimmed);
  };

  const handleSubmit = (event: FormEvent): void => {
    event.preventDefault();
    submit();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>): void => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex items-end gap-2 border-t border-border pt-4">
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask about this chat's uploaded documents, or anything else..."
        rows={1}
        disabled={isBusy}
        className="max-h-40 min-h-[2.5rem] flex-1 resize-none rounded-md border border-input bg-transparent px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
      />
      {isBusy ? (
        <Button
          type="button"
          variant="outline"
          size="icon"
          onClick={onCancel}
          aria-label="Stop generating"
        >
          <Square className="h-4 w-4" />
        </Button>
      ) : (
        <Button type="submit" size="icon" disabled={!value.trim()} aria-label="Send message">
          <ArrowUp className="h-4 w-4" />
        </Button>
      )}
    </form>
  );
}
