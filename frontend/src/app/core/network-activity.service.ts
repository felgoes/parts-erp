import { Injectable, signal } from '@angular/core';

/**
 * Acompanha as chamadas à API: quando a tela está buscando dados e se o servidor está alcançável.
 *
 * A faixa de "sem atualização recente" (P17) precisa das duas coisas — a hora do último contato
 * confirmado e a notícia de que o servidor parou de responder — e nenhuma delas existe só com o
 * silêncio do canal de atualização.
 */
@Injectable({ providedIn: 'root' })
export class NetworkActivityService {
  /** Sem resposta (rede fora) ou com a resposta de "servidor fora do ar" atrás do proxy. */
  private static readonly UNREACHABLE = new Set([0, 502, 503, 504]);
  private inFlight = 0;
  readonly busy = signal(false);
  readonly lastSuccessAt = signal<number | null>(null);
  readonly unreachable = signal(false);

  started(): void {
    this.inFlight += 1;
    this.busy.set(true);
  }

  settled(status: number): void {
    this.inFlight = Math.max(0, this.inFlight - 1);
    if (this.inFlight === 0) this.busy.set(false);
    if (NetworkActivityService.UNREACHABLE.has(status)) {
      // Sem resposta: rede fora, servidor inalcançável ou aplicativo sem internet.
      this.unreachable.set(true);
      return;
    }
    this.unreachable.set(false);
    if (status < 500) this.lastSuccessAt.set(Date.now());
  }

  /** O canal de atualização abriu: o servidor respondeu, mesmo antes da próxima chamada de dados. */
  reachable(): void {
    if (this.unreachable()) this.unreachable.set(false);
  }
}
