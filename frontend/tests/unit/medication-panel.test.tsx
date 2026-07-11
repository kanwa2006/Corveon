import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { MedicationPanel } from '@/components/chats/medication-panel';
import type {
  DiscrepancyFinding,
  InteractionFinding,
  NormalizedMedication,
  PipFinding,
  RenalFinding,
} from '@/lib/api/medication';

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

const renalFinding: RenalFinding = {
  id: 'r1',
  medication_id: 'm1',
  crcl_ml_min: 12.7,
  egfr_ml_min: 17.9,
  threshold_ml_min: 30.0,
  severity: 'major',
  rule_id: 'renal_threshold:warfarin',
  explanation: 'Both equations are below threshold.',
};

const pipFinding: PipFinding = {
  id: 'pip1',
  medication_id: 'm1',
  source: 'beers_2023',
  direction: 'avoid',
  severity: 'major',
  rule_id: 'beers_2023:CRIT-1',
  drug_names: ['warfarin'],
  matched_condition: null,
  explanation: 'AGS Beers Criteria 2023: avoid warfarin — anticoagulant burden.',
  narrative: null,
};

const discrepancyFinding: DiscrepancyFinding = {
  id: 'd1',
  kind: 'added',
  current_medication_id: 'm1',
  previous_medication_id: null,
  rule_id: 'discrepancy:added',
  explanation: 'Warfarin appears in the current list but not the previous one.',
  narrative: null,
  provenance: { name: 'warfarin', rxcui: null },
};

const baseProps = {
  medications: [] as NormalizedMedication[],
  previousMedications: [] as NormalizedMedication[],
  findings: [] as InteractionFinding[],
  renalFindings: [] as RenalFinding[],
  pipFindings: [] as PipFinding[],
  discrepancyFindings: [] as DiscrepancyFinding[],
  errorMessage: null as string | null,
};

