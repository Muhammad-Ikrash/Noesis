import {
  ChangeDetectionStrategy, Component, computed, effect, inject, input, signal, untracked,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { Quiz } from '../../core/api/models';
import { apiErrorMessage } from '../../core/http/api-error';
import { QuizService } from '../../core/services/quiz.service';
import { ConfirmDialog } from '../../shared/ui/confirm-dialog';
import { Icon } from '../../shared/ui/icon';

const LETTERS = ['A', 'B', 'C', 'D'];

@Component({
  selector: 'app-quiz-runner-page',
  imports: [RouterLink, Icon, ConfirmDialog],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '(document:keydown)': 'onKey($event)' },
  template: `
    <div class="page">
      @if (loading()) {
        <div class="skeleton" style="height: 28px; width: 50%"></div>
        <div class="skeleton" style="height: 220px; margin-top: 24px"></div>
      } @else if (error()) {
        <div class="alert" role="alert"><div>{{ error() }}</div><button class="btn btn--sm" type="button" (click)="load()">Retry</button></div>
        <a class="btn btn--quiet" routerLink="/quizzes">Back to quizzes</a>
      } @else if (quiz(); as q) {
        <header class="head">
          <a class="btn btn--quiet btn--sm" routerLink="/quizzes"><app-icon name="left" [size]="14" />Quizzes</a>
          <p class="eyebrow">{{ q.title }}</p>
        </header>

        <nav class="dots" aria-label="Questions">
          @for (item of q.questions; track item.id; let i = $index) {
            <button type="button" [class.is-current]="i === index()" [class.is-done]="answers()[i] !== null"
                    (click)="index.set(i)" [attr.aria-label]="'Question ' + (i + 1) + (answers()[i] !== null ? ', answered' : '')"
                    [attr.aria-current]="i === index() ? 'step' : null">{{ i + 1 }}</button>
          }
        </nav>

        @if (current(); as item) {
          <section class="card" aria-live="polite">
            <p class="mono muted">Question {{ index() + 1 }} of {{ q.questions.length }} · from {{ item.filename }}</p>
            <h2>{{ item.prompt }}</h2>
            <div class="options" role="radiogroup" [attr.aria-label]="'Answers for question ' + (index() + 1)">
              @for (opt of item.options; track $index; let o = $index) {
                <button type="button" role="radio" class="opt" [attr.aria-checked]="answers()[index()] === o"
                        (click)="choose(o)">
                  <span class="opt__key">{{ letters[o] }}</span><span>{{ opt }}</span>
                </button>
              }
            </div>
          </section>
        }

        @if (submitError()) { <div class="alert" role="alert"><div>{{ submitError() }}</div></div> }

        <footer class="nav">
          <button class="btn" type="button" (click)="index.set(index() - 1)" [disabled]="index() === 0">
            <app-icon name="left" [size]="14" />Previous
          </button>
          <span class="mono muted">{{ answeredCount() }}/{{ q.questions.length }} answered</span>
          @if (index() < q.questions.length - 1) {
            <button class="btn btn--primary" type="button" (click)="index.set(index() + 1)">Next<app-icon name="right" [size]="14" /></button>
          } @else {
            <button class="btn btn--primary" type="button" (click)="trySubmit()" [disabled]="submitting()">
              @if (submitting()) { <span class="spinner"></span> } Submit answers
            </button>
          }
        </footer>
        <p class="hint mono muted">Keys: 1–4 or A–D to answer · ← → to move</p>
      }
    </div>

    <app-confirm-dialog [open]="confirmOpen()" title="Submit with unanswered questions?" confirmLabel="Submit anyway"
                        [message]="(total() - answeredCount()) + ' question(s) are unanswered and will be marked wrong.'"
                        [busy]="submitting()" (confirmed)="submit()" (cancelled)="confirmOpen.set(false)" />
  `,
  styles: `
    .page { width: min(760px, 100%); margin: 0 auto; padding: var(--space-6) var(--space-5) var(--space-8); }
    .head { display: flex; align-items: center; gap: var(--space-4); margin-bottom: var(--space-5); }
    .dots {
      display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: var(--space-5);
      button {
        width: 32px; height: 32px; border-radius: 50%; border: 1px solid var(--rule-strong); background: var(--surface);
        font-family: var(--font-mono); font-size: var(--text-xs); color: var(--ink-2); cursor: pointer;
        &.is-done { background: var(--ink); border-color: var(--ink); color: var(--paper); }
        &.is-current { box-shadow: 0 0 0 2px var(--paper), 0 0 0 4px var(--pen); }
      }
    }
    .card {
      padding: var(--space-6); border: 1px solid var(--rule); border-radius: var(--radius); background: var(--surface);
      animation: rise .2s var(--ease);
      .mono { font-size: var(--text-xs); }
      h2 { font-size: var(--text-xl); margin: var(--space-3) 0 var(--space-5); line-height: 1.25; }
    }
    .options { display: grid; gap: var(--space-2); }
    .opt {
      display: flex; gap: var(--space-4); align-items: flex-start; text-align: left;
      padding: var(--space-3) var(--space-4); border: 1px solid var(--rule-strong); border-radius: var(--radius);
      background: var(--paper); font-family: var(--font-read); font-size: var(--text-read); cursor: pointer;
      transition: border-color .12s, background .12s;
      &:hover { border-color: var(--ink-2); }
      &[aria-checked='true'] { border-color: var(--pen); background: var(--pen-soft); .opt__key { background: var(--pen); color: var(--on-pen); border-color: var(--pen); } }
    }
    .opt__key {
      flex: none; display: grid; place-items: center; width: 26px; height: 26px; margin-top: 1px;
      border: 1px solid var(--rule-strong); border-radius: 50%; font-family: var(--font-mono); font-size: var(--text-xs);
    }
    .nav { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); margin-top: var(--space-5); .mono { font-size: var(--text-xs); } }
    .hint { margin-top: var(--space-4); font-size: 11px; text-align: center; }
    .alert { margin-top: var(--space-4); }
    @media (max-width: 560px) {
      .page { padding: var(--space-4) var(--space-3) var(--space-7); }
      .card { padding: var(--space-4); h2 { font-size: var(--text-lg); } }
      .hint { display: none; }
    }
  `,
})
export class QuizRunnerPage {
  readonly quizId = input.required<string>();

