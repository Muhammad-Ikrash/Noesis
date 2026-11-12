import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { Message, Source } from '../../core/api/models';
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

  protected cite(n: number): void {
    const s = this.message().sources.find((x) => x.position === n);
    if (s) this.openSource.emit(s);
  }
}
