import { Conversation, DocumentOut, Message, Source } from '../core/api/models';
import { answerToMarkdown, exportFilename, sessionToMarkdown } from './answer-text';

function source(overrides: Partial<Source> = {}): Source {
  return {
    position: 1,
    document_id: 'doc-1',
    chunk_id: 'chunk-1',
    filename: 'biology.pdf',
    page_number: 3,
    quote: null,
    score: 0.8,
    ...overrides,
  };
}

function message(overrides: Partial<Message> = {}): Message {
  return {
    id: 'm1',
    role: 'assistant',
    content: 'Mitochondria make ATP [1].',
    supplementary: null,
    mode: 'basic',
    retrieval_scope: 'session',
    answer_status: 'answered',
    needs_clarification: false,
    clarification_question: null,
    created_at: '2026-11-20T10:00:00Z',
    sources: [],
    ...overrides,
  };
}

describe('answerToMarkdown', () => {
  it('returns the answer text alone when there are no sources', () => {
    expect(answerToMarkdown(message())).toBe('Mitochondria make ATP [1].');
  });

  it('lists sources sorted by position and marks deleted PDFs', () => {
    const md = answerToMarkdown(
      message({
        sources: [
          source({ position: 2, filename: 'notes.pdf', page_number: 9, document_id: null }),
          source({ position: 1 }),
        ],
      }),
    );
    expect(md).toBe(
      ['Mitochondria make ATP [1].', 'Sources:\n- [1] biology.pdf, p. 3\n- [2] notes.pdf, p. 9 (deleted)'].join('\n\n'),
    );
  });

  it('quotes the supplementary explanation under its label', () => {
    const md = answerToMarkdown(message({ mode: 'extensive', supplementary: 'Line one\n\nLine two' }));
    expect(md).toContain('> **Additional explanation (not from your PDF)**');
    expect(md).toContain('> Line one\n>\n> Line two');
  });

  it('flags answers not covered by the PDFs', () => {
    const md = answerToMarkdown(message({ answer_status: 'insufficient_context', content: 'Try another PDF.' }));
    expect(md.startsWith('_Not covered by your PDFs._\n\nTry another PDF.')).toBe(true);
  });

  it('prefers the clarification question when one was asked', () => {
    const md = answerToMarkdown(
      message({ answer_status: 'needs_clarification', clarification_question: 'Which chapter?', content: 'x' }),
    );
    expect(md).toBe('_Noesis asked for a detail:_ Which chapter?');
  });

  it('describes errors', () => {
    expect(answerToMarkdown(message({ answer_status: 'error', content: 'Timeout.' }))).toBe(
      '_The answer could not be generated:_ Timeout.',
    );
  });
});

describe('sessionToMarkdown', () => {
  const doc = { filename: 'biology.pdf' } as DocumentOut;
  const conv = { title: 'Cell energy', documents: [doc] } as Conversation;

  it('writes a title, the PDFs and each question with its answer', () => {
    const md = sessionToMarkdown(
      conv,
      [
        message({ id: 'q', role: 'user', content: 'What makes\n  ATP?' }),
        message({ id: 'a', mode: 'extensive', sources: [source()] }),
      ],
      new Date('2026-11-20T10:00:00Z'),
    );
    expect(md.startsWith('# Cell energy\n\n_Exported from Noesis on ')).toBe(true);
    expect(md).toContain('PDFs: biology.pdf._');
    expect(md).toContain('---\n\n## Q: What makes ATP?');
    expect(md).toContain('**Answer** · Extensive mode\n\nMitochondria make ATP [1].');
    expect(md).toContain('- [1] biology.pdf, p. 3');
    expect(md.endsWith('\n')).toBe(true);
  });

  it('says when no PDFs are attached', () => {
    const md = sessionToMarkdown({ ...conv, documents: [] }, []);
    expect(md).toContain('PDFs: none attached._');
  });
});

describe('exportFilename', () => {
  it('slugifies the title', () => {
    expect(exportFilename('Cell Energy: Chapter 3!')).toBe('cell-energy-chapter-3.md');
  });

  it('strips accents', () => {
    expect(exportFilename('Café résumé')).toBe('cafe-resume.md');
  });

  it('caps the length without a trailing dash', () => {
    const name = exportFilename('a'.repeat(59) + ' bcd');
    expect(name).toBe('a'.repeat(59) + '.md');
  });

  it('falls back when nothing usable is left', () => {
    expect(exportFilename('!!!')).toBe('study-session.md');
    expect(exportFilename('')).toBe('study-session.md');
  });
});
