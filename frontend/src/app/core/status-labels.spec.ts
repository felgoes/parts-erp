import { describe, expect, it } from 'vitest';
import { statusLabel, trackingEventLabel } from './status-labels';

describe('Mercado Livre status labels', () => {
  it.each([
    ['ready_to_ship', 'Pronto para envio'],
    ['out-for-delivery', 'Saiu para entrega'],
    ['delivery_attempt_failed', 'Tentativa de entrega sem sucesso'],
    ['waiting.for.label.generation', 'Aguardando emissão da etiqueta'],
  ])('translates %s', (value, expected) => {
    expect(statusLabel(value)).toBe(expected);
  });

  it('does not expose an untranslated unknown enum', () => {
    expect(statusLabel('carrier_new_state')).toBe('Status não mapeado');
  });

  it('translates known tracking details and omits unknown technical text', () => {
    expect(trackingEventLabel('shipped', 'out_for_delivery')).toBe('Em trânsito · Saiu para entrega');
    expect(trackingEventLabel('delivered', 'A new carrier detail')).toBe('Entregue');
  });
});
