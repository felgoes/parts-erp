import { Injectable, computed, effect, inject, signal } from '@angular/core';
import { Capacitor, registerPlugin } from '@capacitor/core';
import { Subject } from 'rxjs';
import {
  HEARTBEAT_MS,
  REFRESH_TIMEOUT_MS,
  isAndroidApp,
  resumedAfterBackground,
} from './app-refresh';
import { apiUrl } from './api-url';
import { AuthService } from './auth.service';
import { NetworkActivityService } from './network-activity.service';

interface NativeAppState {
  isActive: boolean;
}

interface NativeAppPlugin {
  addListener(
    event: 'appStateChange',
    callback: (state: NativeAppState) => void,
  ): Promise<{ remove(): Promise<void> }>;
}

/**
 * Plugin de aplicativo do casco Android. Se o casco não expuser o plugin, a chamada falha em
 * silêncio e a retomada continua sendo detectada pelo relógio interno — o WebView congela os
 * temporizadores em segundo plano, e a pausa no relógio é o sinal de que o app voltou.
 */
const nativeApp = registerPlugin<NativeAppPlugin>('App');

@Injectable({ providedIn: 'root' })
export class LiveUpdatesService {
  private readonly auth = inject(AuthService);
  private readonly activity = inject(NetworkActivityService);
  private readonly updates = new Subject<void>();
  /** Algo mudou: as telas recarregam os próprios dados ao receber. */
  readonly changes$ = this.updates.asObservable();
  /** Recarga em andamento — liga o indicador do gesto. */
  readonly refreshing = signal(false);
  /** Quanto o dedo já puxou a tela, em pixels. */
  readonly pullOffset = signal(0);
  /** Sem contato com o servidor: a faixa discreta entra no lugar. */
  readonly offline = computed(() => this.activity.unreachable());
  /** Hora do último contato confirmado com o servidor. */
  readonly lastUpdateAt = computed(() => this.activity.lastSuccessAt());

  private active = false;
  private controller?: AbortController;
  private fallbackTimer?: ReturnType<typeof setInterval>;
  private heartbeat?: ReturnType<typeof setInterval>;
  private settleTimer?: ReturnType<typeof setTimeout>;
  private nativeListener?: { remove(): Promise<void> };
  private streamGeneration = 0;
  private heldEdits = 0;
  private pendingAuto = false;
  private wasHidden = false;
  private lastBeat = Date.now();

