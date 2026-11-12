import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { ToastService } from '../../core/services/toast.service';
import { Icon } from './icon';

@Component({
  selector: 'app-toast-host',
  imports: [Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="toasts" role="region" aria-label="Notifications" aria-live="polite">
      @for (t of toasts.toasts(); track t.id) {
        <div class="toast" [class]="'toast toast--' + t.kind" role="status">
          <app-icon [name]="t.kind === 'ok' ? 'check' : t.kind === 'error' ? 'x' : 'chat'" [size]="16" />
          <span>{{ t.text }}</span>
          <button class="btn btn--quiet btn--icon btn--sm" (click)="toasts.dismiss(t.id)" aria-label="Dismiss">
            <app-icon name="x" [size]="14" />
          </button>
        </div>
      }
    </div>
  `,
  styles: `
    .toasts {
      position: fixed; z-index: 100; right: 16px; bottom: 16px;
      display: grid; gap: 8px; width: min(380px, calc(100vw - 32px));
    }
    .toast {
      display: flex; align-items: center; gap: 10px;
      padding: 10px 8px 10px 14px; border-radius: var(--radius);
      background: var(--ink); color: var(--paper); font-size: var(--text-sm);
      box-shadow: var(--shadow); animation: rise .25s var(--ease);
      span { flex: 1; }
      .btn { --btn-fg: var(--paper); }
    }
    .toast--ok app-icon { color: color-mix(in srgb, var(--ok), white 40%); }
    .toast--error { border-left: 3px solid var(--danger); }
  `,
})
export class ToastHost {
  protected readonly toasts = inject(ToastService);
}