describe('MedicationPanel', () => {
  it('renders a textarea and disabled button when idle with no input', () => {
    render(<MedicationPanel status="idle" {...baseProps} onAnalyze={vi.fn()} onReset={vi.fn()} />);
    expect(screen.getByRole('button', { name: /check for interactions/i })).toBeDisabled();
  });

  it('calls onAnalyze with the trimmed textarea value and null params when no optional section is touched', () => {
    const onAnalyze = vi.fn();
    render(
      <MedicationPanel status="idle" {...baseProps} onAnalyze={onAnalyze} onReset={vi.fn()} />,
    );

    fireEvent.change(screen.getByPlaceholderText(/list medications/i), {
      target: { value: '  metformin 500mg  ' },
    });
    fireEvent.click(screen.getByRole('button', { name: /check for interactions/i }));

    expect(onAnalyze).toHaveBeenCalledWith('metformin 500mg', null);
  });

  it('shows a progress indicator while streaming with no medications yet', () => {
    render(
      <MedicationPanel status="streaming" {...baseProps} onAnalyze={vi.fn()} onReset={vi.fn()} />,
    );
    expect(screen.getByText(/parsing and normalizing medications/i)).toBeInTheDocument();
  });

  it('renders normalized medications with RxCUI badge or unmatched label', () => {
    render(
      <MedicationPanel
        status="streaming"
        {...baseProps}
        medications={[medicationA, medicationB]}
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
        {...baseProps}
        medications={[medicationA, medicationB]}
        findings={[finding]}
        onAnalyze={vi.fn()}
        onReset={vi.fn()}
      />,
    );
    expect(screen.getByText('Warfarin + Aspirin')).toBeInTheDocument();
    expect(screen.getByText('Major')).toBeInTheDocument();
    expect(screen.getByText('DDInter 2.0')).toBeInTheDocument();
    expect(screen.getByText('Increased bleeding risk.')).toBeInTheDocument();
  });

  it('renders a renal finding with CrCl/eGFR values and severity', () => {
    render(
      <MedicationPanel
        status="done"
        {...baseProps}
        medications={[medicationA]}
        renalFindings={[renalFinding]}
        onAnalyze={vi.fn()}
        onReset={vi.fn()}
      />,
    );
    expect(screen.getByText('Warfarin', { selector: 'p' })).toBeInTheDocument();
    expect(screen.getByText(/CrCl 12\.7 mL\/min/)).toBeInTheDocument();
    expect(screen.getByText(/eGFR 17\.9 mL\/min/)).toBeInTheDocument();
    expect(screen.getByText('Both equations are below threshold.')).toBeInTheDocument();
  });

  it('renders a PIP finding with source label and severity', () => {
    render(
      <MedicationPanel
        status="done"
        {...baseProps}
        medications={[medicationA]}
        pipFindings={[pipFinding]}
        onAnalyze={vi.fn()}
        onReset={vi.fn()}
      />,
    );
    expect(screen.getByText('Warfarin', { selector: 'p' })).toBeInTheDocument();
    expect(screen.getByText('AGS Beers Criteria 2023')).toBeInTheDocument();
    expect(
      screen.getByText('AGS Beers Criteria 2023: avoid warfarin — anticoagulant burden.'),
    ).toBeInTheDocument();
  });

  it('renders a START PIP finding by its drug names when medication_id is null', () => {
    const startFinding: PipFinding = {
      ...pipFinding,
      id: 'pip2',
      medication_id: null,
      direction: 'start_consider',
      drug_names: ['calcium and vitamin d'],
    };
    render(
      <MedicationPanel
        status="done"
        {...baseProps}
        medications={[medicationA]}
        pipFindings={[startFinding]}
        onAnalyze={vi.fn()}
        onReset={vi.fn()}
      />,
    );
    expect(screen.getByText(/Consider starting: calcium and vitamin d/)).toBeInTheDocument();
  });

  it('renders a discrepancy finding with its kind label', () => {
    render(
      <MedicationPanel
        status="done"
        {...baseProps}
        medications={[medicationA]}
        discrepancyFindings={[discrepancyFinding]}
        onAnalyze={vi.fn()}
        onReset={vi.fn()}
      />,
    );
    expect(screen.getByText('Warfarin', { selector: 'p' })).toBeInTheDocument();
    expect(screen.getByText('Added')).toBeInTheDocument();
    expect(
      screen.getByText('Warfarin appears in the current list but not the previous one.'),
    ).toBeInTheDocument();
  });

  it('renders a narrative note distinctly from the deterministic explanation when present', () => {
    render(
      <MedicationPanel
        status="done"
        {...baseProps}
        medications={[medicationA]}
        pipFindings={[{ ...pipFinding, narrative: 'A plain-language note.' }]}
        onAnalyze={vi.fn()}
        onReset={vi.fn()}
      />,
    );
    expect(screen.getByText('A plain-language note.')).toBeInTheDocument();
  });

  it('renders the previous medication list under its own heading', () => {
    render(
      <MedicationPanel
        status="done"
        {...baseProps}
        medications={[medicationA]}
        previousMedications={[medicationB]}
        discrepancyFindings={[discrepancyFinding]}
        onAnalyze={vi.fn()}
        onReset={vi.fn()}
      />,
    );
    expect(screen.getByText('Previous list')).toBeInTheDocument();
    expect(screen.getByText('Aspirin')).toBeInTheDocument();
  });

  it('shows a no-interactions message when done with medications but no findings', () => {
    render(
      <MedicationPanel
        status="done"
        {...baseProps}
        medications={[medicationA]}
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
        {...baseProps}
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
        {...baseProps}
        medications={[medicationA]}
        onAnalyze={vi.fn()}
        onReset={onReset}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /start over/i }));
    expect(onReset).toHaveBeenCalledOnce();
  });

  describe('renal parameters', () => {
    it('reveals renal fields when the checkbox is checked, hidden by default', () => {
      render(
        <MedicationPanel status="idle" {...baseProps} onAnalyze={vi.fn()} onReset={vi.fn()} />,
      );
      expect(screen.queryByText(/age \(years\)/i)).not.toBeInTheDocument();

      fireEvent.click(screen.getByRole('checkbox', { name: /include renal function/i }));
      expect(screen.getByText(/age \(years\)/i)).toBeInTheDocument();
    });

    it('disables the trigger until all renal fields are filled once the checkbox is checked', () => {
      render(
        <MedicationPanel status="idle" {...baseProps} onAnalyze={vi.fn()} onReset={vi.fn()} />,
      );
      fireEvent.change(screen.getByPlaceholderText(/list medications/i), {
        target: { value: 'apixaban 5mg' },
      });
      fireEvent.click(screen.getByRole('checkbox', { name: /include renal function/i }));

      const trigger = screen.getByRole('button', { name: /check for interactions/i });
      expect(trigger).toBeDisabled();

      fireEvent.change(screen.getByLabelText(/age \(years\)/i), { target: { value: '85' } });
      fireEvent.change(screen.getByLabelText(/weight \(kg\)/i), { target: { value: '50' } });
      fireEvent.change(screen.getByLabelText(/serum creatinine/i), { target: { value: '3.0' } });
      fireEvent.change(screen.getByLabelText(/height \(cm\)/i), { target: { value: '170' } });

      expect(trigger).toBeEnabled();
    });

    it('calls onAnalyze with the entered renal parameters', () => {
      const onAnalyze = vi.fn();
      render(
        <MedicationPanel status="idle" {...baseProps} onAnalyze={onAnalyze} onReset={vi.fn()} />,
      );
      fireEvent.change(screen.getByPlaceholderText(/list medications/i), {
        target: { value: 'apixaban 5mg' },
      });
      fireEvent.click(screen.getByRole('checkbox', { name: /include renal function/i }));
      fireEvent.change(screen.getByLabelText(/age \(years\)/i), { target: { value: '85' } });
      fireEvent.change(screen.getByLabelText(/weight \(kg\)/i), { target: { value: '50' } });
      fireEvent.change(screen.getByLabelText(/^sex/i), { target: { value: 'male' } });
      fireEvent.change(screen.getByLabelText(/serum creatinine/i), { target: { value: '3.0' } });
      fireEvent.change(screen.getByLabelText(/height \(cm\)/i), { target: { value: '170' } });

      fireEvent.click(screen.getByRole('button', { name: /check for interactions/i }));

      expect(onAnalyze).toHaveBeenCalledWith('apixaban 5mg', {
        age_years: 85,
        weight_kg: 50,
        sex: 'male',
        serum_creatinine_mg_dl: 3.0,
        height_cm: 170,
      });
    });
  });

  describe('PIP screening', () => {
    it('reveals only the age field and conditions input when the checkbox is checked', () => {
      render(
        <MedicationPanel status="idle" {...baseProps} onAnalyze={vi.fn()} onReset={vi.fn()} />,
      );
      expect(screen.queryByText(/age \(years\)/i)).not.toBeInTheDocument();

      fireEvent.click(screen.getByRole('checkbox', { name: /screen for inappropriate/i }));
      expect(screen.getByText(/age \(years\)/i)).toBeInTheDocument();
      expect(screen.getByText(/conditions/i)).toBeInTheDocument();
      expect(screen.queryByText(/weight \(kg\)/i)).not.toBeInTheDocument();
    });

    it('disables the trigger until age is filled, and calls onAnalyze with age_years and conditions', () => {
      const onAnalyze = vi.fn();
      render(
        <MedicationPanel status="idle" {...baseProps} onAnalyze={onAnalyze} onReset={vi.fn()} />,
      );
      fireEvent.change(screen.getByPlaceholderText(/list medications/i), {
        target: { value: 'diphenhydramine 25mg' },
      });
      fireEvent.click(screen.getByRole('checkbox', { name: /screen for inappropriate/i }));

      const trigger = screen.getByRole('button', { name: /check for interactions/i });
      expect(trigger).toBeDisabled();

      fireEvent.change(screen.getByLabelText(/age \(years\)/i), { target: { value: '78' } });
      expect(trigger).toBeEnabled();

      fireEvent.change(screen.getByLabelText(/conditions/i), {
        target: { value: 'heart failure, osteoporosis' },
      });
      fireEvent.click(trigger);

      expect(onAnalyze).toHaveBeenCalledWith('diphenhydramine 25mg', {
        age_years: 78,
        conditions: ['heart failure', 'osteoporosis'],
      });
    });
  });

  describe('discrepancy classification', () => {
    it('reveals the previous-list textarea when the checkbox is checked', () => {
      render(
        <MedicationPanel status="idle" {...baseProps} onAnalyze={vi.fn()} onReset={vi.fn()} />,
      );
      expect(
        screen.queryByPlaceholderText(/list the previous medications/i),
      ).not.toBeInTheDocument();

      fireEvent.click(screen.getByRole('checkbox', { name: /compare to a previous/i }));
      expect(screen.getByPlaceholderText(/list the previous medications/i)).toBeInTheDocument();
    });

    it('disables the trigger until the previous list is filled, and calls onAnalyze with previous_raw_text', () => {
      const onAnalyze = vi.fn();
      render(
        <MedicationPanel status="idle" {...baseProps} onAnalyze={onAnalyze} onReset={vi.fn()} />,
      );
      fireEvent.change(screen.getByPlaceholderText(/list medications/i), {
        target: { value: 'lisinopril 10mg' },
      });
      fireEvent.click(screen.getByRole('checkbox', { name: /compare to a previous/i }));

      const trigger = screen.getByRole('button', { name: /check for interactions/i });
      expect(trigger).toBeDisabled();

      fireEvent.change(screen.getByPlaceholderText(/list the previous medications/i), {
        target: { value: 'metformin 500mg' },
      });
      expect(trigger).toBeEnabled();

      fireEvent.click(trigger);

      expect(onAnalyze).toHaveBeenCalledWith('lisinopril 10mg', {
        previous_raw_text: 'metformin 500mg',
      });
    });
  });
});
