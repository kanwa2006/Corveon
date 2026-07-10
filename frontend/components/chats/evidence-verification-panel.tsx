'use client';

import { motion } from 'framer-motion';
import {
  AlertTriangle,
  BadgeCheck,
  BookOpen,
  Brain,
  ExternalLink,
  FileText,
  ScaleIcon,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import type { EvidenceCitation, SourceClass, VerifiedClaim } from '@/lib/api/evidence';
import type { VerificationRunStatus } from '@/lib/hooks/use-evidence-verification';
import { cn } from '@/lib/utils';

const SOURCE_CLASS_LABEL: Record<SourceClass, string> = {
  uploaded_document: 'Your document',
  verified_public: 'Verified public evidence',
  org_trusted: 'Org-trusted evidence',
  ai_reasoning: 'AI reasoning only',
  conflicting_insufficient: 'Conflicting / insufficient evidence',
};

// Tailwind's JIT compiler statically scans source for class-name strings —
// each combo must appear literally here, not assembled from an interpolated
// color token at runtime, or the corresponding CSS never gets generated.
const SOURCE_CLASS_BADGE_STYLE: Record<SourceClass, string> = {
  uploaded_document: 'border-evidence-uploaded/30 bg-evidence-uploaded/10 text-evidence-uploaded',
  verified_public: 'border-evidence-verified/30 bg-evidence-verified/10 text-evidence-verified',
  org_trusted:
    'border-evidence-org-trusted/30 bg-evidence-org-trusted/10 text-evidence-org-trusted',
  ai_reasoning:
    'border-evidence-ai-reasoning/30 bg-evidence-ai-reasoning/10 text-evidence-ai-reasoning',
  conflicting_insufficient:
    'border-evidence-conflicting/30 bg-evidence-conflicting/10 text-evidence-conflicting',
};

const SOURCE_CLASS_ICON: Record<SourceClass, React.ComponentType<{ className?: string }>> = {
  uploaded_document: FileText,
  verified_public: ShieldCheck,
  org_trusted: BadgeCheck,
  ai_reasoning: Brain,
  conflicting_insufficient: ScaleIcon,
};

const SOURCE_NAME_LABEL: Record<string, string> = {
  pubmed: 'PubMed',
  dailymed: 'DailyMed',
  openfda: 'openFDA',
  clinicaltrials: 'ClinicalTrials.gov',
  mesh: 'MeSH',
  rxnorm: 'RxNorm',
  uploaded_document: 'Your document',
};

function SourceClassBadge({ sourceClass }: { sourceClass: SourceClass }): React.JSX.Element {
  const Icon = SOURCE_CLASS_ICON[sourceClass];
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium',
        SOURCE_CLASS_BADGE_STYLE[sourceClass],
      )}
    >
      <Icon className="h-3 w-3" aria-hidden="true" />
      {SOURCE_CLASS_LABEL[sourceClass]}
    </span>
  );
}

function ConfidenceMeter({
  score,
  rationale,
}: {
  score: number;
  rationale: string;
}): React.JSX.Element {
  return (
    <span
      className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"
      title={rationale}
    >
      <span className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
        <span
          className={cn(
            'block h-full rounded-full',
            score >= 70
              ? 'bg-evidence-verified'
              : score >= 40
                ? 'bg-evidence-ai-reasoning'
                : 'bg-evidence-conflicting',
          )}
          style={{ width: `${Math.max(0, Math.min(100, score))}%` }}
        />
      </span>
      {score}% confidence
    </span>
  );
}

function CitationRow({ citation }: { citation: EvidenceCitation }): React.JSX.Element {
  const label = SOURCE_NAME_LABEL[citation.source] ?? citation.source;
  return (
    <li className="flex items-start gap-1.5 text-xs">
      {citation.supports_claim ? (
        <ShieldCheck
          className="mt-0.5 h-3 w-3 shrink-0 text-evidence-verified"
          aria-hidden="true"
        />
      ) : (
        <ShieldAlert
          className="mt-0.5 h-3 w-3 shrink-0 text-evidence-conflicting"
          aria-hidden="true"
        />
      )}
      <span className="text-muted-foreground">
        <span className="font-medium text-foreground">{label}</span> — {citation.title}
        {citation.published_date ? ` (${citation.published_date.slice(0, 4)})` : ''}
        {citation.url && (
          <a
            href={citation.url}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-1 inline-flex items-center gap-0.5 text-primary hover:underline"
            aria-label={`Open source for ${citation.title}`}
          >
            <ExternalLink className="h-3 w-3" aria-hidden="true" />
          </a>
        )}
      </span>
    </li>
  );
}

function ClaimCard({ claim }: { claim: VerifiedClaim }): React.JSX.Element {
  return (
    <motion.li
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-lg border border-border bg-card p-3"
    >
      <p className="text-sm text-card-foreground">{claim.text}</p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <SourceClassBadge sourceClass={claim.source_class} />
        <ConfidenceMeter score={claim.confidence_score} rationale={claim.confidence_rationale} />
      </div>

      {claim.flags.length > 0 && (
        <ul className="mt-2 space-y-1">
          {claim.flags.map((flag, index) => (
            <li
              key={`${flag.type}-${index}`}
              className="flex items-start gap-1.5 text-xs text-evidence-ai-reasoning"
            >
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />
              <span>{flag.detail}</span>
            </li>
          ))}
        </ul>
      )}

      {claim.citations.length > 0 && (
        <ul className="mt-2 space-y-1 border-t border-border pt-2">
          {claim.citations.map((citation, index) => (
            <CitationRow
              key={`${citation.source}-${citation.identifier ?? index}`}
              citation={citation}
            />
          ))}
        </ul>
      )}
    </motion.li>
  );
}

interface EvidenceVerificationPanelProps {
  status: VerificationRunStatus;
  claims: VerifiedClaim[];
  errorMessage: string | null;
  onVerify: () => void;
  onDismiss: () => void;
}

export function EvidenceVerificationPanel({
  status,
  claims,
  errorMessage,
  onVerify,
  onDismiss,
}: EvidenceVerificationPanelProps): React.JSX.Element {
  if (status === 'idle') {
    return (
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={onVerify}
        className="h-auto gap-1 px-1.5 py-0.5 text-xs text-muted-foreground hover:text-foreground"
      >
        <BookOpen className="h-3 w-3" aria-hidden="true" />
        Verify claims
      </Button>
    );
  }

  return (
    <div className="w-full max-w-full rounded-lg border border-border bg-muted/30 p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-xs font-medium text-foreground">
          <BookOpen className="h-3.5 w-3.5" aria-hidden="true" />
          Evidence verification
        </span>
        <button
          type="button"
          onClick={onDismiss}
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          Dismiss
        </button>
      </div>

      {(status === 'starting' || (status === 'streaming' && claims.length === 0)) && (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current [animation-delay:-0.3s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current [animation-delay:-0.15s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current" />
          Checking claims against public medical evidence…
        </p>
      )}

      {claims.length > 0 && (
        <ul className="space-y-2">
          {claims.map((claim) => (
            <ClaimCard key={claim.id} claim={claim} />
          ))}
        </ul>
      )}

      {status === 'done' && claims.length === 0 && (
        <p className="text-xs text-muted-foreground">
          No independently verifiable claims were found in this message.
        </p>
      )}

      {status === 'error' && errorMessage && (
        <p className="flex items-center gap-1.5 text-xs text-evidence-conflicting">
          <AlertTriangle className="h-3 w-3 shrink-0" aria-hidden="true" />
          {errorMessage}
        </p>
      )}
    </div>
  );
}
