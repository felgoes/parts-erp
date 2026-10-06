import { describe, expect, it } from 'vitest';
import { shippingStatusLabel, statusLabel, trackingEventLabel } from './status-labels';

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
  it.each(['dropped_off', 'in_hub', 'picked_up', 'shipped_to_carrier'])(
    'shows ready_to_ship as dispatched after substatus %s',
    (substatus) => {
      expect(shippingStatusLabel('ready_to_ship', substatus)).toBe('Despachado');
      expect(trackingEventLabel('ready_to_ship', substatus)).toContain('Despachado');
    },
  );
  it('uses the latest shipment event in invoice summaries', () => {
    const history = [{ status: 'ready_to_ship', detail: 'in_hub', created_at: '2026-10-06T11:36:00-03:00' }];
    expect(shippingStatusLabel('ready_to_ship', null, history)).toBe('Despachado');
  });
});
