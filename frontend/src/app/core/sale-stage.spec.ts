import { describe, expect, it } from 'vitest';
import { Invoice, MarketplaceOrder } from './models';
import { saleStageForInvoice, saleStageForOrder } from './sale-stage';

const progressHistory = [
  { status: 'ready_to_ship', detail: 'dropped_off', created_at: '2026-10-21T16:00:00Z' },
  { status: 'ready_to_ship', detail: 'picked_up', created_at: '2026-10-21T16:30:00Z' },
  { status: 'ready_to_ship', detail: 'in_hub', created_at: '2026-10-21T18:00:00Z' },
  { status: 'ready_to_ship', detail: 'in_packing_list', created_at: '2026-10-21T22:00:00Z' },
];

describe('Mercado Livre shipping stages', () => {
  it('keeps the most advanced historical stage when the current state returns to ready_to_ship', () => {
    const invoice = {
      status: 'confirmed',
      source: 'mercadolivre',
      documents: [],
      tracking: {
        shipping_status: 'ready_to_ship',
        shipping_substatus: 'in_packing_list',
        history: progressHistory,
      },
    } as unknown as Invoice;

    expect(saleStageForInvoice(invoice)).toBe('in_transit');
  });

  it('does not treat a pickup or packing list alone as a completed handoff', () => {
    const invoice = {
      status: 'confirmed',
      source: 'mercadolivre',
      documents: [],
      tracking: {
        shipping_status: 'ready_to_ship',
        shipping_substatus: 'in_packing_list',
        history: [],
      },
    } as unknown as Invoice;
    const order = {
      status: 'paid',
      shipping_status: 'ready_to_ship',
      shipping_substatus: 'in_pickup_list',
      invoice_id: invoice.id,
      fiscal_status: 'authorized',
      label_status: 'downloaded',
      invoice: { tracking: { history: [] } },
    } as unknown as MarketplaceOrder;

    expect(saleStageForInvoice(invoice)).toBe('ready_to_ship');
    expect(saleStageForOrder(order)).toBe('ready_to_ship');
  });
});
