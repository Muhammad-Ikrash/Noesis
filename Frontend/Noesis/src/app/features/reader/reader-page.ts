import { ChangeDetectionStrategy, Component, computed, effect, inject, input, signal, untracked } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { DocumentDetail } from '../../core/api/models';
import { apiErrorMessage } from '../../core/http/api-error';
import { ConversationsService } from '../../core/services/conversations.service';
import { DocumentsService } from '../../core/services/documents.service';
import { ToastService } from '../../core/services/toast.service';
import { Icon } from '../../shared/ui/icon';
import { PdfViewer, ViewerTarget } from '../../shared/ui/pdf-viewer';

/** Standalone reader: /read/:documentId?page=12&quote=... (used by quiz review citations). */
@Component({
  selector: 'app-reader-page',
  imports: [RouterLink, Icon, PdfViewer],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <header class="head">
      <a class="btn btn--quiet btn--sm" routerLink="/library"><app-icon name="left" [size]="14" />Library</a>
      <div class="title">
        @if (doc(); as d) {
          <h2>{{ d.filename }}</h2>
          <span class="mono muted">{{ d.page_count }} pages
            @if (d.ocr_pages.length) { · <span class="warn">{{ d.ocr_pages.length }} image-only page{{ d.ocr_pages.length > 1 ? 's' : '' }} not searchable</span> }
          </span>
        } @else if (error()) {
          <h2>Document unavailable</h2>
        } @else {
          <div class="skeleton" style="height: 22px; width: 240px"></div>
        }
      </div>
      <button class="btn btn--primary btn--sm" type="button" (click)="study()" [disabled]="!doc() || starting()">
        @if (starting()) { <span class="spinner"></span> } @else { <app-icon name="book" [size]="14" /> }
        Study this
      </button>
    </header>
    @if (error()) {
      <div class="pad"><div class="alert" role="alert"><div>{{ error() }}</div></div></div>
    } @else {
      <app-pdf-viewer [documentId]="documentId()" [target]="target()" />
    }
  `,
  styles: `
    :host { display: flex; flex-direction: column; height: calc(100vh - var(--topbar-h)); }
    .head {
      display: flex; align-items: center; gap: var(--space-4); padding: var(--space-3) var(--space-4);
      border-bottom: 1px solid var(--rule);
    }
    .title { flex: 1; min-width: 0; h2 { font-size: var(--text-lg); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; } }
    .mono { font-size: var(--text-xs); }
    .warn { color: var(--warn); }
    app-pdf-viewer { flex: 1; min-height: 0; }
    .pad { padding: var(--space-5); }
  `,
})
export class ReaderPage {
  readonly documentId = input.required<string>();
  readonly page = input<string>();
  readonly quote = input<string>();

  private readonly api = inject(DocumentsService);
  private readonly convApi = inject(ConversationsService);
  private readonly router = inject(Router);
  private readonly toast = inject(ToastService);

  protected readonly doc = signal<DocumentDetail | null>(null);
  protected readonly error = signal<string | null>(null);
  protected readonly starting = signal(false);
  protected readonly target = computed<ViewerTarget | null>(() => {
    const p = Number(this.page());
    return p >= 1 ? { page: p, quote: this.quote() ?? null, nonce: 1 } : null;
  });

  constructor() {
    effect(() => {
      const id = this.documentId();
      untracked(() => {
        this.doc.set(null);
        this.error.set(null);
        this.api.get(id).subscribe({
          next: (d) => this.doc.set(d),
          error: (e) => this.error.set(apiErrorMessage(e, 'This document could not be found.')),
        });
      });
    });
  }

  protected study(): void {
    this.starting.set(true);
    this.convApi.create({ document_ids: [this.documentId()] }).subscribe({
      next: (c) => this.router.navigate(['/study', c.id]),
      error: (e) => {
        this.starting.set(false);
        this.toast.error(apiErrorMessage(e));
      },
    });
  }
}