  private readonly api = inject(QuizService);
  private readonly router = inject(Router);
  protected readonly letters = LETTERS;

  protected readonly quiz = signal<Quiz | null>(null);
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly index = signal(0);
  protected readonly answers = signal<(number | null)[]>([]);
  protected readonly submitting = signal(false);
  protected readonly submitError = signal<string | null>(null);
  protected readonly confirmOpen = signal(false);

  protected readonly current = computed(() => this.quiz()?.questions[this.index()] ?? null);
  protected readonly total = computed(() => this.quiz()?.questions.length ?? 0);
  protected readonly answeredCount = computed(() => this.answers().filter((a) => a !== null).length);

  constructor() {
    effect(() => {
      this.quizId();
      untracked(() => this.load());
    });
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.get(this.quizId()).subscribe({
      next: (q) => {
        this.quiz.set(q);
        this.answers.set(q.questions.map(() => null));
        this.index.set(0);
        this.loading.set(false);
      },
      error: (e) => {
        this.error.set(apiErrorMessage(e, 'This quiz could not be loaded.'));
        this.loading.set(false);
      },
    });
  }

  protected choose(option: number): void {
    const i = this.index();
    this.answers.update((a) => a.map((v, j) => (j === i ? option : v)));
  }

  protected onKey(event: KeyboardEvent): void {
    if (!this.quiz() || this.confirmOpen() || (event.target as HTMLElement).closest('input, textarea')) return;
    const key = event.key.toUpperCase();
    const n = '1234'.indexOf(key) >= 0 ? '1234'.indexOf(key) : LETTERS.indexOf(key);
    if (n >= 0 && event.key.length === 1) this.choose(n);
    else if (event.key === 'ArrowRight' && this.index() < this.total() - 1) this.index.update((i) => i + 1);
    else if (event.key === 'ArrowLeft' && this.index() > 0) this.index.update((i) => i - 1);
  }

  protected trySubmit(): void {
    if (this.answeredCount() < this.total()) this.confirmOpen.set(true);
    else this.submit();
  }

  protected submit(): void {
    const q = this.quiz();
    if (!q) return;
    this.submitting.set(true);
    this.submitError.set(null);
    this.api.submit(q.id, this.answers()).subscribe({
      next: (r) => this.router.navigate(['/quizzes', q.id, 'attempts', r.id]),
      error: (e) => {
        this.submitting.set(false);
        this.confirmOpen.set(false);
        this.submitError.set(apiErrorMessage(e, 'Your answers could not be submitted.'));
      },
    });
  }
}
