import { TestBed } from '@angular/core/testing';
import { ThemeService } from './theme.service';
import { ToastService } from './toast.service';

describe('ToastService', () => {
  let toast: ToastService;

  beforeEach(() => {
    vi.useFakeTimers();
    TestBed.configureTestingModule({});
    toast = TestBed.inject(ToastService);
  });
  afterEach(() => vi.useRealTimers());

  it('adds toasts of each kind with increasing ids', () => {
    toast.ok('Saved');
    toast.info('Working');
    toast.error('Failed');
    expect(toast.toasts().map((t) => [t.kind, t.text])).toEqual([
      ['ok', 'Saved'],
      ['info', 'Working'],
      ['error', 'Failed'],
    ]);
    const ids = toast.toasts().map((t) => t.id);
    expect(ids).toEqual([...ids].sort((a, b) => a - b));
  });

  it('keeps at most four toasts, dropping the oldest', () => {
    for (let i = 1; i <= 6; i++) toast.info(`t${i}`);
    expect(toast.toasts().map((t) => t.text)).toEqual(['t3', 't4', 't5', 't6']);
  });

  it('collapses repeated errors that share a key', () => {
    toast.error('Offline', 'offline');
    toast.error('Offline', 'offline');
    expect(toast.toasts()).toHaveLength(1);
  });

  it('dismisses on demand', () => {
    toast.ok('a');
    toast.dismiss(toast.toasts()[0].id);
    expect(toast.toasts()).toEqual([]);
  });

  it('expires normal toasts after 4 s and errors after 7 s', () => {
    toast.ok('ok');
    toast.error('err');
    vi.advanceTimersByTime(4000);
    expect(toast.toasts().map((t) => t.text)).toEqual(['err']);
    vi.advanceTimersByTime(3000);
    expect(toast.toasts()).toEqual([]);
  });
});

describe('ThemeService', () => {
  const root = document.documentElement;

  beforeEach(() => {
    localStorage.clear();
    root.removeAttribute('data-theme');
    TestBed.configureTestingModule({});
  });

  it('follows the system theme by default', () => {
    const theme = TestBed.inject(ThemeService);
    expect(theme.theme()).toBe('system');
    expect(root.hasAttribute('data-theme')).toBe(false);
  });

  it('restores a saved theme', () => {
    localStorage.setItem('noesis.theme', 'dark');
    const theme = TestBed.inject(ThemeService);
    expect(theme.theme()).toBe('dark');
    expect(root.getAttribute('data-theme')).toBe('dark');
  });

  it('ignores an invalid saved value', () => {
    localStorage.setItem('noesis.theme', 'purple');
    expect(TestBed.inject(ThemeService).theme()).toBe('system');
  });

  it('cycles system → light → dark → system and saves each choice', () => {
    const theme = TestBed.inject(ThemeService);
    theme.cycle();
    expect(theme.theme()).toBe('light');
    expect(root.getAttribute('data-theme')).toBe('light');
    expect(localStorage.getItem('noesis.theme')).toBe('light');

    theme.cycle();
    expect(theme.theme()).toBe('dark');
    expect(root.getAttribute('data-theme')).toBe('dark');

    theme.cycle();
    expect(theme.theme()).toBe('system');
    expect(root.hasAttribute('data-theme')).toBe(false);
    expect(localStorage.getItem('noesis.theme')).toBe('system');
  });
});
