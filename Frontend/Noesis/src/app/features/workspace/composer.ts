import { ChangeDetectionStrategy, Component, ElementRef, input, model, output, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { LearningMode, RetrievalScope } from '../../core/api/models';
import { Icon } from '../../shared/ui/icon';

@Component({
  selector: 'app-composer',
  imports: [FormsModule, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <form class="composer" (submit)="$event.preventDefault(); submit()">
      <div class="controls">
        <div class="seg" role="group" aria-label="Learning mode">
          <button type="button" [attr.aria-pressed]="mode() === 'basic'" (click)="modeChange.emit('basic')"
                  title="Answers only from your PDFs, with citations">Basic</button>
          <button type="button" [attr.aria-pressed]="mode() === 'extensive'" (click)="modeChange.emit('extensive')"
                  title="Your PDFs first, plus clearly-labelled deeper explanation">Extensive</button>
        </div>
        <div class="scope" role="group" aria-label="Which PDFs to search">
          <span class="scope__label">Search</span>
          <div class="seg">
            <button type="button" [attr.aria-pressed]="scope() === 'session'" (click)="scopeChange.emit('session')">This chat's PDFs</button>
            <button type="button" [attr.aria-pressed]="scope() === 'library'" (click)="scopeChange.emit('library')">Whole library</button>
          </div>
        </div>
      </div>
      <div class="box">
        <textarea #ta name="q" rows="1" [(ngModel)]="text" [placeholder]="placeholder()" [disabled]="disabled()"
                  (input)="grow()" (keydown.enter)="onEnter($event)" aria-label="Your question" maxlength="4000"></textarea>
        <button class="btn btn--primary btn--icon" type="submit" [disabled]="disabled() || !text().trim()" aria-label="Send">
          @if (busy()) { <span class="spinner"></span> } @else { <app-icon name="send" /> }
        </button>
      </div>
      <p class="hint mono">{{ mode() === 'basic' ? 'Basic: answers only from your PDFs.' : 'Extensive: PDFs first, extra explanation labelled.' }}
        <span class="kbd">Enter</span> to send · <span class="kbd">Shift+Enter</span> new line</p>
    </form>
  `,
  styles: `
    .composer { display: grid; gap: var(--space-2); }
    .controls { display: flex; flex-wrap: wrap; justify-content: space-between; gap: var(--space-2); }
    .scope { display: flex; align-items: center; gap: var(--space-2); }
    .scope__label { font-size: var(--text-xs); color: var(--ink-3); }
    .box {
      display: flex; align-items: flex-end; gap: var(--space-2);
      padding: var(--space-2) var(--space-2) var(--space-2) var(--space-4);
      border: 1px solid var(--rule-strong); border-radius: var(--radius); background: var(--surface);
      &:focus-within { border-color: var(--focus); box-shadow: 0 0 0 3px color-mix(in srgb, var(--focus), transparent 82%); }
    }
    textarea {
      flex: 1; resize: none; border: 0; background: none; outline: none;
      font-family: var(--font-read); font-size: var(--text-read); line-height: 1.5;
      max-height: 200px; padding: 6px 0;
    }
    .hint { font-size: 11px; color: var(--ink-3); }
    .kbd { padding: 0 4px; border: 1px solid var(--rule); border-radius: 3px; }
    @media (max-width: 560px) { .hint .kbd { display: none; } }
  `,
})
export class Composer {
  readonly mode = input.required<LearningMode>();
  readonly scope = input.required<RetrievalScope>();
  readonly busy = input(false);
  readonly disabled = input(false);
  readonly placeholder = input('Ask about your PDFs…');
  readonly text = model('');
  readonly send = output<string>();
  readonly modeChange = output<LearningMode>();
  readonly scopeChange = output<RetrievalScope>();

  private readonly ta = viewChild.required<ElementRef<HTMLTextAreaElement>>('ta');

  protected onEnter(event: Event): void {
    if ((event as KeyboardEvent).shiftKey) return;
    event.preventDefault();
    this.submit();
  }

  protected submit(): void {
    const q = this.text().trim();
    if (!q || this.disabled()) return;
    this.send.emit(q);
  }

  protected grow(): void {
    const el = this.ta().nativeElement;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }

  focus(): void {
    this.ta().nativeElement.focus();
  }

  reset(): void {
    this.text.set('');
    queueMicrotask(() => this.grow());
  }
}
