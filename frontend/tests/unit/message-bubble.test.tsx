import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { MessageBubble } from '@/components/chats/message-bubble';
import type { MessagePublic } from '@/lib/api/messages';

function buildMessage(overrides: Partial<MessagePublic> = {}): MessagePublic {
  return {
    id: 'm1',
    chat_id: 'c1',
    role: 'assistant',
    content: 'Here is an answer.',
    routing_trace: null,
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

describe('MessageBubble', () => {
  it('renders no citation chips when routing_trace is null', () => {
    render(<MessageBubble message={buildMessage()} />);
    expect(screen.queryByText('PubMed')).not.toBeInTheDocument();
  });

  it('renders an uploaded-document citation chip from retrieved_chunks', () => {
    render(
      <MessageBubble
        message={buildMessage({
          routing_trace: {
            path: 'rag_grounded',
            provider: 'stub',
            retrieved_chunks: [
              {
                chunk_id: 'ch1',
                document_id: 'd1',
                document_filename: 'report.pdf',
                ordinal: 0,
                similarity: 0.87,
              },
            ],
            public_evidence: [],
            duration_ms: 10,
            status: 'ok',
          },
        })}
      />,
    );
    expect(screen.getByText('report.pdf')).toBeInTheDocument();
  });

  it('renders a linked public-evidence chip with the source label (ADR-0021)', () => {
    render(
      <MessageBubble
        message={buildMessage({
          routing_trace: {
            path: 'rag_public_evidence',
            provider: 'stub',
            retrieved_chunks: [],
            public_evidence: [
              {
                source: 'pubmed',
                title: 'Headache management: a review',
                url: 'https://pubmed.ncbi.nlm.nih.gov/12345678/',
                identifier: '12345678',
                snippet: 'NSAIDs are first-line therapy.',
                published_date: null,
              },
            ],
            duration_ms: 10,
            status: 'ok',
          },
        })}
      />,
    );
    const link = screen.getByRole('link', { name: /PubMed: Headache management: a review/ });
    expect(link).toHaveAttribute('href', 'https://pubmed.ncbi.nlm.nih.gov/12345678/');
    expect(link).toHaveAttribute('target', '_blank');
  });

  it('renders a non-linked public-evidence chip when the source has no url', () => {
    render(
      <MessageBubble
        message={buildMessage({
          routing_trace: {
            path: 'rag_public_evidence',
            provider: 'stub',
            retrieved_chunks: [],
            public_evidence: [
              {
                source: 'rxnorm',
                title: 'Ibuprofen',
                url: null,
                identifier: null,
                snippet: null,
                published_date: null,
              },
            ],
            duration_ms: 10,
            status: 'ok',
          },
        })}
      />,
    );
    expect(screen.getByText('RxNorm')).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('shows the degraded-mode note when the provider was unavailable', () => {
    render(
      <MessageBubble
        message={buildMessage({
          content: '',
          routing_trace: {
            path: 'pure_llm',
            provider: null,
            retrieved_chunks: [],
            public_evidence: [],
            duration_ms: 5,
            status: 'provider_unavailable',
          },
        })}
      />,
    );
    expect(screen.getByText(/No AI provider was reachable/)).toBeInTheDocument();
  });
});
