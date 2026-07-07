import { AlertCircle } from 'lucide-react';
import { type HTMLAttributes } from 'react';

import { cn } from '@/lib/utils';

export function AlertError({
  className,
  children,
  ...props
}: HTMLAttributes<HTMLDivElement>): React.JSX.Element {
  return (
    <div
      role="alert"
      className={cn(
        'flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive',
        className,
      )}
      {...props}
    >
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <span>{children}</span>
    </div>
  );
}
