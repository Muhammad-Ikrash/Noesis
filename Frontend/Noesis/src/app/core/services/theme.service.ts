import { Injectable, signal } from '@angular/core';

export type Theme = 'system' | 'light' | 'dark';
const KEY = 'noesis.theme';

@Injectable({ providedIn: 'root' })
export class ThemeService {
  readonly theme = signal<Theme>(this.read());

  constructor() {
    this.apply(this.theme());
  }

  cycle(): void {
    const next: Theme = { system: 'light', light: 'dark', dark: 'system' }[this.theme()] as Theme;
    this.theme.set(next);
    this.apply(next);
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* storage unavailable: theme just won't persist */
    }
  }

  private read(): Theme {
    try {
      const v = localStorage.getItem(KEY);
      return v === 'light' || v === 'dark' ? v : 'system';
    } catch {
      return 'system';
    }
  }

  private apply(theme: Theme): void {
    const root = document.documentElement;
    if (theme === 'system') root.removeAttribute('data-theme');
    else root.setAttribute('data-theme', theme);
  }
}
