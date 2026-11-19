import { ChangeDetectionStrategy, Component, computed, inject, input, output, signal } from '@angular/core';
import { Message, Source } from '../../core/api/models';
import { ToastService } from '../../core/services/toast.service';
import { answerToMarkdown } from '../../shared/answer-text';
import { copyText } from '../../shared/download';
import { Icon } from '../../shared/ui/icon';
import { RichText } from '../../shared/ui/rich-text';

export type SuggestionAction = 'library' | 'attach' | 'extensive';

@Component({
  selector: 'app-chat-message',
  imports: [RichText, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './chat-message.html',
  styleUrl: './chat-message.scss',
})
export class ChatMessage {
  readonly message = input.required<Message>();
  readonly openSource = output<Source>();
  readonly suggest = output<SuggestionAction>();

  protected readonly isUser = computed(() => this.message().role === 'user');
  protected readonly status = computed(() => this.message().answer_status);
  protected readonly extensive = computed(() => this.message().mode === 'extensive');
  /** Answered messages (including "not covered" ones that still carry text) can be copied with their sources. */
  protected readonly canCopy = computed(() => {
    const m = this.message();
    return (m.answer_status === 'answered' || m.answer_status === 'insufficient_context') && !!m.content.trim();
  });
  protected readonly copied = signal(false);

  private readonly toast = inject(ToastService);

  protected async copy(): Promise<void> {
    const ok = await copyText(answerToMarkdown(this.message()));
    if (!ok) {
      this.toast.error('Could not copy to the clipboard.');
      return;
    }
    this.copied.set(true);
    this.toast.ok(this.message().sources.length ? 'Answer copied with its sources.' : 'Answer copied.');
    setTimeout(() => this.copied.set(false), 1500);
  }

  protected cite(n: number): void {
    const s = this.message().sources.find((x) => x.position === n);
    if (s) this.openSource.emit(s);
  }
}
