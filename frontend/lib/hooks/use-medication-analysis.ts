'use client';

import { useCallback, useRef, useState } from 'react';

import {
  streamMedicationAnalysis,
  type AnalysisParameters,
  type DiscrepancyFinding,
  type InteractionFinding,
  type NormalizedMedication,
  type PipFinding,
  type RenalFinding,
} from '@/lib/api/medication';
import { fetchStreamTicket } from '@/lib/api/stream-ticket';

export type MedicationAnalysisStatus = 'idle' | 'starting' | 'streaming' | 'done' | 'error';

export function useMedicationAnalysis(chatId: string) {
  const [status, setStatus] = useState<MedicationAnalysisStatus>('idle');
  const [medications, setMedications] = useState<NormalizedMedication[]>([]);
  const [previousMedications, setPreviousMedications] = useState<NormalizedMedication[]>([]);
  const [findings, setFindings] = useState<InteractionFinding[]>([]);
  const [renalFindings, setRenalFindings] = useState<RenalFinding[]>([]);
  const [pipFindings, setPipFindings] = useState<PipFinding[]>([]);
  const [discrepancyFindings, setDiscrepancyFindings] = useState<DiscrepancyFinding[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const analyze = useCallback(
    async (rawText: string, params: AnalysisParameters | null = null) => {
      setStatus('starting');
      setMedications([]);
      setPreviousMedications([]);
      setFindings([]);
      setRenalFindings([]);
      setPipFindings([]);
      setDiscrepancyFindings([]);
      setErrorMessage(null);

      let ticket: string;
      try {
        ticket = await fetchStreamTicket();
      } catch {
        setStatus('error');
        setErrorMessage('Could not start a live connection. Please try again.');
        return;
      }

      const controller = new AbortController();
      abortRef.current = controller;
      setStatus('streaming');

      await streamMedicationAnalysis(
        chatId,
        rawText,
        params,
        ticket,
        {
          onMedication: (medication) => setMedications((prev) => [...prev, medication]),
          onPreviousMedication: (medication) =>
            setPreviousMedications((prev) => [...prev, medication]),
          onInteraction: (finding) => setFindings((prev) => [...prev, finding]),
          onRenal: (finding) => setRenalFindings((prev) => [...prev, finding]),
          onPip: (finding) => setPipFindings((prev) => [...prev, finding]),
          onDiscrepancy: (finding) => setDiscrepancyFindings((prev) => [...prev, finding]),
          onDone: () => setStatus('done'),
          onError: (_code, message) => {
            setStatus('error');
            setErrorMessage(message);
          },
        },
        controller.signal,
      );
    },
    [chatId],
  );

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setStatus('idle');
    setMedications([]);
    setPreviousMedications([]);
    setFindings([]);
    setRenalFindings([]);
    setPipFindings([]);
    setDiscrepancyFindings([]);
    setErrorMessage(null);
  }, []);

  return {
    analyze,
    reset,
    status,
    medications,
    previousMedications,
    findings,
    renalFindings,
    pipFindings,
    discrepancyFindings,
    errorMessage,
  };
}
