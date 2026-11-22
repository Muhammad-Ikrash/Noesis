import { copyText, downloadBlob } from './download';

describe('downloadBlob', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('clicks a temporary link with the filename, then releases the URL', () => {
    vi.useFakeTimers();
    const create = vi.fn(() => 'blob:fake');
    const revoke = vi.fn();
    Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    downloadBlob(new Blob(['hello']), 'notes.md');

    expect(create).toHaveBeenCalledOnce();
    expect(click).toHaveBeenCalledOnce();
    const link = click.mock.contexts[0] as HTMLAnchorElement;
    expect(link.download).toBe('notes.md');
    expect(link.href).toBe('blob:fake');
    expect(document.body.contains(link)).toBe(false);

    expect(revoke).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1000);
    expect(revoke).toHaveBeenCalledWith('blob:fake');
  });
});

describe('copyText', () => {
  const original = Object.getOwnPropertyDescriptor(navigator, 'clipboard');

  afterEach(() => {
    vi.restoreAllMocks();
    if (original) Object.defineProperty(navigator, 'clipboard', original);
    else delete (navigator as { clipboard?: unknown }).clipboard;
  });

  function setClipboard(value: unknown) {
    Object.defineProperty(navigator, 'clipboard', { value, configurable: true });
  }

  it('uses the async clipboard API when available', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    setClipboard({ writeText });
    await expect(copyText('answer')).resolves.toBe(true);
    expect(writeText).toHaveBeenCalledWith('answer');
  });

  it('falls back to execCommand when the clipboard API fails', async () => {
    setClipboard({ writeText: vi.fn().mockRejectedValue(new Error('denied')) });
    const exec = vi.fn().mockReturnValue(true);
    Object.assign(document, { execCommand: exec });

    await expect(copyText('answer')).resolves.toBe(true);
    expect(exec).toHaveBeenCalledWith('copy');
    expect(document.querySelector('textarea')).toBeNull();
  });

  it('reports failure when nothing works', async () => {
    setClipboard(undefined);
    Object.assign(document, {
      execCommand: () => {
        throw new Error('unsupported');
      },
    });
    await expect(copyText('answer')).resolves.toBe(false);
  });
});
