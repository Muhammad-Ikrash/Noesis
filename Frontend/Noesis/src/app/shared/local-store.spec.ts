import { readJson, removeKey, writeJson } from './local-store';

describe('local-store', () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it('round-trips JSON under the noesis. prefix', () => {
    writeJson('quiz.draft.1', { answers: [0, null, 2] });
    expect(localStorage.getItem('noesis.quiz.draft.1')).toBe('{"answers":[0,null,2]}');
    expect(readJson<{ answers: (number | null)[] }>('quiz.draft.1')).toEqual({ answers: [0, null, 2] });
  });

  it('returns null for a missing key', () => {
    expect(readJson('nothing-here')).toBeNull();
  });

  it('returns null instead of throwing on corrupt JSON', () => {
    localStorage.setItem('noesis.broken', '{not json');
    expect(readJson('broken')).toBeNull();
  });

  it('removes a key', () => {
    writeJson('reader.page', 4);
    removeKey('reader.page');
    expect(readJson('reader.page')).toBeNull();
  });

  it('never throws when storage is unavailable', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota exceeded');
    });
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new Error('blocked');
    });

    expect(() => writeJson('a', 1)).not.toThrow();
    expect(readJson('a')).toBeNull();
    expect(() => removeKey('a')).not.toThrow();
  });
});
