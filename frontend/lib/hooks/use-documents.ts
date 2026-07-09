'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';

import type { ApiError } from '@/lib/api/auth';
import {
  deleteDocument,
  listDocuments,
  subscribeToJobEvents,
  uploadDocument,
  type DocumentPublic,
  type JobStatus,
} from '@/lib/api/documents';
import { fetchStreamTicket } from '@/lib/api/stream-ticket';

const documentsKey = (chatId: string) => ['documents', chatId] as const;

export function useDocuments(chatId: string) {
  return useQuery<DocumentPublic[], ApiError>({
    queryKey: documentsKey(chatId),
    queryFn: () => listDocuments(chatId),
  });
}

export function useDeleteDocument(chatId: string) {
  const queryClient = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: (documentId) => deleteDocument(documentId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: documentsKey(chatId) });
    },
  });
}

export interface UploadProgress {
  fileName: string;
  stage: string | null;
  status: JobStatus | 'uploading';
  error: string | null;
}

export function useUploadDocument(chatId: string) {
  const queryClient = useQueryClient();
  const [uploads, setUploads] = useState<Record<string, UploadProgress>>({});
  const unsubscribeRefs = useRef<Record<string, () => void>>({});

  useEffect(() => {
    const subs = unsubscribeRefs.current;
    return () => {
      Object.values(subs).forEach((unsubscribe) => unsubscribe());
    };
  }, []);

  const upload = useCallback(
    async (file: File) => {
      const uploadKey = `${file.name}-${Date.now()}`;
      setUploads((prev) => ({
        ...prev,
        [uploadKey]: { fileName: file.name, stage: null, status: 'uploading', error: null },
      }));

      // Every branch below constructs a complete UploadProgress explicitly
      // (never spreads prev[uploadKey]) — noUncheckedIndexedAccess types
      // that lookup as possibly-undefined, and file.name is already in scope.
      let jobId: string;
      try {
        const result = await uploadDocument(chatId, file);
        jobId = result.job_id;
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Upload failed.';
        setUploads((prev) => ({
          ...prev,
          [uploadKey]: { fileName: file.name, stage: null, status: 'failed', error: message },
        }));
        return;
      }

      await queryClient.invalidateQueries({ queryKey: documentsKey(chatId) });

      let ticket: string;
      try {
        ticket = await fetchStreamTicket();
      } catch {
        setUploads((prev) => ({
          ...prev,
          [uploadKey]: {
            fileName: file.name,
            stage: null,
            status: 'failed',
            error: 'Lost connection to the server.',
          },
        }));
        return;
      }

      const unsubscribe = subscribeToJobEvents(jobId, ticket, {
        onStage: (job) => {
          setUploads((prev) => ({
            ...prev,
            [uploadKey]: {
              fileName: file.name,
              stage: job.progress_stage,
              status: job.status,
              error: job.error,
            },
          }));
          if (job.status === 'succeeded' || job.status === 'failed') {
            void queryClient.invalidateQueries({ queryKey: documentsKey(chatId) });
          }
        },
        onNotFound: () => {
          setUploads((prev) => ({
            ...prev,
            [uploadKey]: {
              fileName: file.name,
              stage: null,
              status: 'failed',
              error: 'Job not found.',
            },
          }));
        },
        onConnectionError: () => {
          setUploads((prev) => ({
            ...prev,
            [uploadKey]: {
              fileName: file.name,
              stage: null,
              status: 'failed',
              error: 'Lost connection to the server.',
            },
          }));
        },
      });
      unsubscribeRefs.current[uploadKey] = unsubscribe;
    },
    [chatId, queryClient],
  );

  const dismissUpload = useCallback((uploadKey: string) => {
    unsubscribeRefs.current[uploadKey]?.();
    delete unsubscribeRefs.current[uploadKey];
    setUploads((prev) => {
      const next = { ...prev };
      delete next[uploadKey];
      return next;
    });
  }, []);

  return { upload, uploads, dismissUpload };
}
