'use client';

import { motion } from 'framer-motion';
import {
  AlertTriangle,
  ExternalLink,
  Pill,
  ShieldAlert,
  ShieldQuestion,
  Stethoscope,
} from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import type {
  FindingSeverity,
  InteractionFinding,
  NormalizedMedication,
  RenalFinding,
  RenalParameters,
  Sex,
} from '@/lib/api/medication';
import type { MedicationAnalysisStatus } from '@/lib/hooks/use-medication-analysis';
import { cn } from '@/lib/utils';

// Tailwind's JIT compiler statically scans source for class-name strings —
// each combo must appear literally here, not assembled from an interpolated
// color token at runtime, or the corresponding CSS never gets generated
// (same constraint as evidence-verification-panel.tsx's SourceClassBadge).
const SEVERITY_STYLE: Record<FindingSeverity, string> = {
  major: 'border-evidence-conflicting/30 bg-evidence-conflicting/10 text-evidence-conflicting',
  moderate:
    'border-evidence-ai-reasoning/30 bg-evidence-ai-reasoning/10 text-evidence-ai-reasoning',
  minor: 'border-border bg-muted text-muted-foreground',
  unclassified: 'border-evidence-uploaded/30 bg-evidence-uploaded/10 text-evidence-uploaded',
};

const SEVERITY_LABEL: Record<FindingSeverity, string> = {
  major: 'Major',
  moderate: 'Moderate',
  minor: 'Minor',
  unclassified: 'Unclassified — read source',
};

const SOURCE_LABEL: Record<string, string> = {
  ddinter: 'DDInter 2.0',
  openfda_label: 'openFDA label',
};

function SeverityBadge({ severity }: { severity: FindingSeverity }): React.JSX.Element {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium',
        SEVERITY_STYLE[severity],
      )}
    >
      {severity === 'unclassified' ? (
        <ShieldQuestion className="h-3 w-3" aria-hidden="true" />
      ) : (
        <ShieldAlert className="h-3 w-3" aria-hidden="true" />
      )}
      {SEVERITY_LABEL[severity]}
    </span>
  );
}

function MedicationChip({ medication }: { medication: NormalizedMedication }): React.JSX.Element {
  return (
    <li
      className="flex items-center gap-2 rounded-md border border-border px-2.5 py-1.5 text-xs"
      title={medication.raw_text}
    >
      <Pill className="h-3.5 w-3.5 shrink-0 text-evidence-uploaded" aria-hidden="true" />
      <span className="min-w-0 flex-1 truncate font-medium">{medication.name}</span>
      {medication.dose && <span className="shrink-0 text-muted-foreground">{medication.dose}</span>}
      {medication.frequency && (
        <span className="shrink-0 text-muted-foreground">{medication.frequency}</span>
      )}
      {medication.rxcui ? (
        <span className="shrink-0 rounded-full bg-evidence-verified/10 px-1.5 py-0.5 text-[10px] font-medium text-evidence-verified">
          RxCUI {medication.rxcui}
        </span>
      ) : (
        <span className="shrink-0 rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
          unmatched
        </span>
      )}
    </li>
  );
}

function FindingCard({
  finding,
  medicationNameById,
}: {
  finding: InteractionFinding;
  medicationNameById: Map<string, string>;
}): React.JSX.Element {
  const nameA = medicationNameById.get(finding.medication_a_id) ?? 'a medication';
  const nameB = medicationNameById.get(finding.medication_b_id) ?? 'another medication';
  const url = typeof finding.provenance.url === 'string' ? finding.provenance.url : null;

  return (
    <motion.li
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-lg border border-border bg-card p-3"
    >
      <p className="text-sm font-medium text-card-foreground">
        {nameA} + {nameB}
      </p>
      <div className="mt-1.5 flex flex-wrap items-center gap-2">
        <SeverityBadge severity={finding.severity} />
        <span className="text-xs text-muted-foreground">
          {SOURCE_LABEL[finding.source] ?? finding.source}
        </span>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        {finding.explanation}
        {url && (
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-1 inline-flex items-center gap-0.5 text-primary hover:underline"
            aria-label="Open source label"
          >
            <ExternalLink className="h-3 w-3" aria-hidden="true" />
          </a>
        )}
      </p>
    </motion.li>
  );
}

function RenalFindingCard({
  finding,
  medicationNameById,
}: {
  finding: RenalFinding;
  medicationNameById: Map<string, string>;
}): React.JSX.Element {
  const name = medicationNameById.get(finding.medication_id) ?? 'a medication';

  return (
    <motion.li
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-lg border border-border bg-card p-3"
    >
      <p className="flex items-center gap-1.5 text-sm font-medium text-card-foreground">
        <Stethoscope className="h-3.5 w-3.5 shrink-0 text-evidence-uploaded" aria-hidden="true" />
        {name}
      </p>
      <div className="mt-1.5 flex flex-wrap items-center gap-2">
        <SeverityBadge severity={finding.severity} />
        <span className="text-xs text-muted-foreground">
          CrCl {finding.crcl_ml_min} mL/min · eGFR {finding.egfr_ml_min} mL/min · threshold{' '}
          {finding.threshold_ml_min} mL/min
        </span>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">{finding.explanation}</p>
    </motion.li>
  );
}

interface MedicationPanelProps {
  status: MedicationAnalysisStatus;
  medications: NormalizedMedication[];
  findings: InteractionFinding[];
  renalFindings: RenalFinding[];
  errorMessage: string | null;
  onAnalyze: (rawText: string, renalParams: RenalParameters | null) => void;
  onReset: () => void;
}

