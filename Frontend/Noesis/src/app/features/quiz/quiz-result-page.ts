import { ChangeDetectionStrategy, Component, computed, effect, inject, input, signal, untracked } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { AttemptResult, QuizAnswer, QuizQuestionReview } from '../../core/api/models';
import { apiErrorMessage } from '../../core/http/api-error';
import { QuizService } from '../../core/services/quiz.service';
import { Icon } from '../../shared/ui/icon';

/** Options the student picked, as a list (empty when skipped). */
export function chosenOptions(answer: QuizAnswer): number[] {
  if (answer === null || answer === undefined) return [];
  return Array.isArray(answer) ? answer : [answer];
}

/** Correct options; falls back to correct_index for quizzes made before multiple choice existed. */
export function correctOptions(q: QuizQuestionReview): number[] {
  return q.correct_indices?.length ? q.correct_indices : [q.correct_index];
}

/** Same rule as the backend: every correct option and nothing else. */
export function isRight(q: QuizQuestionReview, answer: QuizAnswer): boolean {
  const chosen = new Set(chosenOptions(answer));
  const correct = correctOptions(q);
  return chosen.size > 0 && chosen.size === correct.length && correct.every((o) => chosen.has(o));
}

/** Label above each reviewed question. */
export function resultMark(q: QuizQuestionReview, answer: QuizAnswer): string {
  const chosen = chosenOptions(answer);
  if (!chosen.length) return 'Skipped';
  if (isRight(q, answer)) return 'Correct';
  if (q.kind === 'multiple') {
    const found = correctOptions(q).filter((o) => chosen.includes(o)).length;
    if (found) return `Incorrect · found ${found} of ${correctOptions(q).length}`;
  }
  return 'Incorrect';
}

/** Questions answered wrongly or skipped in this attempt, in quiz order. */
export function missedQuestions(r: AttemptResult): QuizQuestionReview[] {
  return r.questions.filter((q, i) => !isRight(q, r.answers[i] ?? null));
}

const KIND_LABEL: Record<QuizQuestionReview['kind'], string> = {
  single: 'Single choice',
  multiple: 'Multiple choice',
  true_false: 'True / false',
};

