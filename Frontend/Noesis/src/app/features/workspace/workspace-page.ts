import {
  ChangeDetectionStrategy, Component, ElementRef, computed, effect, inject, input, signal, untracked, viewChild,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import {
  AskResponse, Conversation, ConversationDetail, DocumentOut, LearningMode, Message, RetrievalScope, Source,
} from '../../core/api/models';
import { apiErrorMessage } from '../../core/http/api-error';
import { ConversationsService } from '../../core/services/conversations.service';
import { DocumentsService } from '../../core/services/documents.service';
import { QuizService } from '../../core/services/quiz.service';
import { ToastService } from '../../core/services/toast.service';
import { relativeTime } from '../../shared/format';
import { ConfirmDialog } from '../../shared/ui/confirm-dialog';
import { Icon } from '../../shared/ui/icon';
import { PdfViewer, ViewerTarget } from '../../shared/ui/pdf-viewer';
import { AttachDialog } from './attach-dialog';
import { ChatMessage, SuggestionAction } from './chat-message';
import { Composer } from './composer';

interface OpenDoc {
  id: string;
  filename: string;
}

@Component({
  selector: 'app-workspace-page',
  imports: [RouterLink, Icon, PdfViewer, ChatMessage, Composer, AttachDialog, ConfirmDialog],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './workspace-page.html',
  styleUrl: './workspace-page.scss',
  host: { class: 'workspace' },
})
export class WorkspacePage {
  /** Bound from the route (/study/:conversationId). */
  readonly conversationId = input<string>();

  private readonly convApi = inject(ConversationsService);
  private readonly docsApi = inject(DocumentsService);
  private readonly quizApi = inject(QuizService);
  private readonly toast = inject(ToastService);
  private readonly router = inject(Router);
  private readonly thread = viewChild<ElementRef<HTMLElement>>('thread');
  private readonly composer = viewChild(Composer);

  protected readonly ago = relativeTime;

  // Rail
  protected readonly conversations = signal<Conversation[]>([]);
  protected readonly railOpen = signal(false);

  // Conversation
  protected readonly detail = signal<ConversationDetail | null>(null);
  protected readonly loading = signal(false);
  protected readonly loadError = signal<string | null>(null);
  protected readonly messages = signal<Message[]>([]);
  protected readonly mode = signal<LearningMode>('basic');
  protected readonly scope = signal<RetrievalScope>('session');
  protected readonly pendingQuestion = signal<string | null>(null);
  protected readonly sendError = signal<{ question: string; message: string } | null>(null);
  protected readonly draft = signal('');
  protected readonly editingTitle = signal(false);

  // Viewer
  protected readonly openDocs = signal<OpenDoc[]>([]);
  protected readonly activeDoc = signal<string | null>(null);
  protected readonly target = signal<ViewerTarget | null>(null);
  protected readonly mobileTab = signal<'chat' | 'pdf'>('chat');

  // Dialogs / actions
  protected readonly attachOpen = signal(false);
  protected readonly attachBusy = signal(false);
  protected readonly deleteOpen = signal(false);
  protected readonly deleting = signal(false);
  protected readonly quizBusy = signal(false);

  // Start screen (no conversation selected)
  protected readonly library = signal<DocumentOut[]>([]);
  protected readonly libraryLoading = signal(false);
  protected readonly startPicked = signal<Set<string>>(new Set());
  protected readonly starting = signal(false);

  protected readonly lastAssistant = computed(() => [...this.messages()].reverse().find((m) => m.role === 'assistant'));
  protected readonly awaitingClarification = computed(() => this.lastAssistant()?.needs_clarification ?? false);
  protected readonly attachedIds = computed(() => this.detail()?.documents.map((d) => d.id) ?? []);
  protected readonly noDocsForSession = computed(
    () => this.scope() === 'session' && (this.detail()?.documents.filter((d) => d.status === 'completed').length ?? 0) === 0,
  );

  constructor() {
    this.loadRail();
    effect(() => {
      const id = this.conversationId();
      untracked(() => (id ? this.load(id) : this.showStart()));
    });
    // Keep the newest message in view.
    effect(() => {
      this.messages();
      this.pendingQuestion();
      queueMicrotask(() => {
        const el = this.thread()?.nativeElement;
        if (el) el.scrollTop = el.scrollHeight;
      });
    });
  }

  // ----- loading ------------------------------------------------------------

  private loadRail(): void {
    this.convApi.list().subscribe({ next: (c) => this.conversations.set(c), error: () => {} });
  }

  protected load(id: string): void {
    this.loading.set(true);
    this.loadError.set(null);
    this.sendError.set(null);
    this.pendingQuestion.set(null);
    this.railOpen.set(false);
    this.convApi.get(id).subscribe({
      next: (c) => {
        this.detail.set(c);
        this.messages.set(c.messages);
        this.mode.set(c.mode);
        this.scope.set(c.retrieval_scope);
        const docs = c.documents.filter((d) => d.status === 'completed').map((d) => ({ id: d.id, filename: d.filename }));
        this.openDocs.set(docs);
        this.activeDoc.set(docs[0]?.id ?? null);
        this.target.set(null);
        this.loading.set(false);
        queueMicrotask(() => this.composer()?.focus());
      },
      error: (e) => {
        this.detail.set(null);
        this.loading.set(false);
        this.loadError.set(apiErrorMessage(e, 'This study session could not be loaded.'));
      },
    });
  }

  private showStart(): void {
    this.detail.set(null);
    this.messages.set([]);
    this.loadError.set(null);
    this.libraryLoading.set(true);
    this.docsApi.list().subscribe({
      next: (d) => {
        this.library.set(d.filter((x) => x.status === 'completed'));
        this.libraryLoading.set(false);
      },
      error: (e) => {
        this.libraryLoading.set(false);
        this.loadError.set(apiErrorMessage(e, 'Could not load your library.'));
      },
    });
  }

  // ----- start --------------------------------------------------------------

  protected toggleStart(id: string): void {
    this.startPicked.update((s) => {
      const next = new Set(s);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  protected start(): void {
    const ids = [...this.startPicked()];
    this.starting.set(true);
    this.convApi.create({ document_ids: ids, retrieval_scope: ids.length ? undefined : 'library' }).subscribe({
      next: (c) => {
        this.starting.set(false);
        this.startPicked.set(new Set());
        this.conversations.update((l) => [c, ...l]);
        this.router.navigate(['/study', c.id]);
      },
      error: (e) => {
        this.starting.set(false);
        this.toast.error(apiErrorMessage(e, 'Could not start a session.'));
      },
    });
  }

  // ----- chat ---------------------------------------------------------------

  protected send(question: string): void {
    const conv = this.detail();
    if (!conv || this.pendingQuestion()) return;
    this.pendingQuestion.set(question);
    this.sendError.set(null);
    this.composer()?.reset();
    this.convApi.ask(conv.id, { question, mode: this.mode(), retrieval_scope: this.scope() }).subscribe({
      next: (res) => {
        this.messages.update((l) => [...l, res.user_message, toAssistant(res)]);
        this.pendingQuestion.set(null);
        if (this.messages().length === 2) this.loadRail(); // title is set from the first question
        else this.bumpRail(conv.id);
      },
      error: (e) => {
        this.pendingQuestion.set(null);
        this.sendError.set({ question, message: apiErrorMessage(e, 'The answer could not be generated.') });
      },
    });
  }

  protected retrySend(): void {
    const err = this.sendError();
    if (err) this.send(err.question);
  }

  protected editFailed(): void {
    const err = this.sendError();
    if (!err) return;
    this.draft.set(err.question);
    this.sendError.set(null);
    queueMicrotask(() => this.composer()?.focus());
  }

  protected setMode(mode: LearningMode): void {
    if (mode === this.mode()) return;
    this.mode.set(mode);
    this.persist({ mode });
  }

  protected setScope(scope: RetrievalScope): void {
    if (scope === this.scope()) return;
    this.scope.set(scope);
    this.persist({ retrieval_scope: scope });
  }

  private persist(change: { mode?: LearningMode; retrieval_scope?: RetrievalScope }): void {
    const conv = this.detail();
    if (conv) this.convApi.update(conv.id, change).subscribe({ error: () => this.toast.error('Could not save that setting.') });
  }

  protected onSuggest(action: SuggestionAction): void {
    const lastQ = [...this.messages()].reverse().find((m) => m.role === 'user')?.content;
    if (action === 'attach') {
      this.attachOpen.set(true);
      return;
    }
    if (action === 'library') this.setScope('library');
    if (action === 'extensive') this.setMode('extensive');
    if (lastQ) this.send(lastQ);
  }

  private bumpRail(id: string): void {
    this.conversations.update((list) => {
      const c = list.find((x) => x.id === id);
      return c ? [{ ...c, last_message_at: new Date().toISOString() }, ...list.filter((x) => x.id !== id)] : list;
    });
  }

  // ----- viewer -------------------------------------------------------------

  protected openSource(s: Source): void {
    if (!s.document_id) return;
    const id = s.document_id;
    if (!this.openDocs().some((d) => d.id === id)) this.openDocs.update((l) => [...l, { id, filename: s.filename }]);
    this.activeDoc.set(id);
    this.target.set({ page: s.page_number, quote: s.quote, nonce: Date.now() });
    this.mobileTab.set('pdf');
  }

  protected selectDoc(id: string): void {
    this.activeDoc.set(id);
    this.target.set(null);
  }

  // ----- header actions -----------------------------------------------------

  protected saveTitle(event: Event): void {
    const conv = this.detail();
    const value = (event.target as HTMLInputElement).value.trim();
    this.editingTitle.set(false);
    if (!conv || !value || value === conv.title) return;
    this.detail.set({ ...conv, title: value });
    this.conversations.update((l) => l.map((c) => (c.id === conv.id ? { ...c, title: value } : c)));
    this.convApi.update(conv.id, { title: value }).subscribe({ error: () => this.toast.error('Could not rename.') });
  }

  protected saveAttached(ids: string[]): void {
    const conv = this.detail();
    if (!conv) return;
    this.attachBusy.set(true);
    this.convApi.update(conv.id, { document_ids: ids }).subscribe({
      next: (c) => {
        this.detail.set({ ...conv, documents: c.documents });
        const docs = c.documents.map((d) => ({ id: d.id, filename: d.filename }));
        this.openDocs.set(docs);
        if (!docs.some((d) => d.id === this.activeDoc())) this.activeDoc.set(docs[0]?.id ?? null);
        this.attachBusy.set(false);
        this.attachOpen.set(false);
        this.toast.ok(`${docs.length} PDF${docs.length === 1 ? '' : 's'} in this chat.`);
      },
      error: (e) => {
        this.attachBusy.set(false);
        this.toast.error(apiErrorMessage(e, 'Could not update PDFs.'));
      },
    });
  }

  protected quizMe(): void {
    const conv = this.detail();
    if (!conv) return;
    if (!conv.documents.some((d) => d.status === 'completed')) {
      this.toast.info('Attach at least one PDF to this chat to build a quiz.');
      this.attachOpen.set(true);
      return;
    }
    this.quizBusy.set(true);
    this.quizApi.create({ conversation_id: conv.id, question_count: 5 }).subscribe({
      next: (q) => this.router.navigate(['/quizzes', q.id]),
      error: (e) => {
        this.quizBusy.set(false);
        this.toast.error(apiErrorMessage(e, 'Could not generate a quiz.'));
      },
    });
  }

  protected deleteConversation(): void {
    const conv = this.detail();
    if (!conv) return;
    this.deleting.set(true);
    this.convApi.delete(conv.id).subscribe({
      next: () => {
        this.deleting.set(false);
        this.deleteOpen.set(false);
        this.conversations.update((l) => l.filter((c) => c.id !== conv.id));
        this.toast.ok('Session deleted.');
        this.router.navigate(['/study']);
      },
      error: (e) => {
        this.deleting.set(false);
        this.toast.error(apiErrorMessage(e, 'Could not delete the session.'));
      },
    });
  }
}

function toAssistant(res: AskResponse): Message {
  return {
    id: res.message_id,
    role: 'assistant',
    content: res.answer,
    supplementary: res.supplementary,
    mode: res.mode,
    retrieval_scope: res.retrieval_scope,
    answer_status: res.answer_status,
    needs_clarification: res.needs_clarification,
    clarification_question: res.clarification_question,
    created_at: res.user_message.created_at,
    sources: res.sources,
  };
}
