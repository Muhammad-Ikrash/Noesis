import { ChangeDetectionStrategy, Component, computed, effect, inject, input, signal, untracked } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { DeckSummary, DocumentOut } from '../../core/api/models';
import { apiErrorMessage } from '../../core/http/api-error';
import { DocumentsService } from '../../core/services/documents.service';
import { FlashcardService } from '../../core/services/flashcard.service';
import { ToastService } from '../../core/services/toast.service';
import { relativeTime } from '../../shared/format';
import { ConfirmDialog } from '../../shared/ui/confirm-dialog';
import { Icon } from '../../shared/ui/icon';

@Component({
  selector: 'app-deck-list-page',
  imports: [FormsModule, RouterLink, Icon, ConfirmDialog],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './deck-list-page.html',
  styleUrl: './deck-list-page.scss',
})
export class DeckListPage {
  /** ?docs=id1,id2 pre-selects documents (from the library). */
  readonly docsParam = input<string>(undefined, { alias: 'docs' });

  private readonly api = inject(FlashcardService);
  private readonly docsApi = inject(DocumentsService);
  private readonly toast = inject(ToastService);
  private readonly router = inject(Router);
  protected readonly ago = relativeTime;

  protected readonly decks = signal<DeckSummary[]>([]);
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);

  protected readonly library = signal<DocumentOut[]>([]);
  protected readonly picked = signal<Set<string>>(new Set());
  protected readonly topic = signal('');
  protected readonly count = signal(12);
  protected readonly generating = signal(false);
  protected readonly genError = signal<string | null>(null);

  protected readonly toDelete = signal<DeckSummary | null>(null);
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
        this.error.set(apiErrorMessage(e, 'Could not load your flashcards.'));
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
      .create({ document_ids: [...this.picked()], topic: this.topic().trim() || undefined, card_count: this.count() })
      .subscribe({
        next: (d) => this.router.navigate(['/flashcards', d.id]),
        error: (e) => {
          this.generating.set(false);
          this.genError.set(apiErrorMessage(e, 'The flashcards could not be made.'));
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
        this.toast.ok('Deck deleted.');
      },
      error: (e) => {
        this.deleting.set(false);
        this.toast.error(apiErrorMessage(e));
      },
    });
  }

  protected pct(d: DeckSummary): number {
    return d.card_count ? Math.round((d.known_count / d.card_count) * 100) : 0;
  }
}
