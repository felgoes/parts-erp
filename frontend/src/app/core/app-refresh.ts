/**
 * Regras do "puxar para atualizar" e da retomada do aplicativo (P17).
 *
 * Separado do serviço para a conta ficar testável sem navegador: quanto o dedo já puxou, a partir
 * de quando vale recarregar, e como reconhecer que o aplicativo voltou do segundo plano — inclusive
 * quando o Android congela os eventos de visibilidade do WebView e só o relógio denuncia a pausa.
 */

/** Distância que o dedo precisa puxar para valer a recarga. */
export const PULL_TRIGGER_PX = 72;
/** Quanto a faixa de "puxando" pode descer, para o gesto não virar uma cortina na tela. */
export const PULL_MAX_PX = 108;
/** Pausa no relógio que só acontece se o aplicativo ficou parado (tela bloqueada ou em segundo plano). */
export const RESUME_GAP_MS = 5_000;
/** Frequência do relógio usado para detectar a retomada. */
export const HEARTBEAT_MS = 2_000;
/** Tempo máximo que o indicador espera a tela terminar de recarregar. */
export const REFRESH_TIMEOUT_MS = 10_000;

export function isAndroidApp(native: boolean, platform: string): boolean {
  return native && platform === 'android';
}

/**
 * Deslocamento do gesto, em pixels. Só existe com a tela no topo — se a pessoa estiver rolando o
 * conteúdo, o gesto pertence à rolagem.
 */
export function pullOffset(startY: number, currentY: number, scrollTop: number): number {
  if (scrollTop > 0) return 0;
  return Math.max(0, currentY - startY);
}

/** Fração do gesto já cumprida, de 0 a 1, para a faixa acompanhar o dedo. */
export function pullProgress(offset: number, trigger: number = PULL_TRIGGER_PX): number {
  if (trigger <= 0) return 1;
  return Math.min(1, Math.max(0, offset / trigger));
}

export function pullBandHeight(offset: number, max: number = PULL_MAX_PX): number {
  return Math.min(max, Math.max(0, offset));
}

export function shouldRefresh(offset: number, trigger: number = PULL_TRIGGER_PX): boolean {
  return offset >= trigger;
}

/**
 * Uma pausa longa entre dois batimentos do relógio significa que o aplicativo esteve parado: o
 * Android suspende os temporizadores do WebView em segundo plano, então o intervalo real fica muito
 * maior que o esperado. É o sinal de retomada que não depende de evento de visibilidade.
 */
export function resumedAfterBackground(
  lastBeatAt: number,
  now: number,
  expectedMs: number = HEARTBEAT_MS,
): boolean {
  return now - lastBeatAt > expectedMs + RESUME_GAP_MS - HEARTBEAT_MS;
}
