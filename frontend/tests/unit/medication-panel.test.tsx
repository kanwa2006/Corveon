import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { MedicationPanel } from '@/components/chats/medication-panel';
import type { InteractionFinding, NormalizedMedication } from '@/lib/api/medication';

const medicationA: NormalizedMedication = {
  id: 'm1',
  raw_text: 'warfarin 5mg',
  name: 'Warfarin',
  rxcui: '855290',
  dose: '5mg',
  route: null,
  frequency: 'once daily',
};

const medicationB: NormalizedMedication = {
  id: 'm2',
  raw_text: 'aspirin 81mg',
  name: 'Aspirin',
  rxcui: null,
  dose: '81mg',
  route: null,
  frequency: 'once daily',
};

const finding: InteractionFinding = {
  id: 'f1',
  medication_a_id: 'm1',
  medication_b_id: 'm2',
  severity: 'major',
  source: 'ddinter',
  rule_id: 'rule-1',
  explanation: 'Increased bleeding risk.',
  provenance: {},
};

describe('MedicationPanel', () => {
  it('renders a textarea and disabled button when idle with no input', () => {
    render(
      <MedicationPanel
        status="idle"
        medications={[]}
        findings={[]}
        errorMessage={null}
        onAnalyze={vi.fn()}
        onReset={vi.fn()}
      />,
    );
    expect(screen.getByRole('button', { name: /check for interactions/i })).toBeDisabled();
  });

  it('calls onAnalyze with the trimmed textarea value when clicked', () => {
    const onAnalyze = vi.fn();
    render(
      <MedicationPanel
        status="idle"
        medications={[]}
        findings={[]}
        errorMessage={null}
        onAnalyze={onAnalyze}
        onReset={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText(/list medications/i), {
      target: { value: '  metformin 500mg  ' },
    });
    fireEvent.click(screen.getByRole('button', { name: /check for interactions/i }));

    expect(onAnalyze).toHaveBeenCalledWith('metformin 500mg');
  });

  it('shows a progress indicator while streaming with no medications yet', () => {
    render(
      <MedicationPanel
        status="streaming"
        medications={[]}
        findings={[]}
        errorMessage={null}
        onAnalyze={vi.fn()}
        onReset={vi.fn()}
      />,
    );
    expect(screen.getByText(/parsing and normalizing medications/i)).toBeInTheDocument();
  });

  it('renders normalized medications with RxCUI badge or unmatched label', () => {
    render(
      <MedicationPanel
        status="streaming"
        medications={[medicationA, medicationB]}
        findings={[]}
        errorMessage={null}
        onAnalyze={vi.fn()}
        onReset={vi.fn()}
      />,
    );
    expect(screen.getByText('Warfarin')).toBeInTheDocument();
    expect(screen.getByText('RxCUI 855290')).toBeInTheDocument();
    expect(screen.getByText('Aspirin')).toBeInTheDocument();
    expect(screen.getByText('unmatched')).toBeInTheDocument();
  });

  it('renders an interaction finding with severity and source', () => {
    render(
      <MedicationPanel
        status="done"
        medications={[medicationA, medicationB]}
        findings={[finding]}
        errorMessage={null}
        onAnalyze={vi.fn()}
        onReset={vi.fn()}
      />,
    );
    expect(screen.getByText('Warfarin + Aspirin')).toBeInTheDocument();
    expect(screen.getByText('Major')).toBeInTheDocument();
    expect(screen.getByText('DDInter 2.0')).toBeInTheDocument();
    expect(screen.getByText('Increased bleeding risk.')).toBeInTheDocument();
  });

  it('shows a no-interactions message when done with medications but no findings', () => {
    render(
      <MedicationPanel
        status="done"
        medications={[medicationA]}
        findings={[]}
        errorMessage={null}
        onAnalyze={vi.fn()}
        onReset={vi.fn()}
      />,
    );
    expect(screen.getByText(/no known interactions found/i)).toBeInTheDocument();
  });

  it('shows the error message on error status', () => {
    render(
      <MedicationPanel
        status="error"
        medications={[]}
        findings={[]}
        errorMessage="No AI provider is currently reachable."
        onAnalyze={vi.fn()}
        onReset={vi.fn()}
      />,
    );
    expect(screen.getByText('No AI provider is currently reachable.')).toBeInTheDocument();
  });

  it('calls onReset when Start over is clicked', () => {
    const onReset = vi.fn();
    render(
      <MedicationPanel
        status="done"
        medications={[medicationA]}
        findings={[]}
        errorMessage={null}
        onAnalyze={vi.fn()}
        onReset={onReset}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /start over/i }));
    expect(onReset).toHaveBeenCalledOnce();
  });
});
