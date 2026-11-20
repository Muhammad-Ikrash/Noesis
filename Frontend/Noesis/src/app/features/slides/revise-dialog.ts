import {
  ChangeDetectionStrategy, Component, ElementRef, effect, input, output, signal, viewChild,
} from '@angular/core';
import { Icon } from '../../shared/ui/icon';

export type ReviseScope = 'slide' | 'deck';

export interface ReviseRequest {
  scope: ReviseScope;
  instruction: string;
}

const SUGGESTIONS: Record<ReviseScope, string[]> = {
  slide: ['Make it shorter', 'Use simpler language', 'Add an example from the PDF', 'Add more detail'],
  deck: ['Make every slide shorter', 'Use simpler language', 'Add a slide with examples', 'Focus more on the main argument'],
};

/** Native <dialog> (same look as the confirm dialog) asking what the AI should change. */
@Component({
  selector: 'app-revise-dialog',
  imports: [Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <dialog #dlg class="dialog" (close)="cancelled.emit()" (cancel)="onCancel($event)" aria-labelledby="revise-h">
      <form (submit)="$event.preventDefault(); submit()">
        <header>
          <h3 id="revise-h">Revise with AI</h3>
          <p class="muted small">Describe what to change. Noesis rewrites the slides using your PDF.</p>
        </header>
        <div class="dialog__body body">
          <div class="seg" role="group" aria-label="What to revise">
            <button type="button" [attr.aria-pressed]="scope() === 'slide'" (click)="scope.set('slide')" [disabled]="!slideNumber() || busy()"
                    [title]="slideNumber() ? '' : 'Pick a content slide to revise just one'">
              This slide{{ slideNumber() ? ' (' + slideNumber() + ')' : '' }}
            </button>
            <button type="button" [attr.aria-pressed]="scope() === 'deck'" (click)="scope.set('deck')" [disabled]="busy()">Whole deck</button>
          </div>

          <label class="field">
            <span>What should change?</span>
            <textarea #box class="input" rows="4" maxlength="1000" [value]="text()" (input)="text.set($any($event.target).value)"
                      (keydown.control.enter)="submit()" (keydown.meta.enter)="submit()" [disabled]="busy()"
                      [placeholder]="scope() === 'slide' ? 'e.g. Split this into two clearer points' : 'e.g. Focus more on the risks and add a summary slide'"></textarea>
          </label>

          <div class="chips" role="group" aria-label="Suggestions">
            @for (s of suggestions(); track s) {
              <button class="btn btn--sm btn--quiet" type="button" (click)="text.set(s); box.focus()" [disabled]="busy()">{{ s }}</button>
            }
          </div>

          @if (error()) { <div class="alert" role="alert"><div>{{ error() }}</div></div> }
          @if (busy()) { <p class="muted small" role="status">Rewriting… this takes a few seconds.</p> }
        </div>
        <footer>
          <button class="btn" type="button" (click)="dlg.close()" [disabled]="busy()">Cancel</button>
          <button class="btn btn--primary" type="submit" [disabled]="busy() || text().trim().length < 3">
            @if (busy()) { <span class="spinner"></span> } @else { <app-icon name="sparkle" [size]="14" /> }
            Revise {{ scope() === 'slide' ? 'slide' : 'deck' }}
          </button>
        </footer>
      </form>
    </dialog>
  `,
  styles: `
    .small { font-size: var(--text-sm); margin: var(--space-2) 0 0; }
    .body { display: grid; gap: var(--space-4); padding-bottom: var(--space-1); }
    .seg { justify-self: start; }
    textarea.input { resize: vertical; font-family: inherit; line-height: 1.45; }
    .chips { display: flex; flex-wrap: wrap; gap: var(--space-1); margin-top: calc(-1 * var(--space-2)); }
  `,
})
export class ReviseDialog {
  readonly open = input(false);
  /** Content slide number (1-based), or 0 on the title slide. */
  readonly slideNumber = input(0);
  readonly busy = input(false);
  readonly error = input<string | null>(null);
  readonly submitted = output<ReviseRequest>();
  readonly cancelled = output<void>();

  protected readonly scope = signal<ReviseScope>('slide');
  protected readonly text = signal('');
  protected readonly suggestions = () => SUGGESTIONS[this.scope()];

  private readonly dlg = viewChild.required<ElementRef<HTMLDialogElement>>('dlg');
  private readonly box = viewChild.required<ElementRef<HTMLTextAreaElement>>('box');

  constructor() {
    effect(() => {
      const el = this.dlg().nativeElement;
      if (this.open() && !el.open) {
        // Default to the slide being viewed; the title slide can only be revised with the deck.
        this.scope.set(this.slideNumber() ? 'slide' : 'deck');
        el.showModal();
        queueMicrotask(() => this.box().nativeElement.focus());
      }
      if (!this.open() && el.open) el.close();
    });
  }

  protected onCancel(event: Event): void {
    // Esc while a revision is running would hide it without stopping it.
    if (this.busy()) event.preventDefault();
  }

  protected submit(): void {
    const instruction = this.text().trim();
    if (this.busy() || instruction.length < 3) return;
    this.submitted.emit({ scope: this.scope(), instruction });
  }

  /** Called after a successful revision so the next one starts empty. */
  clear(): void {
    this.text.set('');
  }
}