const inputClassName =
  'rounded-md border border-input bg-transparent px-2 py-1.5 text-xs placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';

export function MedicationPanel({
  status,
  medications,
  findings,
  renalFindings,
  errorMessage,
  onAnalyze,
  onReset,
}: MedicationPanelProps): React.JSX.Element {
  const [draft, setDraft] = useState('');
  const [showRenal, setShowRenal] = useState(false);
  const [ageYears, setAgeYears] = useState('');
  const [weightKg, setWeightKg] = useState('');
  const [sex, setSex] = useState<Sex>('female');
  const [serumCreatinine, setSerumCreatinine] = useState('');
  const [heightCm, setHeightCm] = useState('');

  const isBusy = status === 'starting' || status === 'streaming';
  const medicationNameById = new Map(medications.map((m) => [m.id, m.name]));
  const renalFieldsComplete =
    ageYears.trim() !== '' &&
    weightKg.trim() !== '' &&
    serumCreatinine.trim() !== '' &&
    heightCm.trim() !== '';
  const canAnalyze = draft.trim() !== '' && (!showRenal || renalFieldsComplete);

  const handleAnalyze = (): void => {
    if (!canAnalyze || isBusy) return;
    const renalParams: RenalParameters | null =
      showRenal && renalFieldsComplete
        ? {
            age_years: Number(ageYears),
            weight_kg: Number(weightKg),
            sex,
            serum_creatinine_mg_dl: Number(serumCreatinine),
            height_cm: Number(heightCm),
          }
        : null;
    onAnalyze(draft.trim(), renalParams);
  };

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-sm font-semibold text-card-foreground">
          Medication safety
        </h2>
        {status !== 'idle' && (
          <button
            type="button"
            onClick={() => {
              onReset();
              setDraft('');
            }}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            Start over
          </button>
        )}
      </div>

      {status === 'idle' && (
        <>
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="List medications, one per line — e.g. metformin 500mg twice daily"
            rows={2}
            className="min-h-[3rem] resize-none rounded-md border border-input bg-transparent px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />

          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={showRenal}
              onChange={(e) => setShowRenal(e.target.checked)}
              className="h-3.5 w-3.5"
            />
            Include renal function (optional) — checks DOACs/aminoglycosides/vancomycin against
            Cockcroft-Gault + CKD-EPI 2021
          </label>

          {showRenal && (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              <label className="flex flex-col gap-0.5 text-[10px] text-muted-foreground">
                Age (years)
                <input
                  type="number"
                  min={0}
                  max={120}
                  value={ageYears}
                  onChange={(e) => setAgeYears(e.target.value)}
                  className={inputClassName}
                />
              </label>
              <label className="flex flex-col gap-0.5 text-[10px] text-muted-foreground">
                Weight (kg)
                <input
                  type="number"
                  min={0}
                  step="0.1"
                  value={weightKg}
                  onChange={(e) => setWeightKg(e.target.value)}
                  className={inputClassName}
                />
              </label>
              <label className="flex flex-col gap-0.5 text-[10px] text-muted-foreground">
                Sex
                <select
                  value={sex}
                  onChange={(e) => setSex(e.target.value as Sex)}
                  className={inputClassName}
                >
                  <option value="female">Female</option>
                  <option value="male">Male</option>
                </select>
              </label>
              <label className="flex flex-col gap-0.5 text-[10px] text-muted-foreground">
                Serum creatinine (mg/dL)
                <input
                  type="number"
                  min={0}
                  step="0.1"
                  value={serumCreatinine}
                  onChange={(e) => setSerumCreatinine(e.target.value)}
                  className={inputClassName}
                />
              </label>
              <label className="flex flex-col gap-0.5 text-[10px] text-muted-foreground">
                Height (cm)
                <input
                  type="number"
                  min={0}
                  step="0.1"
                  value={heightCm}
                  onChange={(e) => setHeightCm(e.target.value)}
                  className={inputClassName}
                />
              </label>
            </div>
          )}

          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleAnalyze}
            disabled={!canAnalyze}
            className="self-start"
          >
            <Pill className="h-3.5 w-3.5" aria-hidden="true" />
            Check for interactions
          </Button>
        </>
      )}

      {(status === 'starting' || (status === 'streaming' && medications.length === 0)) && (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current [animation-delay:-0.3s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current [animation-delay:-0.15s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current" />
          Parsing and normalizing medications…
        </p>
      )}

      {medications.length > 0 && (
        <ul className="flex flex-col gap-1.5">
          {medications.map((medication) => (
            <MedicationChip key={medication.id} medication={medication} />
          ))}
        </ul>
      )}

      {findings.length > 0 && (
        <ul className="flex flex-col gap-2 border-t border-border pt-2">
          {findings.map((finding) => (
            <FindingCard
              key={finding.id}
              finding={finding}
              medicationNameById={medicationNameById}
            />
          ))}
        </ul>
      )}

      {renalFindings.length > 0 && (
        <ul className="flex flex-col gap-2 border-t border-border pt-2">
          {renalFindings.map((finding) => (
            <RenalFindingCard
              key={finding.id}
              finding={finding}
              medicationNameById={medicationNameById}
            />
          ))}
        </ul>
      )}

      {status === 'done' && medications.length > 0 && findings.length === 0 && (
        <p className="text-xs text-muted-foreground">
          No known interactions found among these medications.
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
