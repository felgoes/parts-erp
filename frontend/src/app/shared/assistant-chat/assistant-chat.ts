import { DatePipe } from '@angular/common';
import {
  Component,
  ElementRef,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AssistantApi } from '../../core/api/assistant-api';
import { AuthService } from '../../core/auth.service';
import {
  AssistantBudget,
  AssistantConversation,
  AssistantConversationSummary,
  AssistantPendingAction,
} from '../../core/models/assistant';
import { renderAssistantMarkdown } from './assistant-markdown';

@Component({
  selector: 'app-assistant-chat',
  imports: [DatePipe, FormsModule],
  templateUrl: './assistant-chat.html',
  styleUrl: './assistant-chat.scss',
})
export class AssistantChat {
  private readonly api = inject(AssistantApi);
  readonly auth = inject(AuthService);
  readonly open = signal(false);
  readonly showHistory = signal(false);
  readonly conversations = signal<AssistantConversationSummary[]>([]);
  readonly conversation = signal<AssistantConversation | null>(null);
  readonly pending = signal<AssistantPendingAction[]>([]);
  readonly budget = signal<AssistantBudget | null>(null);
  readonly draft = signal('');
  readonly sending = signal(false);
  readonly loading = signal(false);
  readonly error = signal('');
  readonly isAdmin = computed(() => this.auth.user()?.role === 'admin');
  readonly budgetLabel = computed(() => {
    const value = this.budget();
    if (!value?.percent_used) return '';
    return `${Number(value.percent_used).toLocaleString('pt-BR', {
      maximumFractionDigits: 0,
    })}% do limite`;
  });
  private readonly messagesEnd = viewChild<ElementRef<HTMLElement>>('messagesEnd');
  private readonly composer = viewChild<ElementRef<HTMLTextAreaElement>>('composer');
  private loaded = false;

  toggle(): void {
    const next = !this.open();
    this.open.set(next);
    if (next) {
      this.loadConfiguration();
      this.loadConversations(!this.loaded);
      this.loaded = true;
      setTimeout(() => this.composer()?.nativeElement.focus());
    }
  }

  close(): void {
    this.open.set(false);
  }

  private loadConfiguration(): void {
    this.api.configuration().subscribe({
      next: (config) => this.budget.set(config.budget),
      error: () => undefined,
    });
  }

  private loadConversations(selectLast: boolean): void {
    this.loading.set(true);
    this.api.conversations().subscribe({
      next: (items) => {
        this.conversations.set(items);
        this.loading.set(false);
        if (!selectLast) return;
        const saved = localStorage.getItem('parts-erp.assistant.conversation');
        const target = items.find((item) => item.id === saved) ?? items[0];
        if (target) this.openConversation(target.id);
      },
      error: () => this.loading.set(false),
    });
  }

  openConversation(id: string): void {
    this.error.set('');
    this.api.conversation(id).subscribe({
      next: (value) => {
        this.conversation.set(value);
        localStorage.setItem('parts-erp.assistant.conversation', value.id);
        this.showHistory.set(false);
        this.loadActions(id);
        this.scrollToEnd();
      },
      error: (err) => this.error.set(this.messageOf(err, 'Não foi possível abrir a conversa.')),
    });
  }

  private loadActions(id: string): void {
    this.api.actions(id).subscribe({
      next: (items) => {
        this.pending.set(items);
        this.scrollToEnd();
      },
      error: () => this.pending.set([]),
    });
  }

  newConversation(): void {
    if (this.sending()) return;
    this.api.createConversation().subscribe({
      next: (created) => {
        this.conversations.update((items) => [created, ...items]);
        this.conversation.set({ ...created, messages: [] });
        this.pending.set([]);
        this.showHistory.set(false);
        localStorage.setItem('parts-erp.assistant.conversation', created.id);
      },
      error: (err) => this.error.set(this.messageOf(err, 'Não foi possível criar a conversa.')),
    });
  }

  deleteConversation(id: string, event: Event): void {
    event.stopPropagation();
    if (!window.confirm('Excluir esta conversa? Esta ação não pode ser desfeita.')) return;
    this.api.deleteConversation(id).subscribe({
      next: () => {
        this.conversations.update((items) => items.filter((item) => item.id !== id));
        if (this.conversation()?.id === id) {
          this.conversation.set(null);
          this.pending.set([]);
          localStorage.removeItem('parts-erp.assistant.conversation');
        }
      },
      error: (err) => this.error.set(this.messageOf(err, 'Não foi possível excluir a conversa.')),
    });
  }

  send(): void {
    const text = this.draft().trim();
    if (!text || this.sending()) return;
    const current = this.conversation();
    if (!current) {
      this.api.createConversation().subscribe({
        next: (created) => {
          this.conversations.update((items) => [created, ...items]);
          this.conversation.set({ ...created, messages: [] });
          this.sendText(text);
        },
        error: (err) => this.error.set(this.messageOf(err, 'Não foi possível criar a conversa.')),
      });
      return;
    }
    this.sendText(text);
  }

  private sendText(text: string): void {
    const current = this.conversation();
    if (!current) return;
    this.draft.set('');
    this.sending.set(true);
    this.error.set('');
    this.conversation.set({
      ...current,
      messages: [
        ...current.messages,
        {
          id: `local-${Date.now()}`,
          role: 'user',
          content: text,
          created_at: new Date().toISOString(),
        },
      ],
    });
    this.scrollToEnd();
    this.api.sendMessage(current.id, text).subscribe({
      next: (turn) => {
        this.sending.set(false);
        this.budget.set(turn.budget);
        this.pending.update((items) => [
          ...items,
          ...turn.pending_actions.filter(
            (action) => !items.some((item) => item.id === action.id),
          ),
        ]);
        this.openConversation(current.id);
      },
      error: (err) => {
        this.sending.set(false);
        this.error.set(this.messageOf(err, 'O assistente não respondeu agora.'));
        this.openConversation(current.id);
      },
    });
  }

  confirm(action: AssistantPendingAction): void {
    if (this.sending()) return;
    this.sending.set(true);
    this.error.set('');
    this.api.confirmAction(action.id).subscribe({
      next: (result) => {
        this.sending.set(false);
        this.pending.update((items) => items.filter((item) => item.id !== action.id));
        const current = this.conversation();
        if (current) this.openConversation(current.id);
        else this.error.set(result.message);
      },
      error: (err) => {
        this.sending.set(false);
        this.error.set(this.messageOf(err, 'Não foi possível confirmar a ação.'));
        const current = this.conversation();
        if (current) this.openConversation(current.id);
      },
    });
  }

  cancel(action: AssistantPendingAction): void {
    this.api.cancelAction(action.id).subscribe({
      next: () => this.pending.update((items) => items.filter((item) => item.id !== action.id)),
      error: (err) => this.error.set(this.messageOf(err, 'Não foi possível cancelar a ação.')),
    });
  }

  onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.send();
    }
  }

  rendered(content: string): string {
    return renderAssistantMarkdown(content);
  }

  private scrollToEnd(): void {
    setTimeout(() => this.messagesEnd()?.nativeElement.scrollIntoView({ block: 'end' }));
  }

  private messageOf(error: unknown, fallback: string): string {
    const detail = (error as { error?: { detail?: unknown } })?.error?.detail;
    return typeof detail === 'string' ? detail : fallback;
  }
}
