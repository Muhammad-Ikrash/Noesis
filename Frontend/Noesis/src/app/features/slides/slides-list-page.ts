import { ChangeDetectionStrategy, Component, computed, effect, inject, input, signal, untracked } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { DocumentOut, SlideDeckSummary } from '../../core/api/models';
import { apiErrorMessage } from '../../core/http/api-error';
import { DocumentsService } from '../../core/services/documents.service';
import { SlidesService } from '../../core/services/slides.service';
import { ToastService } from '../../core/services/toast.service';
import { relativeTime } from '../../shared/format';
import { ConfirmDialog } from '../../shared/ui/confirm-dialog';
import { Icon } from '../../shared/ui/icon';
import { downloadDeck } from './slides-download';

@Component({
  selector: 'app-slides-list-page',
  imports: [FormsModule, RouterLink, Icon, ConfirmDialog],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './slides-list-page.html',
  styleUrl: './slides-list-page.scss',
})
export class SlidesListPage {
  /** ?docs=id1,id2 pre-selects documents (from the library). */
  readonly docsParam = input<string>(undefined, { alias: 'docs' });

  private readonly api = inject(SlidesService);
  private readonly docsApi = inject(DocumentsService);
  private readonly toast = inject(ToastService);
  private readonly router = inject(Router);
  protected readonly ago = relativeTime;

  protected readonly decks = signal<SlideDeckSummary[]>([]);
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);

  protected readonly library = signal<DocumentOut[]>([]);
  protected readonly picked = signal<Set<string>>(new Set());
  protected readonly topic = signal('');
  protected readonly count = signal(8);
  protected readonly generating = signal(false);
  protected readonly genError = signal<string | null>(null);

  protected readonly downloading = signal<string | null>(null);
  protected readonly toDelete = signal<SlideDeckSummary | null>(null);
  protected readonly deleting = signal(false);

  protected readonly canGenerate = computed(() => this.picked().size > 0 && !this.generating());

  constructor() {
    this.load();
    effect(() => {
      const param = this.docsParam();
      untracked(() => {
        this.docsApi.list().subscribe({
          next: (d) => {
            const ready = d.filter((x) => x.status === 'completed');
            this.library.set(ready);
            const wanted = new Set((param ?? '').split(',').filter(Boolean));
            this.picked.set(new Set(ready.filter((x) => wanted.has(x.id)).map((x) => x.id)));
          },
          error: () => {},
        });
      });
    });
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.list().subscribe({
      next: (d) => {
        this.decks.set(d);
        this.loading.set(false);
      },
      error: (e) => {
        this.error.set(apiErrorMessage(e, 'Could not load your slide decks.'));
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

  protected generate(): void {
    if (!this.canGenerate()) return;
    this.generating.set(true);
    this.genError.set(null);
    this.api
      .create({ document_ids: [...this.picked()], topic: this.topic().trim() || undefined, slide_count: this.count() })
      .subscribe({
        next: (d) => this.router.navigate(['/slides', d.id]),
        error: (e) => {
          this.generating.set(false);
          this.genError.set(apiErrorMessage(e, 'The slides could not be made.'));
        },
      });
  }

  protected download(d: SlideDeckSummary): void {
    if (this.downloading()) return;
    this.downloading.set(d.id);
    downloadDeck(this.api, d.id, d.title).subscribe({
      next: () => this.downloading.set(null),
      error: (e) => {
        this.downloading.set(null);
        this.toast.error(apiErrorMessage(e, 'The PowerPoint file could not be made.'));
      },
    });
  }

  protected confirmDelete(): void {
    const d = this.toDelete();
    if (!d) return;
    this.deleting.set(true);
    this.api.delete(d.id).subscribe({
      next: () => {
        this.decks.update((l) => l.filter((x) => x.id !== d.id));
        this.deleting.set(false);
        this.toDelete.set(null);
        this.toast.ok('Slide deck deleted.');
      },
      error: (e) => {
        this.deleting.set(false);
        this.toast.error(apiErrorMessage(e));
      },
    });
  }
}
