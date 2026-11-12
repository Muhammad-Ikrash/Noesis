import { ChangeDetectionStrategy, Component, computed, effect, inject, input, signal, untracked } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { DocumentOut, QuizSummary } from '../../core/api/models';
import { apiErrorMessage } from '../../core/http/api-error';
import { DocumentsService } from '../../core/services/documents.service';
import { QuizService } from '../../core/services/quiz.service';
import { ToastService } from '../../core/services/toast.service';
import { relativeTime } from '../../shared/format';
import { ConfirmDialog } from '../../shared/ui/confirm-dialog';
import { Icon } from '../../shared/ui/icon';

@Component({
  selector: 'app-quiz-list-page',
  imports: [FormsModule, RouterLink, Icon, ConfirmDialog],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './quiz-list-page.html',
  styleUrl: './quiz-list-page.scss',
})
export class QuizListPage {
  /** ?docs=id1,id2 pre-selects documents (from the library). */
  readonly docsParam = input<string>(undefined, { alias: 'docs' });

  private readonly quizApi = inject(QuizService);
  private readonly docsApi = inject(DocumentsService);
  private readonly toast = inject(ToastService);
  private readonly router = inject(Router);
  protected readonly ago = relativeTime;

  protected readonly quizzes = signal<QuizSummary[]>([]);
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);

  protected readonly library = signal<DocumentOut[]>([]);
  protected readonly picked = signal<Set<string>>(new Set());
  protected readonly topic = signal('');
  protected readonly count = signal(5);
  protected readonly generating = signal(false);
  protected readonly genError = signal<string | null>(null);

  protected readonly toDelete = signal<QuizSummary | null>(null);
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
    this.quizApi.list().subscribe({
      next: (q) => {
        this.quizzes.set(q);
        this.loading.set(false);
      },
      error: (e) => {
        this.error.set(apiErrorMessage(e, 'Could not load your quizzes.'));
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
    this.quizApi
      .create({ document_ids: [...this.picked()], topic: this.topic().trim() || undefined, question_count: this.count() })
      .subscribe({
        next: (q) => this.router.navigate(['/quizzes', q.id]),
        error: (e) => {
          this.generating.set(false);
          this.genError.set(apiErrorMessage(e, 'The quiz could not be generated.'));
        },
      });
  }

  protected confirmDelete(): void {
    const q = this.toDelete();
    if (!q) return;
    this.deleting.set(true);
    this.quizApi.delete(q.id).subscribe({
      next: () => {
        this.quizzes.update((l) => l.filter((x) => x.id !== q.id));
        this.deleting.set(false);
        this.toDelete.set(null);
        this.toast.ok('Quiz deleted.');
      },
      error: (e) => {
        this.deleting.set(false);
        this.toast.error(apiErrorMessage(e));
      },
    });
  }

  protected pct(q: QuizSummary): number {
    return q.best_score === null ? 0 : Math.round((q.best_score / q.question_count) * 100);
  }
}
