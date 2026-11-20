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

export type StatusFilter = 'all' | 'ready' | 'processing' | 'failed';
export type DocSort = 'default' | 'name' | 'newest' | 'oldest';

const STATUS_GROUP: Record<StatusFilter, (d: DocumentOut) => boolean> = {
  all: () => true,
  ready: (d) => d.status === 'completed',
  processing: (d) => d.status === 'pending' || d.status === 'processing',
  failed: (d) => d.status === 'failed' || d.status === 'missing',
};

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

  // Search / filter / sort (applied to the loaded list only; polling keeps writing `docs`).
  protected readonly query = signal('');
  protected readonly statusFilter = signal<StatusFilter>('all');
  protected readonly sort = signal<DocSort>('default');
  protected readonly filtering = computed(() => !!this.query().trim() || this.statusFilter() !== 'all');

  protected readonly visibleDocs = computed(() => {
    const q = this.query().trim().toLowerCase();
    const match = STATUS_GROUP[this.statusFilter()];
    const list = this.docs().filter((d) => match(d) && (!q || d.filename.toLowerCase().includes(q)));
    switch (this.sort()) {
      case 'name':
        return [...list].sort((a, b) => a.filename.localeCompare(b.filename, undefined, { sensitivity: 'base', numeric: true }));
      case 'newest':
        return [...list].sort((a, b) => b.created_at.localeCompare(a.created_at));
      case 'oldest':
        return [...list].sort((a, b) => a.created_at.localeCompare(b.created_at));
      default:
        return list;
    }
  });

  protected readonly readyCount = computed(() => this.docs().filter((d) => d.status === 'completed').length);
  private readonly visibleReady = computed(() => this.visibleDocs().filter((d) => d.status === 'completed'));
  protected readonly selectedReady = computed(() =>
    this.docs().filter((d) => this.selected().has(d.id) && d.status === 'completed'),
  );
  /** Selected PDFs that the current filter hides; they are still included in Study / Quiz. */
  protected readonly hiddenSelected = computed(() => {
    const visible = new Set(this.visibleDocs().map((d) => d.id));
    return this.selectedReady().filter((d) => !visible.has(d.id)).length;
  });
  protected readonly allSelected = computed(
    () => this.visibleReady().length > 0 && this.visibleReady().every((d) => this.selected().has(d.id)),
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

  /** Selects or clears the ready PDFs currently shown; selections hidden by a filter are left alone. */
  protected toggleAll(): void {
    const ids = this.visibleReady().map((d) => d.id);
    const clear = this.allSelected();
    this.selected.update((s) => {
      const next = new Set(s);
      for (const id of ids) clear ? next.delete(id) : next.add(id);
      return next;
    });
  }

  protected clearFilters(): void {
    this.query.set('');
    this.statusFilter.set('all');
  }

  protected onQueryKey(event: KeyboardEvent): void {
    if (event.key === 'Escape') this.query.set('');
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

  protected flashcards(ids: string[]): void {
    this.router.navigate(['/flashcards'], { queryParams: { docs: ids.join(',') } });
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
