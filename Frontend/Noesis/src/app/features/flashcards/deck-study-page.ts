import {
  ChangeDetectionStrategy, Component, computed, effect, inject, input, signal, untracked,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { Deck, Flashcard } from '../../core/api/models';
import { apiErrorMessage } from '../../core/http/api-error';
import { FlashcardService } from '../../core/services/flashcard.service';
import { ToastService } from '../../core/services/toast.service';
import { ConfirmDialog } from '../../shared/ui/confirm-dialog';
import { Icon } from '../../shared/ui/icon';

type Filter = 'all' | 'learning';

@Component({
  selector: 'app-deck-study-page',
  imports: [RouterLink, Icon, ConfirmDialog],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '(document:keydown)': 'onKey($event)' },
  templateUrl: './deck-study-page.html',
  styleUrl: './deck-study-page.scss',
})
export class DeckStudyPage {
  readonly deckId = input.required<string>();

  private readonly api = inject(FlashcardService);
  private readonly toast = inject(ToastService);

  protected readonly deck = signal<Deck | null>(null);
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);

  protected readonly filter = signal<Filter>('all');
  protected readonly shuffled = signal(false);
  /** Card ids for the current run, fixed when it starts so marking a card doesn't reshuffle it. */
  protected readonly order = signal<string[]>([]);
  protected readonly pos = signal(0);
  protected readonly flipped = signal(false);
  /** This run's answers: card id -> known. */
  protected readonly results = signal<Map<string, boolean>>(new Map());

  protected readonly resetOpen = signal(false);
  protected readonly resetting = signal(false);

  private readonly byId = computed(() => new Map((this.deck()?.cards ?? []).map((c) => [c.id, c])));
  protected readonly total = computed(() => this.deck()?.cards.length ?? 0);
  protected readonly knownCount = computed(() => (this.deck()?.cards ?? []).filter((c) => c.known).length);
  protected readonly learningCount = computed(() => this.total() - this.knownCount());
  protected readonly knownPct = computed(() => (this.total() ? (this.knownCount() / this.total()) * 100 : 0));

  protected readonly current = computed<Flashcard | null>(() => {
    const id = this.order()[this.pos()];
    return id ? (this.byId().get(id) ?? null) : null;
  });
  protected readonly finished = computed(() => this.order().length > 0 && this.pos() >= this.order().length);
  protected readonly gotIt = computed(() => [...this.results().values()].filter(Boolean).length);
  protected readonly stillLearning = computed(() => [...this.results().values()].filter((v) => !v).length);

  constructor() {
    effect(() => {
      this.deckId();
      untracked(() => this.load());
    });
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.get(this.deckId()).subscribe({
      next: (d) => {
        this.deck.set(d);
        this.loading.set(false);
        // Coming back to a deck with progress: carry on with the cards not known yet.
        const known = d.cards.filter((c) => c.known).length;
        this.start(known > 0 && known < d.cards.length ? 'learning' : 'all');
      },
      error: (e) => {
        this.error.set(apiErrorMessage(e, 'This deck could not be loaded.'));
        this.loading.set(false);
      },
    });
  }

  /** Begin a run over all cards or only the ones still being learned. */
  protected start(filter: Filter = this.filter(), shuffle = this.shuffled()): void {
    const cards = this.deck()?.cards ?? [];
    const ids = cards.filter((c) => filter === 'all' || !c.known).map((c) => c.id);
    this.filter.set(filter);
    this.shuffled.set(shuffle);
    this.order.set(shuffle ? shuffle_(ids) : ids);
    this.pos.set(0);
    this.flipped.set(false);
    this.results.set(new Map());
  }

  protected toggleShuffle(): void {
    this.start(this.filter(), !this.shuffled());
  }

  protected flip(): void {
    if (this.current()) this.flipped.update((f) => !f);
  }

  protected move(delta: number): void {
    const next = this.pos() + delta;
    if (next < 0 || next > this.order().length) return;
    this.pos.set(next);
    this.flipped.set(false);
  }

  /** Optimistic: update the card, move on, and undo if saving fails. */
  protected mark(known: boolean): void {
    const d = this.deck();
    const card = this.current();
    if (!d || !card) return;
    const before = card.known;
    this.setKnown(card.id, known);
    this.results.update((m) => new Map(m).set(card.id, known));
    this.move(1);
    this.api.mark(d.id, card.id, known).subscribe({
      next: (saved) => this.patchCard(saved.id, { reviewed_at: saved.reviewed_at }),
      error: (e) => {
        this.setKnown(card.id, before);
        this.toast.error(apiErrorMessage(e, 'Your progress on that card could not be saved.'));
      },
    });
  }

  protected reset(): void {
    const d = this.deck();
    if (!d) return;
    this.resetting.set(true);
    this.api.reset(d.id).subscribe({
      next: (fresh) => {
        this.deck.set(fresh);
        this.resetting.set(false);
        this.resetOpen.set(false);
        this.start('all');
        this.toast.ok('Progress reset. Every card is back to “still learning”.');
      },
      error: (e) => {
        this.resetting.set(false);
        this.toast.error(apiErrorMessage(e));
      },
    });
  }

  protected onKey(event: KeyboardEvent): void {
    if (!this.deck() || this.resetOpen()) return;
    const target = event.target as HTMLElement;
    if (target.closest('input, textarea, select')) return;
    const onControl = !!target.closest('button, a');
    if ((event.key === ' ' || event.key === 'Enter') && !onControl && this.current()) {
      event.preventDefault();
      this.flip();
    } else if (event.key === '1' && this.flipped()) this.mark(false);
    else if (event.key === '2' && this.flipped()) this.mark(true);
    else if (event.key === 'ArrowRight') this.move(1);
    else if (event.key === 'ArrowLeft') this.move(-1);
  }

  private setKnown(id: string, known: boolean): void {
    this.patchCard(id, { known });
  }

  private patchCard(id: string, patch: Partial<Flashcard>): void {
    this.deck.update((d) => (d ? { ...d, cards: d.cards.map((c) => (c.id === id ? { ...c, ...patch } : c)) } : d));
  }
}

function shuffle_<T>(items: T[]): T[] {
  const out = [...items];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}
