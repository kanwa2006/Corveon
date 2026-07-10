'use client';

import { useCallback, useRef, useState } from 'react';

import { streamVerification, type VerifiedClaim } from '@/lib/api/evidence';
import { fetchStreamTicket } from '@/lib/api/stream-ticket';

export type VerificationRunStatus = 'idle' | 'starting' | 'streaming' | 'done' | 'error';

export function useEvidenceVerification(chatId: string) {
  const [status, setStatus] = useState<VerificationRunStatus>('idle');
  const [claims, setClaims] = useState<VerifiedClaim[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const verify = useCallback(
    async (messageId: string) => {
      setStatus('starting');
      setClaims([]);
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

      await streamVerification(
        chatId,
        messageId,
        ticket,
        {
          onClaim: (claim) => setClaims((prev) => [...prev, claim]),
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
    setClaims([]);
    setErrorMessage(null);
  }, []);

  return { verify, reset, status, claims, errorMessage };
}
