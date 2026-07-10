'use client';

import { useCallback, useRef, useState } from 'react';

import {
  streamMedicationAnalysis,
  type InteractionFinding,
  type NormalizedMedication,
} from '@/lib/api/medication';
import { fetchStreamTicket } from '@/lib/api/stream-ticket';

export type MedicationAnalysisStatus = 'idle' | 'starting' | 'streaming' | 'done' | 'error';

export function useMedicationAnalysis(chatId: string) {
  const [status, setStatus] = useState<MedicationAnalysisStatus>('idle');
  const [medications, setMedications] = useState<NormalizedMedication[]>([]);
  const [findings, setFindings] = useState<InteractionFinding[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const analyze = useCallback(
    async (rawText: string) => {
      setStatus('starting');
      setMedications([]);
      setFindings([]);
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
        ticket,
        {
          onMedication: (medication) => setMedications((prev) => [...prev, medication]),
          onInteraction: (finding) => setFindings((prev) => [...prev, finding]),
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
    setFindings([]);
    setErrorMessage(null);
  }, []);

  return { analyze, reset, status, medications, findings, errorMessage };
}
