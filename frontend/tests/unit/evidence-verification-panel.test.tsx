import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { EvidenceVerificationPanel } from '@/components/chats/evidence-verification-panel';
import type { VerifiedClaim } from '@/lib/api/evidence';

const claim: VerifiedClaim = {
  id: 'c1',
  ordinal: 0,
  text: 'Metformin is first-line therapy for type 2 diabetes.',
  source_class: 'verified_public',
  confidence_score: 82,
  confidence_rationale: 'Base 70 for verified_public evidence; +8 for 1 independent source.',
  flags: [],
  citations: [
    {
      source: 'pubmed',
      title: 'A study on metformin',
      url: 'https://pubmed.ncbi.nlm.nih.gov/12345678/',
      identifier: '12345678',
      published_date: '2023-01-01',
      supports_claim: true,
    },
  ],
};

describe('EvidenceVerificationPanel', () => {
  it('renders a trigger button when idle', () => {
    render(
      <EvidenceVerificationPanel
        status="idle"
        claims={[]}
        errorMessage={null}
        onVerify={vi.fn()}
        onDismiss={vi.fn()}
      />,
    );
    expect(screen.getByRole('button', { name: /verify claims/i })).toBeInTheDocument();
  });

  it('calls onVerify when the trigger is clicked', () => {
    const onVerify = vi.fn();
    render(
      <EvidenceVerificationPanel
        status="idle"
        claims={[]}
        errorMessage={null}
        onVerify={onVerify}
        onDismiss={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /verify claims/i }));
    expect(onVerify).toHaveBeenCalledOnce();
  });

  it('shows a progress indicator while streaming with no claims yet', () => {
    render(
      <EvidenceVerificationPanel
        status="streaming"
        claims={[]}
        errorMessage={null}
        onVerify={vi.fn()}
        onDismiss={vi.fn()}
      />,
    );
    expect(
      screen.getByText(/checking claims against public medical evidence/i),
    ).toBeInTheDocument();
  });

  it('renders a claim with its source class, confidence, and citation', () => {
    render(
      <EvidenceVerificationPanel
        status="done"
        claims={[claim]}
        errorMessage={null}
        onVerify={vi.fn()}
        onDismiss={vi.fn()}
      />,
    );
    expect(screen.getByText(claim.text)).toBeInTheDocument();
    expect(screen.getByText('Verified public evidence')).toBeInTheDocument();
    expect(screen.getByText('82% confidence')).toBeInTheDocument();
    expect(screen.getByText(/A study on metformin/)).toBeInTheDocument();
  });

  it('renders flags as warnings', () => {
    const flaggedClaim: VerifiedClaim = {
      ...claim,
      source_class: 'conflicting_insufficient',
      flags: [{ type: 'contradictory', detail: 'Sources disagree on dosage timing.' }],
    };
    render(
      <EvidenceVerificationPanel
        status="done"
        claims={[flaggedClaim]}
        errorMessage={null}
        onVerify={vi.fn()}
        onDismiss={vi.fn()}
      />,
    );
    expect(screen.getByText('Sources disagree on dosage timing.')).toBeInTheDocument();
  });

  it('shows a no-claims message when done with nothing found', () => {
    render(
      <EvidenceVerificationPanel
        status="done"
        claims={[]}
        errorMessage={null}
        onVerify={vi.fn()}
        onDismiss={vi.fn()}
      />,
    );
    expect(screen.getByText(/no independently verifiable claims were found/i)).toBeInTheDocument();
  });

  it('shows the error message on error status', () => {
    render(
      <EvidenceVerificationPanel
        status="error"
        claims={[]}
        errorMessage="No AI provider is currently reachable."
        onVerify={vi.fn()}
        onDismiss={vi.fn()}
      />,
    );
    expect(screen.getByText('No AI provider is currently reachable.')).toBeInTheDocument();
  });

  it('calls onDismiss when Dismiss is clicked', () => {
    const onDismiss = vi.fn();
    render(
      <EvidenceVerificationPanel
        status="done"
        claims={[claim]}
        errorMessage={null}
        onVerify={vi.fn()}
        onDismiss={onDismiss}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /dismiss/i }));
    expect(onDismiss).toHaveBeenCalledOnce();
  });
});
