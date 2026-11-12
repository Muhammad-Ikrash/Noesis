import { ChangeDetectionStrategy, Component, computed, effect, inject, input, signal, untracked } from '@angular/core';
import { RouterLink } from '@angular/router';
import { AttemptResult } from '../../core/api/models';
import { apiErrorMessage } from '../../core/http/api-error';
import { QuizService } from '../../core/services/quiz.service';
import { Icon } from '../../shared/ui/icon';

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
            <a class="btn btn--primary" [routerLink]="['/quizzes', r.quiz_id]"><app-icon name="refresh" [size]="14" />Retake</a>
            <a class="btn" routerLink="/quizzes">New quiz</a>
          </div>
        </header>

        <ol class="review">
          @for (q of r.questions; track q.id; let i = $index) {
            @let given = r.answers[i];
            @let right = given === q.correct_index;
            <li [class.is-right]="right" [class.is-wrong]="!right">
              <p class="mark mono">{{ right ? 'Correct' : given === null ? 'Skipped' : 'Incorrect' }}</p>
              <h3>{{ i + 1 }}. {{ q.prompt }}</h3>
              <ul class="opts">
                @for (opt of q.options; track $index; let o = $index) {
                  <li [class.correct]="o === q.correct_index" [class.chosen]="o === given && !right">
                    <span class="key mono">{{ 'ABCD'[o] }}</span>{{ opt }}
                    @if (o === q.correct_index) { <app-icon name="check" [size]="14" /> }
                    @if (o === given && !right) { <span class="mono you">your answer</span> }
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
    .actions { display: flex; gap: var(--space-2); margin-top: var(--space-3); }
    .review { list-style: none; margin: 0; padding: 0; }
    .review > li { padding: var(--space-5) 0 var(--space-5) var(--space-4); border-bottom: 1px solid var(--rule); border-left: 3px solid transparent; }
    .review > li.is-right { border-left-color: var(--ok); }
    .review > li.is-wrong { border-left-color: var(--danger); }
    .mark { font-size: var(--text-xs); text-transform: uppercase; letter-spacing: .08em; }
    .is-right .mark { color: var(--ok); }
    .is-wrong .mark { color: var(--danger); }
    h3 { margin: var(--space-2) 0 var(--space-3); font-size: var(--text-lg); }
    .opts {
      list-style: none; margin: 0 0 var(--space-3); padding: 0; display: grid; gap: 4px;
      li { display: flex; gap: var(--space-3); align-items: center; padding: 6px var(--space-3); border-radius: var(--radius-sm); font-family: var(--font-read); }
      .correct { background: var(--ok-soft); color: var(--ok); }
      .chosen { background: var(--danger-soft); color: var(--danger); text-decoration: line-through; text-decoration-thickness: 1px; }
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
  protected readonly result = signal<AttemptResult | null>(null);
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);

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
