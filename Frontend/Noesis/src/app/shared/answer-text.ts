import { Conversation, Message, Source } from '../core/api/models';

/**
 * Plain Markdown versions of answers, built only from data already loaded in the browser.
 * Sources use the saved filename and page, so citations from deleted PDFs survive.
 */

const SUPP_LABEL = 'Additional explanation (not from your PDF)';

function sourceLine(s: Source): string {
  return `- [${s.position}] ${s.filename}, p. ${s.page_number}${s.document_id ? '' : ' (deleted)'}`;
}

/** Answer text, its labelled supplementary explanation, then its own numbered sources. */
export function answerToMarkdown(m: Message): string {
  const parts: string[] = [];
  switch (m.answer_status) {
    case 'needs_clarification':
      parts.push(`_Noesis asked for a detail:_ ${(m.clarification_question || m.content).trim()}`);
      break;
    case 'error':
      parts.push(`_The answer could not be generated:_ ${m.content.trim()}`);
      break;
    default:
      if (m.answer_status === 'insufficient_context') parts.push('_Not covered by your PDFs._');
      if (m.content.trim()) parts.push(m.content.trim());
  }

  if (m.supplementary?.trim()) {
    const quoted = m.supplementary.trim().split(/\r?\n/).map((l) => (l ? `> ${l}` : '>')).join('\n');
    parts.push(`> **${SUPP_LABEL}**\n>\n${quoted}`);
  }

  const sources = [...m.sources].sort((a, b) => a.position - b.position);
  if (sources.length) parts.push(['Sources:', ...sources.map(sourceLine)].join('\n'));

  return parts.join('\n\n');
}

/** Whole session: title, metadata, then each question with its answer and that answer's own sources. */
export function sessionToMarkdown(conv: Conversation, messages: Message[], exportedAt = new Date()): string {
  const date = exportedAt.toLocaleString(undefined, {
    day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
  const pdfs = conv.documents.map((d) => d.filename).join(', ') || 'none attached';
  const out: string[] = [
    `# ${conv.title}`,
    `_Exported from Noesis on ${date}. PDFs: ${pdfs}._`,
  ];

  for (const m of messages) {
    if (m.role === 'user') {
      out.push('---', `## Q: ${m.content.trim().replace(/\s*\r?\n\s*/g, ' ')}`);
    } else {
      const mode = m.mode === 'extensive' ? ' · Extensive mode' : '';
      out.push(`**Answer**${mode}`, answerToMarkdown(m));
    }
  }
  return out.join('\n\n') + '\n';
}

/** File-system friendly name for an exported session. */
export function exportFilename(title: string): string {
  const slug = title
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60)
    .replace(/-+$/g, '');
  return `${slug || 'study-session'}.md`;
}
