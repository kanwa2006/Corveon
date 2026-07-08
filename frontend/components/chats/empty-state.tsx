import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  action?: ReactNode;
  /** Heading level for `title` — must match this instance's position in the
   * page's heading outline (axe `heading-order`). Defaults to `h2`, correct
   * when EmptyState sits directly under a page's own `<h1>`; pass `h3` when
   * it's nested one level deeper (e.g. under a Card's `<h2>` title). */
  as?: 'h2' | 'h3';
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  as: Heading = 'h2',
}: EmptyStateProps): React.JSX.Element {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-border px-6 py-16 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted">
        <Icon className="h-6 w-6 text-muted-foreground" aria-hidden="true" />
      </div>
      <div className="space-y-1">
        <Heading className="font-display text-lg font-semibold">{title}</Heading>
        <p className="max-w-sm text-sm text-muted-foreground">{description}</p>
      </div>
      {action}
    </div>
  );
}
