import {
  ChangeDetectionStrategy, Component, DestroyRef, computed, effect, inject, signal,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { Conversation, DocumentOut } from '../../core/api/models';
import { apiErrorMessage } from '../../core/http/api-error';
import { ConversationsService } from '../../core/services/conversations.service';
import { DocumentsService } from '../../core/services/documents.service';
import { ToastService } from '../../core/services/toast.service';
import { STATUS_LABEL, formatBytes, relativeTime, statusClass } from '../../shared/format';
import { ConfirmDialog } from '../../shared/ui/confirm-dialog';
import { Icon } from '../../shared/ui/icon';
import { UploadDropzone } from './upload-dropzone';

const POLL_MS = 2500;

@Component({
  selector: 'app-library-page',
  imports: [RouterLink, Icon, UploadDropzone, ConfirmDialog],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './library-page.html',
  styleUrl: './library-page.scss',
})
export class LibraryPage {
  private readonly docsApi = inject(DocumentsService);
  private readonly convApi = inject(ConversationsService);
  private readonly toast = inject(ToastService);
  private readonly router = inject(Router);

  protected readonly docs = signal<DocumentOut[]>([]);
  protected readonly conversations = signal<Conversation[]>([]);
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly selected = signal<Set<string>>(new Set());
  protected readonly starting = signal(false);
  protected readonly toDelete = signal<DocumentOut | null>(null);
  protected readonly deleting = signal(false);

  protected readonly label = STATUS_LABEL;
  protected readonly pillClass = statusClass;

  /** Embedding progress 0-100, or null while the PDF is still being read. */
  protected percent(doc: DocumentOut): number | null {
    if (!doc.progress_total) return null;
    return Math.round((100 * (doc.progress_done ?? 0)) / doc.progress_total);
  }

  protected progressLabel(doc: DocumentOut): string {
    const pct = this.percent(doc);
    return pct === null ? '· reading' : `· ${pct}%`;
  }
  protected readonly size = formatBytes;
  protected readonly ago = relativeTime;

  protected readonly readyCount = computed(() => this.docs().filter((d) => d.status === 'completed').length);
  protected readonly selectedReady = computed(() =>
    this.docs().filter((d) => this.selected().has(d.id) && d.status === 'completed'),
  );
  protected readonly allSelected = computed(
    () => this.readyCount() > 0 && this.selectedReady().length === this.readyCount(),
  );
  private readonly busy = computed(() => this.docs().some((d) => d.status === 'pending' || d.status === 'processing'));

  constructor() {
    this.load();
    this.convApi.list().subscribe({ next: (c) => this.conversations.set(c.slice(0, 4)), error: () => {} });

    // Poll while anything is still being processed.
    let timer: ReturnType<typeof setInterval> | undefined;
    effect(() => {
      clearInterval(timer);
      if (this.busy()) timer = setInterval(() => this.refresh(), POLL_MS);
    });
    inject(DestroyRef).onDestroy(() => clearInterval(timer));
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.docsApi.list().subscribe({
      next: (d) => {
        this.docs.set(d);
        this.loading.set(false);
      },
      error: (e) => {
        this.error.set(apiErrorMessage(e, 'Could not load your library.'));
        this.loading.set(false);
      },
    });
  }

  private refresh(): void {
    const before = new Map(this.docs().map((d) => [d.id, d.status]));
    this.docsApi.list().subscribe({
      next: (list) => {
        this.docs.set(list);
        for (const d of list) {
          const was = before.get(d.id);
          if (was && was !== d.status && d.status === 'completed') this.toast.ok(`“${d.filename}” is ready to study.`);
          if (was && was !== d.status && d.status === 'failed') this.toast.error(`“${d.filename}” could not be processed.`);
        }
      },
      error: () => {},
    });
  }

  protected onUploaded(doc: DocumentOut): void {
    this.docs.update((list) => [doc, ...list.filter((d) => d.id !== doc.id)]);
  }

  protected readonly selectedIds = () => this.selectedReady().map((d) => d.id);
  protected clearSelection(): void {
    this.selected.set(new Set());
  }

  protected toggle(id: string): void {
    this.selected.update((s) => {
      const next = new Set(s);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  protected toggleAll(): void {
    this.selected.set(
      this.allSelected() ? new Set() : new Set(this.docs().filter((d) => d.status === 'completed').map((d) => d.id)),
    );
  }

  protected study(ids: string[]): void {
    this.starting.set(true);
    this.convApi.create({ document_ids: ids }).subscribe({
      next: (c) => this.router.navigate(['/study', c.id]),
      error: (e) => {
        this.starting.set(false);
        this.toast.error(apiErrorMessage(e, 'Could not start a study session.'));
      },
    });
  }

  protected quiz(ids: string[]): void {
    this.router.navigate(['/quizzes'], { queryParams: { docs: ids.join(',') } });
  }

  protected confirmDelete(): void {
    const doc = this.toDelete();
    if (!doc) return;
    this.deleting.set(true);
    this.docsApi.delete(doc.id).subscribe({
      next: () => {
        this.docs.update((l) => l.filter((d) => d.id !== doc.id));
        this.selected.update((s) => {
          const next = new Set(s);
          next.delete(doc.id);
          return next;
        });
        this.toast.ok(`Deleted “${doc.filename}”. Past answers keep their citations.`);
        this.deleting.set(false);
        this.toDelete.set(null);
      },
      error: (e) => {
        this.deleting.set(false);
        this.toast.error(apiErrorMessage(e, 'Could not delete the document.'));
      },
    });
  }
}
