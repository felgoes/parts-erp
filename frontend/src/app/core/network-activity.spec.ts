import { describe, expect, it } from 'vitest';
import { NetworkActivityService } from './network-activity.service';

describe('atividade de rede', () => {
  it('marca o último contato quando o servidor responde', () => {
    const activity = new NetworkActivityService();

    activity.started();
    activity.settled(200);

    expect(activity.busy()).toBe(false);
    expect(activity.unreachable()).toBe(false);
    expect(activity.lastSuccessAt()).toBeTypeOf('number');
  });

  it('trata sem-resposta e servidor fora do ar como inalcançável', () => {
    const activity = new NetworkActivityService();

    for (const status of [0, 502, 503, 504]) {
      activity.started();
      activity.settled(status);
      expect(activity.unreachable()).toBe(true);
    }
  });

  it('erro do próprio servidor não vira aviso de conexão', () => {
    const activity = new NetworkActivityService();

    activity.started();
    activity.settled(500);

    expect(activity.unreachable()).toBe(false);
    expect(activity.lastSuccessAt()).toBeNull();
  });

  it('continua ocupado enquanto houver chamada em andamento', () => {
    const activity = new NetworkActivityService();

    activity.started();
    activity.started();
    activity.settled(200);
    expect(activity.busy()).toBe(true);

    activity.settled(200);
    expect(activity.busy()).toBe(false);
  });
});