@Component({
  selector: 'app-quiz-result-page',
  imports: [RouterLink, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="page">
      @if (loading()) {
        <div class="skeleton" style="height: 120px"></div>
      } @else if (error()) {
        <div class="alert" role="alert"><div>{{ error() }}</div></div>
        <a class="btn btn--quiet" routerLink="/quizzes">Back to quizzes</a>
      } @else if (result(); as r) {
        <header class="score">
          <a class="btn btn--quiet btn--sm" routerLink="/quizzes"><app-icon name="left" [size]="14" />Quizzes</a>
          <p class="eyebrow">Result</p>
          <p class="big"><span [class.is-good]="pct() >= 70">{{ r.score }}</span><span class="of">/{{ r.total }}</span></p>
          <p class="verdict">{{ verdict() }}</p>
          <div class="actions">
            @if (missedCount()) {
              <button class="btn btn--primary" type="button" (click)="retryMissed()" [disabled]="retrying()">
                @if (retrying()) { <span class="spinner"></span> } @else { <app-icon name="refresh" [size]="14" /> }
                Retry {{ missedCount() }} missed
              </button>
              <a class="btn" [routerLink]="['/quizzes', r.quiz_id]">Retake all</a>
            } @else {
              <a class="btn btn--primary" [routerLink]="['/quizzes', r.quiz_id]"><app-icon name="refresh" [size]="14" />Retake</a>
            }
            <a class="btn" routerLink="/quizzes">New quiz</a>
          </div>
          @if (retryError()) { <div class="alert" role="alert"><div>{{ retryError() }}</div></div> }
        </header>

        <ol class="review">
          @for (q of r.questions; track q.id; let i = $index) {
            @let given = r.answers[i];
            @let right = isRight(q, given);
            @let chosen = chosenOptions(given);
            @let correct = correctOptions(q);
            <li [class.is-right]="right" [class.is-wrong]="!right">
              <p class="mark mono">{{ resultMark(q, given) }} <span class="kind">· {{ kindLabel[q.kind] ?? kindLabel.single }}</span></p>
              <h3>{{ i + 1 }}. {{ q.prompt }}</h3>
              <ul class="opts">
                @for (opt of q.options; track $index; let o = $index) {
                  @let isCorrect = correct.includes(o);
                  @let isChosen = chosen.includes(o);
                  <li [class.correct]="isCorrect" [class.chosen]="isChosen && !isCorrect"
                      [class.missed]="isCorrect && !isChosen && q.kind === 'multiple'">
                    <span class="key mono">{{ 'ABCD'[o] }}</span>{{ opt }}
                    @if (isCorrect) { <app-icon name="check" [size]="14" /> }
                    @if (isChosen) { <span class="mono you">your answer</span> }
                    @else if (isCorrect && q.kind === 'multiple') { <span class="mono you">missed</span> }
                  </li>
                }
              </ul>
              @if (q.explanation) { <p class="why">{{ q.explanation }}</p> }
              @if (q.document_id) {
                <a class="cite" [routerLink]="['/read', q.document_id]" [queryParams]="{ page: q.page_number }">
                  {{ q.filename }} · p.{{ q.page_number }}
                </a>
              } @else {
                <span class="cite cite--gone">{{ q.filename }} · p.{{ q.page_number }} · deleted</span>
              }
            </li>
          }
        </ol>
      }
    </div>
  `,
  styles: `
    .page { width: min(760px, 100%); margin: 0 auto; padding: var(--space-6) var(--space-5) var(--space-8); }
    .score { display: grid; justify-items: start; gap: var(--space-2); padding-bottom: var(--space-6); border-bottom: 2px solid var(--ink); }
    .big { font-family: var(--font-read); font-size: 5rem; line-height: 1; letter-spacing: -0.03em; .is-good { color: var(--ok); } }
    .of { color: var(--ink-3); font-size: 2.5rem; }
    .verdict { font-family: var(--font-read); font-size: var(--text-lg); color: var(--ink-2); }
    .actions { display: flex; flex-wrap: wrap; gap: var(--space-2); margin-top: var(--space-3); }
    .score .alert { margin-top: var(--space-3); }
    .review { list-style: none; margin: 0; padding: 0; }
    .review > li { padding: var(--space-5) 0 var(--space-5) var(--space-4); border-bottom: 1px solid var(--rule); border-left: 3px solid transparent; }
    .review > li.is-right { border-left-color: var(--ok); }
    .review > li.is-wrong { border-left-color: var(--danger); }
    .mark { font-size: var(--text-xs); text-transform: uppercase; letter-spacing: .08em; }
    .mark .kind { color: var(--ink-3); }
    .is-right .mark { color: var(--ok); }
    .is-wrong .mark { color: var(--danger); }
    h3 { margin: var(--space-2) 0 var(--space-3); font-size: var(--text-lg); }
    .opts {
      list-style: none; margin: 0 0 var(--space-3); padding: 0; display: grid; gap: 4px;
      li { display: flex; gap: var(--space-3); align-items: center; padding: 6px var(--space-3); border-radius: var(--radius-sm); font-family: var(--font-read); }
      .correct { background: var(--ok-soft); color: var(--ok); }
      .chosen { background: var(--danger-soft); color: var(--danger); text-decoration: line-through; text-decoration-thickness: 1px; }
      .missed { outline: 1px dashed var(--ok); outline-offset: -1px; }
      .key { font-size: var(--text-xs); opacity: .7; }
      .you { font-size: 11px; margin-left: auto; text-decoration: none; }
    }
    .why { font-family: var(--font-read); color: var(--ink-2); margin-bottom: var(--space-3); }
    @media (max-width: 560px) { .page { padding: var(--space-4) var(--space-3) var(--space-7); } .big { font-size: 3.5rem; } }
  `,
})
export class QuizResultPage {
  readonly quizId = input.required<string>();
  readonly attemptId = input.required<string>();

  private readonly api = inject(QuizService);
  private readonly router = inject(Router);
  protected readonly isRight = isRight;
  protected readonly chosenOptions = chosenOptions;
  protected readonly correctOptions = correctOptions;
  protected readonly resultMark = resultMark;
  protected readonly kindLabel = KIND_LABEL;
  protected readonly result = signal<AttemptResult | null>(null);
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);

  protected readonly retrying = signal(false);
  protected readonly retryError = signal<string | null>(null);
  /** Wrong or skipped questions, the ones a retry would contain. */
  protected readonly missedCount = computed(() => {
    const r = this.result();
    return r ? missedQuestions(r).length : 0;
  });

  protected retryMissed(): void {
    const r = this.result();
    if (!r || this.retrying()) return;
    this.retrying.set(true);
    this.retryError.set(null);
    this.api.retryMissed(r.quiz_id, r.id).subscribe({
      next: (quiz) => this.router.navigate(['/quizzes', quiz.id]),
      error: (e) => {
        this.retrying.set(false);
        this.retryError.set(apiErrorMessage(e, 'The retry quiz could not be created.'));
      },
    });
  }

  protected readonly pct = computed(() => {
    const r = this.result();
    return r ? Math.round((r.score / r.total) * 100) : 0;
  });
  protected readonly verdict = computed(() => {
    const p = this.pct();
    if (p === 100) return 'Perfect. You know this material.';
    if (p >= 70) return 'Solid. Review the misses below and you are there.';
    if (p >= 40) return 'Getting there. Each miss links to the page that explains it.';
    return 'Worth another read. Open the cited pages, then retake.';
  });

  constructor() {
    effect(() => {
      const [q, a] = [this.quizId(), this.attemptId()];
      untracked(() => {
        this.loading.set(true);
        this.api.attempt(q, a).subscribe({
          next: (r) => {
            this.result.set(r);
            this.loading.set(false);
          },
          error: (e) => {
            this.error.set(apiErrorMessage(e, 'These results could not be loaded.'));
            this.loading.set(false);
          },
        });
      });
    });
  }
}
