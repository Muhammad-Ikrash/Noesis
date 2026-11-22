import { parseBlocks, parseInline } from './rich-text';

describe('parseInline', () => {
  it('returns plain text unchanged', () => {
    expect(parseInline('just words')).toEqual([{ t: 'text', v: 'just words' }]);
  });

  it('recognises bold, italic, code and citations', () => {
    expect(parseInline('**ATP** is *energy* in `cells` [2]')).toEqual([
      { t: 'b', v: 'ATP' },
      { t: 'text', v: ' is ' },
      { t: 'i', v: 'energy' },
      { t: 'text', v: ' in ' },
      { t: 'code', v: 'cells' },
      { t: 'text', v: ' ' },
      { t: 'cite', n: 2 },
    ]);
  });

  it('supports underscore italics', () => {
    expect(parseInline('_note_')).toEqual([{ t: 'i', v: 'note' }]);
  });

  it('only treats one- or two-digit brackets as citations', () => {
    expect(parseInline('[123]')).toEqual([{ t: 'text', v: '[123]' }]);
    expect(parseInline('[12]')).toEqual([{ t: 'cite', n: 12 }]);
  });
});

describe('parseBlocks', () => {
  it('joins wrapped lines into one paragraph and splits on blank lines', () => {
    expect(parseBlocks('first line\nsecond line\n\nnext')).toEqual([
      { t: 'p', inl: [{ t: 'text', v: 'first line second line' }] },
      { t: 'p', inl: [{ t: 'text', v: 'next' }] },
    ]);
  });

  it('parses headings', () => {
    expect(parseBlocks('## Summary')).toEqual([{ t: 'h', inl: [{ t: 'text', v: 'Summary' }] }]);
  });

  it('groups consecutive list items and keeps list kinds apart', () => {
    const blocks = parseBlocks('- a\n* b\n• c\n1. one\n2) two');
    expect(blocks).toEqual([
      { t: 'ul', items: [[{ t: 'text', v: 'a' }], [{ t: 'text', v: 'b' }], [{ t: 'text', v: 'c' }]] },
      { t: 'ol', items: [[{ t: 'text', v: 'one' }], [{ t: 'text', v: 'two' }]] },
    ]);
  });

  it('renders pipe tables as preformatted text without the separator row', () => {
    const blocks = parseBlocks('Intro\n| A | B |\n|---|:-:|\n| 1 | 2 |\nAfter');
    expect(blocks).toEqual([
      { t: 'p', inl: [{ t: 'text', v: 'Intro' }] },
      { t: 'pre', v: '| A | B |\n| 1 | 2 |' },
      { t: 'p', inl: [{ t: 'text', v: 'After' }] },
    ]);
  });

  it('handles Windows line endings', () => {
    expect(parseBlocks('a\r\n\r\nb')).toHaveLength(2);
  });

  it('returns nothing for empty input', () => {
    expect(parseBlocks('')).toEqual([]);
    expect(parseBlocks('   \n\n  ')).toEqual([]);
  });
});
