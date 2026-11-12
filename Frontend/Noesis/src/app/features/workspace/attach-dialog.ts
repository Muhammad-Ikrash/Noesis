import {
  ChangeDetectionStrategy, Component, ElementRef, effect, inject, input, output, signal, viewChild,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { DocumentOut } from '../../core/api/models';
import { apiErrorMessage } from '../../core/http/api-error';
import { DocumentsService } from '../../core/services/documents.service';

@Component({
  selector: 'app-attach-dialog',
  imports: [RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <dialog #dlg class="dialog" (close)="closed.emit()">
      <header>
        <h3>PDFs in this chat</h3>
        <p class="muted small">With search set to <em>This chat's PDFs</em>, only these are used to answer.</p>
      </header>
      <div class="dialog__body">
        @if (loading()) {
          <p class="muted"><span class="spinner"></span> Loading library…</p>
        } @else if (error()) {
          <div class="alert"><div>{{ error() }}</div></div>
        } @else if (!docs().length) {
          <div class="empty"><p>No processed PDFs yet.</p><a class="btn btn--sm" routerLink="/library">Go to library</a></div>
        } @else {
          <ul class="list">
            @for (d of docs(); track d.id) {
              <li>
                <label>
                  <input type="checkbox" [checked]="picked().has(d.id)" (change)="toggle(d.id)" />
                  <span class="name">{{ d.filename }}</span>
                  <span class="mono muted">{{ d.page_count }} pp</span>
                </label>
              </li>
            }
          </ul>
        }
      </div>
      <footer>
        <button class="btn" type="button" (click)="dlg.close()">Cancel</button>
        <button class="btn btn--primary" type="button" (click)="save.emit([...picked()])" [disabled]="busy() || loading()">
          @if (busy()) { <span class="spinner"></span> } Save
        </button>
      </footer>
    </dialog>
  `,
  styles: `
    .small { font-size: var(--text-sm); margin-top: 4px; }
    .list { list-style: none; margin: 0; padding: 0; }
    label {
      display: flex; align-items: center; gap: var(--space-3); padding: var(--space-3) 0;
      border-bottom: 1px solid var(--rule); cursor: pointer;
      input { accent-color: var(--pen); width: 16px; height: 16px; }
    }
    .name { flex: 1; font-family: var(--font-read); }
    .mono { font-size: var(--text-xs); }
    p:has(.spinner) { display: flex; gap: 8px; align-items: center; }
  `,
})
export class AttachDialog {
  readonly open = input(false);
  readonly attached = input<string[]>([]);
  readonly busy = input(false);
  readonly save = output<string[]>();
  readonly closed = output<void>();

  private readonly api = inject(DocumentsService);
  private readonly dlg = viewChild.required<ElementRef<HTMLDialogElement>>('dlg');
  protected readonly docs = signal<DocumentOut[]>([]);
  protected readonly picked = signal<Set<string>>(new Set());
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);

  constructor() {
    effect(() => {
      const el = this.dlg().nativeElement;
      if (this.open() && !el.open) {
        this.picked.set(new Set(this.attached()));
        this.load();
        el.showModal();
      }
      if (!this.open() && el.open) el.close();
    });
  }

  private load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.list().subscribe({
      next: (d) => {
        this.docs.set(d.filter((x) => x.status === 'completed'));
        this.loading.set(false);
      },
      error: (e) => {
        this.error.set(apiErrorMessage(e));
        this.loading.set(false);
      },
    });
  }

  protected toggle(id: string): void {
    this.picked.update((s) => {
      const next = new Set(s);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }
}
