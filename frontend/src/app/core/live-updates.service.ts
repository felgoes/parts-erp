import { Injectable, effect, inject } from '@angular/core';
import { Subject } from 'rxjs';
import { apiUrl } from './api-url';
import { AuthService } from './auth.service';

@Injectable({ providedIn: 'root' })
export class LiveUpdatesService {
  private readonly auth = inject(AuthService);
  private readonly updates = new Subject<void>();
  readonly changes$ = this.updates.asObservable();
  private active = false;
  private controller?: AbortController;
  private fallbackTimer?: ReturnType<typeof setInterval>;

  constructor() {
    effect(() => {
      if (this.auth.isAuthenticated()) this.start();
      else this.stop();
    });
    window.addEventListener('focus', () => this.refreshVisible());
    document.addEventListener('visibilitychange', () => this.refreshVisible());
  }

  private start(): void {
    if (this.active) return;
    this.active = true;
    this.fallbackTimer = setInterval(() => this.refreshVisible(), 20_000);
    void this.connect();
  }

  private stop(): void {
    this.active = false;
    this.controller?.abort();
    if (this.fallbackTimer) clearInterval(this.fallbackTimer);
    this.fallbackTimer = undefined;
  }

  private refreshVisible(): void {
    if (this.active && document.visibilityState === 'visible') this.updates.next();
  }

  private async connect(): Promise<void> {
    while (this.active) {
      const controller = new AbortController();
      this.controller = controller;
      try {
        const token = this.auth.token;
        if (!token) return;
        const response = await fetch(apiUrl('/events/stream'), {
          headers: { Authorization: `Bearer ${token}` },
          cache: 'no-store',
          signal: controller.signal,
        });
        if (!response.ok || !response.body) throw new Error(`Stream HTTP ${response.status}`);
        this.refreshVisible();
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (this.active) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const frames = buffer.split('\n\n');
          buffer = frames.pop() ?? '';
          if (frames.some((frame) => frame.includes('event: update'))) this.refreshVisible();
        }
      } catch {
        // The periodic refresh remains active while the stream reconnects.
      } finally {
        if (this.controller === controller) this.controller = undefined;
      }
      if (this.active) await new Promise((resolve) => setTimeout(resolve, 2_000));
    }
  }
}
