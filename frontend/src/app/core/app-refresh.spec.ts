import { describe, expect, it } from 'vitest';
import {
  HEARTBEAT_MS,
  PULL_TRIGGER_PX,
  isAndroidApp,
  pullBandHeight,
  pullOffset,
  pullProgress,
  resumedAfterBackground,
  shouldRefresh,
} from './app-refresh';

describe('puxar para atualizar', () => {
  it('só considera o gesto com a tela no topo', () => {
    expect(pullOffset(100, 180, 0)).toBe(80);
    expect(pullOffset(100, 180, 12)).toBe(0);
  });

  it('ignora o gesto para cima, que é rolagem', () => {
    expect(pullOffset(180, 100, 0)).toBe(0);
  });

  it('acompanha o dedo até o limite da faixa', () => {
    expect(pullProgress(0)).toBe(0);
    expect(pullProgress(PULL_TRIGGER_PX / 2)).toBeCloseTo(0.5);
    expect(pullProgress(PULL_TRIGGER_PX)).toBe(1);
    expect(pullProgress(400)).toBe(1);
    expect(pullBandHeight(400)).toBe(108);
  });

  it('só dispara a recarga quando passa do ponto', () => {
    expect(shouldRefresh(PULL_TRIGGER_PX - 1)).toBe(false);
    expect(shouldRefresh(PULL_TRIGGER_PX)).toBe(true);
  });

  it('vale só no aplicativo Android', () => {
    expect(isAndroidApp(true, 'android')).toBe(true);
    expect(isAndroidApp(true, 'ios')).toBe(false);
    expect(isAndroidApp(false, 'android')).toBe(false);
    expect(isAndroidApp(false, 'web')).toBe(false);
  });
});

describe('retomada do aplicativo', () => {
  it('reconhece a pausa longa do relógio como volta do segundo plano', () => {
    const agora = 1_800_000_000_000;

    expect(resumedAfterBackground(agora - HEARTBEAT_MS, agora)).toBe(false);
    expect(resumedAfterBackground(agora - HEARTBEAT_MS - 3_000, agora)).toBe(false);
    expect(resumedAfterBackground(agora - 60_000, agora)).toBe(true);
  });
});