  constructor() {
    effect(() => {
      if (this.auth.isAuthenticated()) this.start();
      else this.stop();
    });
    window.addEventListener('focus', () => this.resume(false));
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState !== 'visible') {
        this.wasHidden = true;
        return;
      }
      // Voltar para a frente é o momento em que o dado pode estar velho — e em que o canal de
      // atualização pode ter morrido no segundo plano.
      const paused = this.wasHidden;
      this.wasHidden = false;
      this.resume(paused);
    });
  }

  isAndroidApp(): boolean {
    return isAndroidApp(Capacitor.isNativePlatform(), Capacitor.getPlatform());
  }

  /** Recarga pedida pelo usuário (gesto de puxar ou botão "tentar agora"). */
  refreshNow(): void {
    this.emit();
  }

  /** Marca digitação não salva: a recarga automática espera até o fim da edição. */
  beginEdit(): void {
    this.heldEdits += 1;
  }

  endEdit(): void {
    this.heldEdits = Math.max(0, this.heldEdits - 1);
    this.releaseHeld();
  }

  private start(): void {
    if (this.active) return;
    this.active = true;
    this.lastBeat = Date.now();
    this.fallbackTimer = setInterval(() => this.refreshAuto(), 20_000);
    this.heartbeat = setInterval(() => this.watchClock(), HEARTBEAT_MS);
    void this.listenNativeResume();
    this.startStream();
  }

  private stop(): void {
    this.active = false;
    this.streamGeneration += 1;
    this.controller?.abort();
    if (this.fallbackTimer) clearInterval(this.fallbackTimer);
    this.fallbackTimer = undefined;
    if (this.heartbeat) clearInterval(this.heartbeat);
    this.heartbeat = undefined;
    if (this.settleTimer) clearTimeout(this.settleTimer);
    this.settleTimer = undefined;
    this.refreshing.set(false);
    const listener = this.nativeListener;
    this.nativeListener = undefined;
    if (listener) void listener.remove().catch(() => undefined);
  }

  /** O relógio parou por tempo demais: o aplicativo esteve em segundo plano. */
  private watchClock(): void {
    const now = Date.now();
    if (resumedAfterBackground(this.lastBeat, now)) this.resume(true);
    this.lastBeat = now;
  }

  private resume(paused: boolean): void {
    if (!this.active) return;
    this.lastBeat = Date.now();
    if (paused) this.reconnect();
    this.refreshAuto();
  }

  private async listenNativeResume(): Promise<void> {
    if (!this.isAndroidApp() || this.nativeListener) return;
    try {
      this.nativeListener = await nativeApp.addListener('appStateChange', (state) => {
        if (state.isActive) this.resume(true);
      });
    } catch {
      this.nativeListener = undefined;
    }
  }

  /** Recarga automática: respeita a digitação em andamento (decisão 4 da P17). */
  private refreshAuto(): void {
    if (!this.active) return;
    if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return;
    if (this.holdAutomatic()) {
      this.pendingAuto = true;
      return;
    }
    this.emit();
  }

  /**
   * Existe alteração não salva? Duas respostas: o que uma tela marcou de propósito (`beginEdit`)
   * e o que o Angular já classifica sozinho — formulário alterado carrega a classe `ng-dirty`.
   */
  private holdAutomatic(): boolean {
    if (this.heldEdits > 0) return true;
    if (typeof document === 'undefined') return false;
    return document.querySelector('form.ng-dirty') !== null;
  }

  private releaseHeld(): void {
    if (!this.pendingAuto || this.holdAutomatic()) return;
    this.pendingAuto = false;
    this.refreshAuto();
  }

  private emit(): void {
    this.updates.next();
    this.watchRefresh();
  }

  /** O indicador fica de pé até a tela terminar de buscar os dados (ou até o limite). */
  private watchRefresh(): void {
    if (this.settleTimer) clearTimeout(this.settleTimer);
    this.refreshing.set(true);
    const deadline = Date.now() + REFRESH_TIMEOUT_MS;
    const poll = (): void => {
      this.settleTimer = setTimeout(() => {
        if (this.activity.busy() && Date.now() < deadline) {
          poll();
          return;
        }
        this.settleTimer = undefined;
        this.refreshing.set(false);
      }, 200);
    };
    // As telas aplicam a recarga com um pequeno atraso; olhar a rede antes disso veria a casa vazia.
    this.settleTimer = setTimeout(poll, 400);
  }

  private startStream(): void {
    const generation = ++this.streamGeneration;
    void this.streamLoop(generation);
  }

  /** Derruba a conexão atual (que pode ter morrido no segundo plano) e abre outra. */
  private reconnect(): void {
    this.controller?.abort();
    if (this.active) this.startStream();
  }

  private async streamLoop(generation: number): Promise<void> {
    while (this.active && generation === this.streamGeneration) {
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
        this.activity.reachable();
        this.refreshAuto();
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (this.active && generation === this.streamGeneration) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const frames = buffer.split('\n\n');
          buffer = frames.pop() ?? '';
          if (frames.some((frame) => frame.includes('event: update'))) this.refreshAuto();
        }
      } catch {
        // O ciclo de 20 segundos segue como rede de proteção enquanto o canal se recupera.
      } finally {
        if (this.controller === controller) this.controller = undefined;
      }
      if (this.active && generation === this.streamGeneration) {
        await new Promise((resolve) => setTimeout(resolve, 2_000));
      }
    }
  }
}
