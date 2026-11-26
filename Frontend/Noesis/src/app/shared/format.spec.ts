import { STATUS_LABEL, formatBytes, relativeTime, statusClass } from './format';

describe('formatBytes', () => {
  it('shows bytes below 1 KB', () => {
    expect(formatBytes(0)).toBe('0 B');
    expect(formatBytes(1023)).toBe('1023 B');
  });

  it('shows whole kilobytes below 1 MB', () => {
    expect(formatBytes(1024)).toBe('1 KB');
    expect(formatBytes(1536)).toBe('2 KB');
    expect(formatBytes(1024 * 1024 - 1)).toBe('1024 KB');
  });

  it('shows megabytes with one decimal', () => {
    expect(formatBytes(1024 * 1024)).toBe('1.0 MB');
    expect(formatBytes(5.25 * 1024 * 1024)).toBe('5.3 MB');
  });
});

describe('relativeTime', () => {
  const now = new Date('2026-11-20T12:00:00Z');
  const ago = (seconds: number) => new Date(now.getTime() - seconds * 1000).toISOString();

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(now);
  });
  afterEach(() => vi.useRealTimers());

  it('returns an empty string for null', () => {
    expect(relativeTime(null)).toBe('');
  });

  it('says "just now" under a minute', () => {
    expect(relativeTime(ago(0))).toBe('just now');
    expect(relativeTime(ago(59))).toBe('just now');
  });

  it('uses minutes, hours and days', () => {
    expect(relativeTime(ago(60))).toBe('1 min ago');
    expect(relativeTime(ago(59 * 60))).toBe('59 min ago');
    expect(relativeTime(ago(3600))).toBe('1 h ago');
    expect(relativeTime(ago(23 * 3600))).toBe('23 h ago');
    expect(relativeTime(ago(86400))).toBe('1 d ago');
    expect(relativeTime(ago(6 * 86400))).toBe('6 d ago');
  });

  it('falls back to a date after a week', () => {
    const iso = ago(8 * 86400);
    const expected = new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
    expect(relativeTime(iso)).toBe(expected);
  });
});

describe('document status helpers', () => {
  it('has a label for every backend status', () => {
    for (const status of ['pending', 'processing', 'completed', 'failed', 'missing']) {
      expect(STATUS_LABEL[status]).toBeTruthy();
    }
  });

  it('maps statuses to pill classes', () => {
    expect(statusClass('pending')).toContain('pill--busy');
    expect(statusClass('processing')).toContain('pill--busy');
    expect(statusClass('completed')).toBe('pill--ok');
    expect(statusClass('failed')).toBe('pill--danger');
    expect(statusClass('missing')).toBe('pill--danger');
  });

  it('returns no class for an unknown status', () => {
    expect(statusClass('something-else')).toBe('');
  });
});
