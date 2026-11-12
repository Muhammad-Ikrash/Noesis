/**
 * Minimal, safe Markdown subset for model answers: paragraphs, lists, bold/italic/code,
 * headings, pipe tables (rendered preformatted) and citation markers like [2].
 * Produces data for templates; never builds HTML strings.
 */

export type Inline =
  | { t: 'text'; v: string }
  | { t: 'b'; v: string }
  | { t: 'i'; v: string }
  | { t: 'code'; v: string }
  | { t: 'cite'; n: number };

export type Block =
  | { t: 'p'; inl: Inline[] }
  | { t: 'h'; inl: Inline[] }
  | { t: 'ul' | 'ol'; items: Inline[][] }
  | { t: 'pre'; v: string };

const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|\[\d{1,2}\]|\*[^*\s][^*]*\*|_[^_\s][^_]*_)/g;

export function parseInline(text: string): Inline[] {
  const out: Inline[] = [];
  let last = 0;
  for (const m of text.matchAll(INLINE)) {
    if (m.index! > last) out.push({ t: 'text', v: text.slice(last, m.index) });
    const tok = m[0];
    if (tok.startsWith('**')) out.push({ t: 'b', v: tok.slice(2, -2) });
    else if (tok.startsWith('`')) out.push({ t: 'code', v: tok.slice(1, -1) });
    else if (tok.startsWith('[')) out.push({ t: 'cite', n: Number(tok.slice(1, -1)) });
    else out.push({ t: 'i', v: tok.slice(1, -1) });
    last = m.index! + tok.length;
  }
  if (last < text.length) out.push({ t: 'text', v: text.slice(last) });
  return out;
}

export function parseBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  const lines = text.replace(/\r\n/g, '\n').split('\n');
  let para: string[] = [];

  const flush = () => {
    if (para.length) blocks.push({ t: 'p', inl: parseInline(para.join(' ')) });
    para = [];
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();
    if (!trimmed) { flush(); continue; }

    if (trimmed.startsWith('|')) {
      flush();
      const rows: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith('|')) rows.push(lines[i++].trim());
      i--;
      blocks.push({ t: 'pre', v: rows.filter((r) => !/^\|[\s:|-]+\|$/.test(r)).join('\n') });
      continue;
    }
    const heading = /^#{1,6}\s+(.*)$/.exec(trimmed);
    if (heading) { flush(); blocks.push({ t: 'h', inl: parseInline(heading[1]) }); continue; }

    const ul = /^[-*•]\s+(.*)$/.exec(trimmed);
    const ol = /^\d+[.)]\s+(.*)$/.exec(trimmed);
    if (ul || ol) {
      flush();
      const kind = ul ? 'ul' : 'ol';
      const prev = blocks[blocks.length - 1];
      const item = parseInline((ul ?? ol)![1]);
      if (prev && prev.t === kind) prev.items.push(item);
      else blocks.push({ t: kind, items: [item] });
      continue;
    }
    para.push(trimmed);
  }
  flush();
  return blocks;
}
