import { describe, expect, it } from 'vitest';
import type { Invoice, InvoiceTracking, InvoiceTrackingEvent } from '../../core/models/invoices';
import { invoiceProgress } from './invoice-progress';

function sale(tracking: Partial<InvoiceTracking> = {}): Invoice {
  return {
    id: 'sale', number: 'SALE-1', customer_id: null, marketplace_order_id: 'order',
    status: 'confirmed', source: 'mercadolivre', created_at: '2026-11-08T13:00:00Z',
    subtotal: 100, discount: 0, shipping: 0, total: 100, issued_at: null, notes: null,
    items: [], documents: [],
    tracking: {
      shipment_id: 'shipment', destination_address: null, status: 'paid',
      shipping_status: null, shipping_substatus: null, label_status: null,
      last_update: null, last_update_source: 'erp', history: [], ...tracking,
    },
  };
}

function event(status: string, detail: string | null, created_at: string): InvoiceTrackingEvent {
  return { status, detail, created_at };
}

describe('invoice progress', () => {
  it('uses the first dispatch event and keeps delivery pending after a failed attempt', () => {
    const progress = invoiceProgress(sale({
      shipping_status: 'shipped', shipping_substatus: 'delivery_attempt_failed',
      history: [
        event('shipped', 'in_transit', '2026-11-08T18:00:00Z'),
        event('ready_to_ship', 'picked_up', '2026-11-08T16:00:00Z'),
      ],
    }));
    expect(progress.label).toBe('Tentativa de entrega sem sucesso');
    expect(progress.canTrack).toBe(true);
    expect(progress.steps[1]).toMatchObject({ done: true, date: '2026-11-08T16:00:00Z' });
    expect(progress.steps[2]).toMatchObject({ done: false, date: null });
  });

  it('shows delivery from a known status without inventing a timestamp', () => {
    const progress = invoiceProgress(sale({ shipping_status: 'delivered' }));
    expect(progress.label).toBe('Entregue');
    expect(progress.steps.map((step) => step.done)).toEqual([true, true, true]);
    expect(progress.steps[2].date).toBeNull();
  });

  it('does not infer dispatch from a pickup list or from a cancellation', () => {
    const progress = invoiceProgress({
      ...sale({ shipping_status: 'ready_to_ship', shipping_substatus: 'in_pickup_list' }),
      status: 'cancelled',
    });
    expect(progress.label).toBe('Venda cancelada');
    expect(progress.steps.map((step) => step.done)).toEqual([true, false, false]);
  });
});
