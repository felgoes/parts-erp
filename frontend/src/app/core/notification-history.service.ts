import { Injectable, computed, inject, signal } from '@angular/core';
import { finalize } from 'rxjs';
import { ApiService } from './api.service';
import { SettingsApi } from './api/settings-api';
import { AuthService } from './auth.service';
import { PushNotification } from './models';

@Injectable({ providedIn: 'root' })
export class NotificationHistory {
  private readonly api = inject(ApiService);
  private readonly settings = inject(SettingsApi);
  private readonly auth = inject(AuthService);
  private readonly items = signal<PushNotification[]>([]);
  private readonly loadedFor = signal<string | undefined>(undefined);
  private readonly seen = signal('');
  private request = 0;
  private markPending = false;
  readonly loading = signal(false);
  readonly error = signal('');
  readonly deleting = signal<string | null>(null);
  readonly history = computed(() => this.loadedFor() === this.auth.user()?.id ? this.items() : []);
  readonly unread = computed(() => this.history().filter((item) => item.created_at > this.seen()).length);

  seenAt(): string {
    const id = this.auth.user()?.id;
    try { return id ? localStorage.getItem('parts-erp.notifications.seen.' + id) ?? '' : ''; }
    catch { return this.seen(); }
  }

  load(markSeen = false): void {
    const userId = this.auth.user()?.id;
    if (!userId) return;
    if (this.loadedFor() !== userId) {
      this.items.set([]);
      this.loadedFor.set(userId);
      this.markPending = false;
    }
    this.markPending ||= markSeen;
    const request = ++this.request;
    this.seen.set(this.seenAt());
    this.loading.set(true);
    this.error.set('');
    this.api.pushHistory().pipe(finalize(() => {
      if (request === this.request) this.loading.set(false);
    })).subscribe({
      next: (items) => {
        if (request !== this.request || userId !== this.auth.user()?.id) return;
        this.items.set(items);
        const latest = items[0]?.created_at;
        if (this.markPending && latest) {
          this.seen.set(latest);
          try { localStorage.setItem('parts-erp.notifications.seen.' + userId, latest); } catch { /* Session only. */ }
        }
        this.markPending = false;
      },
      error: () => {
        if (request !== this.request) return;
        this.markPending = false;
        this.error.set('Não foi possível carregar as notificações.');
      },
    });
  }

  dismiss(item: PushNotification): void {
    if (this.deleting()) return;
    this.deleting.set(item.id);
    this.error.set('');
    this.settings.dismissPushNotification(item.id).pipe(finalize(() => this.deleting.set(null))).subscribe({
      next: () => this.items.update((items) => items.filter((value) => value.id !== item.id)),
      error: () => this.error.set('Não foi possível excluir a notificação.'),
    });
  }
}
