import { Injectable, signal } from '@angular/core';

export interface Toast {
  id: number;
  kind: 'ok' | 'error' | 'info';
  text: string;
  key?: string;
}

@Injectable({ providedIn: 'root' })
export class ToastService {
  private nextId = 1;
  readonly toasts = signal<Toast[]>([]);

  ok(text: string): void {
    this.push('ok', text);
  }

  info(text: string): void {
    this.push('info', text);
  }

  /** `key` collapses repeats of the same error (e.g. many failed requests while offline). */
  error(text: string, key?: string): void {
    this.push('error', text, key, 7000);
  }

  dismiss(id: number): void {
    this.toasts.update((list) => list.filter((t) => t.id !== id));
  }

  private push(kind: Toast['kind'], text: string, key?: string, ttl = 4000): void {
    if (key && this.toasts().some((t) => t.key === key)) return;
    const id = this.nextId++;
    this.toasts.update((list) => [...list.slice(-3), { id, kind, text, key }]);
    setTimeout(() => this.dismiss(id), ttl);
  }
}
