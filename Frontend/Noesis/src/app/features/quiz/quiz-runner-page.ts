import {
  ChangeDetectionStrategy, Component, computed, effect, inject, input, signal, untracked,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { AttemptSummary, Quiz } from '../../core/api/models';
import { apiErrorMessage } from '../../core/http/api-error';
import { QuizService } from '../../core/services/quiz.service';
import { relativeTime } from '../../shared/format';
import { readJson, removeKey, writeJson } from '../../shared/local-store';
import { ConfirmDialog } from '../../shared/ui/confirm-dialog';
import { Icon } from '../../shared/ui/icon';

const LETTERS = ['A', 'B', 'C', 'D'];

/** Unsubmitted answers, kept per quiz in this browser. `qids` guards against a changed question set. */
interface QuizDraft {
  qids: string[];
  answers: (number | null)[];
  index: number;
}

const draftKey = (quizId: string) => `quizDraft.${quizId}`;

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

        @if (attempts().length) {
          <details class="history">
            <summary>
              <span>Past attempts</span>
              <span class="mono muted">{{ attempts().length }} · best {{ bestScore() }}/{{ q.questions.length }}</span>
            </summary>
            <ol>
              @for (a of attempts(); track a.id) {
                <li>
                  <a [routerLink]="['/quizzes', q.id, 'attempts', a.id]" [attr.aria-label]="'Review attempt from ' + when(a.created_at)">
                    <span class="history__when">{{ when(a.created_at) }}</span>
                    <span class="mono muted">{{ ago(a.created_at) }}</span>
                    <span class="history__score mono" [class.is-good]="a.total && a.score / a.total >= 0.7">{{ a.score }}/{{ a.total }}</span>
                    <app-icon name="right" [size]="14" />
                  </a>
                </li>
              }
            </ol>
          </details>
        }

        @if (resumed()) {
          <p class="resumed mono muted" role="status">
            Resumed your unfinished answers ·
            <button type="button" class="linkish" (click)="startOver()">Start over</button>
          </p>
        }

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
    .history {
      margin-bottom: var(--space-5); border: 1px solid var(--rule); border-radius: var(--radius); background: var(--surface);
      summary {
        display: flex; align-items: baseline; justify-content: space-between; gap: var(--space-3);
        padding: var(--space-3) var(--space-4); cursor: pointer; font-size: var(--text-sm); font-weight: 500;
        .mono { font-size: var(--text-xs); font-weight: 400; }
      }
      &[open] summary { border-bottom: 1px solid var(--rule); }
      ol { list-style: none; margin: 0; padding: 0; max-height: 240px; overflow: auto; }
      li + li { border-top: 1px solid var(--rule); }
      a {
        display: flex; align-items: center; gap: var(--space-3); padding: var(--space-2) var(--space-4);
        text-decoration: none; color: inherit; font-size: var(--text-sm);
        &:hover { background: color-mix(in srgb, var(--paper-sunk), transparent 40%); .history__when { color: var(--pen); } }
        .mono { font-size: var(--text-xs); }
      }
    }
    .history__when { flex: 1; min-width: 0; font-family: var(--font-read); }
    .history__score { color: var(--ink-2); &.is-good { color: var(--ok); } }
    .resumed { margin: calc(-1 * var(--space-2)) 0 var(--space-4); font-size: var(--text-xs); }
    .linkish {
      border: 0; padding: 0; background: none; font: inherit; color: var(--pen); cursor: pointer;
      text-decoration: underline; text-underline-offset: 2px;
    }
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
  protected readonly resumed = signal(false);
  private submitted = false;

  protected readonly ago = relativeTime;
  protected readonly current = computed(() => this.quiz()?.questions[this.index()] ?? null);
  protected readonly total = computed(() => this.quiz()?.questions.length ?? 0);
  protected readonly answeredCount = computed(() => this.answers().filter((a) => a !== null).length);

  /** Past attempts from the quiz detail response, newest first. */
  protected readonly attempts = computed<AttemptSummary[]>(() =>
    [...(this.quiz()?.attempts ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at)),
  );
  protected readonly bestScore = computed(() => Math.max(0, ...this.attempts().map((a) => a.score)));

  constructor() {
    effect(() => {
      this.quizId();
      untracked(() => this.load());
    });

    // Keep an unsubmitted draft so a refresh or failed submit doesn't lose answers.
    effect(() => {
      const q = this.quiz();
      const answers = this.answers();
      const index = this.index();
      if (!q || this.submitted || answers.length !== q.questions.length) return;
      if (answers.every((a) => a === null) && index === 0) removeKey(draftKey(q.id));
      else writeJson(draftKey(q.id), { qids: q.questions.map((x) => x.id), answers, index } satisfies QuizDraft);
    });
  }

  protected when(iso: string): string {
    return new Date(iso).toLocaleString(undefined, {
      day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  }

  /** A draft is only valid for the exact same questions in the same order. */
  private restoreDraft(q: Quiz): QuizDraft | null {
    const draft = readJson<QuizDraft>(draftKey(q.id));
    if (!draft) return null;
    const ids = q.questions.map((x) => x.id);
    const valid =
      Array.isArray(draft.qids) && Array.isArray(draft.answers) &&
      draft.qids.length === ids.length && draft.qids.every((id, i) => id === ids[i]) &&
      draft.answers.length === ids.length &&
      draft.answers.every((a) => a === null || (Number.isInteger(a) && a >= 0 && a < LETTERS.length));
    if (!valid) {
      removeKey(draftKey(q.id));
      return null;
    }
    return { ...draft, index: clampIndex(draft.index, ids.length) };
  }

  protected startOver(): void {
    const q = this.quiz();
    if (!q) return;
    removeKey(draftKey(q.id));
    this.answers.set(q.questions.map(() => null));
    this.index.set(0);
    this.resumed.set(false);
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.get(this.quizId()).subscribe({
      next: (q) => {
        const draft = this.restoreDraft(q);
        this.submitted = false;
        this.quiz.set(q);
        this.answers.set(draft ? draft.answers : q.questions.map(() => null));
        this.index.set(draft ? draft.index : 0);
        this.resumed.set(!!draft && draft.answers.some((a) => a !== null));
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
      next: (r) => {
        // Only a successful submit clears the draft; a failed one keeps it for retry.
        this.submitted = true;
        removeKey(draftKey(q.id));
        this.router.navigate(['/quizzes', q.id, 'attempts', r.id]);
      },
      error: (e) => {
        this.submitting.set(false);
        this.confirmOpen.set(false);
        this.submitError.set(apiErrorMessage(e, 'Your answers could not be submitted.'));
      },
    });
  }
}

function clampIndex(i: unknown, length: number): number {
  return Number.isInteger(i) ? Math.min(Math.max(i as number, 0), length - 1) : 0;
}
