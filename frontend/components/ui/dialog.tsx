'use client';

import { forwardRef, useImperativeHandle, useRef, type ReactNode } from 'react';

export interface DialogHandle {
  showModal: () => void;
  close: () => void;
}

interface DialogProps {
  title: string;
  description?: string;
  children: ReactNode;
}

/**
 * Built on the native <dialog> element — free focus-trapping, ESC-to-close,
 * and a styleable ::backdrop, with no extra dependency (no Radix installed
 * yet; revisit if a future feature needs more than this).
 */
export const Dialog = forwardRef<DialogHandle, DialogProps>(function Dialog(
  { title, description, children },
  ref,
) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useImperativeHandle(ref, () => ({
    showModal: () => dialogRef.current?.showModal(),
    close: () => dialogRef.current?.close(),
  }));

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby="dialog-title"
      className="w-[min(28rem,calc(100vw-2rem))] rounded-xl border border-border bg-card p-0 text-card-foreground shadow-2xl backdrop:bg-black/60 backdrop:backdrop-blur-sm"
    >
      <div className="p-6">
        <h2 id="dialog-title" className="font-display text-lg font-semibold">
          {title}
        </h2>
        {description && <p className="mt-1.5 text-sm text-muted-foreground">{description}</p>}
        <div className="mt-5">{children}</div>
      </div>
    </dialog>
  );
});
