import { HttpErrorResponse } from '@angular/common/http';
import {
  ChangeDetectionStrategy, Component, DestroyRef, computed, effect, inject, input, signal, untracked,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { DocumentDetail } from '../../core/api/models';
import { apiErrorMessage } from '../../core/http/api-error';
import { ConversationsService } from '../../core/services/conversations.service';
import { DocumentsService } from '../../core/services/documents.service';
import { ToastService } from '../../core/services/toast.service';
import { downloadBlob } from '../../shared/download';
import { readJson, writeJson } from '../../shared/local-store';
import { Icon } from '../../shared/ui/icon';
import { PdfViewer, ViewerTarget } from '../../shared/ui/pdf-viewer';

const lastPageKey = (documentId: string) => `lastPage.${documentId}`;
const SAVE_DELAY_MS = 400;

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
      <button class="btn btn--sm" type="button" (click)="download()" [disabled]="!doc() || downloading()"
              [attr.aria-label]="'Download ' + (doc()?.filename ?? 'PDF')" title="Download PDF">
        @if (downloading()) { <span class="spinner"></span> } @else { <app-icon name="download" [size]="14" /> }
        <span class="hide-sm">Download</span>
      </button>
      <button class="btn btn--primary btn--sm" type="button" (click)="study()" [disabled]="!doc() || starting()">
        @if (starting()) { <span class="spinner"></span> } @else { <app-icon name="book" [size]="14" /> }
        Study this
      </button>
    </header>
    @if (error()) {
      <div class="pad"><div class="alert" role="alert"><div>{{ error() }}</div></div></div>
    } @else {
      <app-pdf-viewer [documentId]="documentId()" [target]="target()" (pageChange)="rememberPage($event)" />
    }
  `,
  styles: `
    :host { display: flex; flex-direction: column; height: calc(100vh - var(--topbar-h)); }
    .head {
      display: flex; align-items: center; gap: var(--space-2) var(--space-4); padding: var(--space-3) var(--space-4);
      border-bottom: 1px solid var(--rule);
    }
    .title { flex: 1; min-width: 0; h2 { font-size: var(--text-lg); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; } }
    .mono { font-size: var(--text-xs); }
    .warn { color: var(--warn); }
    app-pdf-viewer { flex: 1; min-height: 0; }
    .pad { padding: var(--space-5); }
    @media (max-width: 560px) { .hide-sm { display: none; } }
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
  protected readonly downloading = signal(false);

  /** Last page read in this browser, captured once per document so later saves don't move the view. */
  private readonly resumePage = signal<number | null>(null);
  private saveTimer: ReturnType<typeof setTimeout> | undefined;

  /** An explicit ?page= (citation or link) always wins; otherwise resume where the reader left off. */
  protected readonly target = computed<ViewerTarget | null>(() => {
    const p = Number(this.page());
    if (p >= 1) return { page: p, quote: this.quote() ?? null, nonce: 1 };
    const resume = this.resumePage();
    return resume && resume > 1 ? { page: resume, quote: null, nonce: 1, quiet: true } : null;
  });

  constructor() {
    effect(() => {
      const id = this.documentId();
      untracked(() => {
        this.flushSave();
        const saved = readJson<number>(lastPageKey(id));
        this.resumePage.set(Number.isInteger(saved) && saved! >= 1 ? saved : null);
        this.doc.set(null);
        this.error.set(null);
        this.api.get(id).subscribe({
          next: (d) => this.doc.set(d),
          error: (e) => this.error.set(apiErrorMessage(e, 'This document could not be found.')),
        });
      });
    });
    inject(DestroyRef).onDestroy(() => this.flushSave());
  }

  private pendingSave: { id: string; page: number } | null = null;

  protected rememberPage(page: number): void {
    this.pendingSave = { id: this.documentId(), page };
    clearTimeout(this.saveTimer);
    this.saveTimer = setTimeout(() => this.flushSave(), SAVE_DELAY_MS);
  }

  private flushSave(): void {
    clearTimeout(this.saveTimer);
    if (this.pendingSave) writeJson(lastPageKey(this.pendingSave.id), this.pendingSave.page);
    this.pendingSave = null;
  }

  protected download(): void {
    const d = this.doc();
    if (!d || this.downloading()) return;
    this.downloading.set(true);
    this.api.file(d.id).subscribe({
      next: (data) => {
        downloadBlob(new Blob([data], { type: 'application/pdf' }), d.filename);
        this.downloading.set(false);
      },
      error: (e) => {
        this.downloading.set(false);
        this.toast.error(downloadErrorMessage(e));
      },
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

/** The file endpoint is fetched as an ArrayBuffer, so a JSON error body has to be decoded by hand. */
function downloadErrorMessage(e: unknown): string {
  if (e instanceof HttpErrorResponse) {
    if (e.error instanceof ArrayBuffer) {
      try {
        const detail = JSON.parse(new TextDecoder().decode(e.error))?.detail;
        if (typeof detail === 'string') return detail;
      } catch {
        // Not JSON; use the status-based message below.
      }
    }
    if (e.status === 404 || e.status === 410) return "This PDF file is missing, so it can't be downloaded.";
  }
  return apiErrorMessage(e, 'The PDF could not be downloaded.');
}
