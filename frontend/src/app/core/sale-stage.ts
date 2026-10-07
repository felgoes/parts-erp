import { Invoice, MarketplaceOrder } from './models';

export type SaleStageCode =
  | 'received'
  | 'payment_pending'
  | 'awaiting_invoice'
  | 'awaiting_label'
  | 'ready_to_ship'
  | 'dispatched'
  | 'in_transit'
  | 'finalized'
  | 'returned'
  | 'cancelled'
  | 'invoice_error'
  | 'label_error';

const labels: Record<SaleStageCode, string> = {
  received: 'Pedido recebido',
  payment_pending: 'Pagamento pendente',
  awaiting_invoice: 'Aguardando NF',
  awaiting_label: 'Aguardando etiqueta',
  ready_to_ship: 'Pronto para envio',
  dispatched: 'Despachado',
  in_transit: 'Em trânsito',
  finalized: 'Finalizado',
  returned: 'Devolvido',
  cancelled: 'Cancelado',
  invoice_error: 'Falha na NF',
  label_error: 'Falha na etiqueta',
};

export function saleStageLabel(value: SaleStageCode): string {
  return labels[value];
}

export function saleStageForOrder(order: MarketplaceOrder): SaleStageCode {
  const status = String(order.status || '').toLowerCase();
  const shipping = String(order.shipping_status || '').toLowerCase();
  const label = String(order.label_status || '').toLowerCase();
  const fiscal = String(order.fiscal_status || '').toLowerCase();
  if (['cancelled', 'canceled', 'in_cancel'].includes(status)) return 'cancelled';
  if (['unpaid', 'pending', 'payment_required', 'payment_pending'].includes(status)) return 'payment_pending';
  if (['returned', 'returning_to_sender', 'returned_to_sender'].includes(shipping)) return 'returned';
  if (shipping === 'delivered') return 'finalized';
  if (['shipped', 'shipped_to_carrier', 'dropped_off'].includes(shipping)) return 'dispatched';
  if (['in_transit', 'in_hub', 'on_route', 'out_for_delivery'].includes(shipping)) return 'in_transit';
  if (shipping === 'ready_to_ship' || ['downloaded', 'completed'].includes(label)) return 'ready_to_ship';
  if (fiscal === 'error') return 'invoice_error';
  if (label === 'error') return 'label_error';
  if (fiscal !== 'authorized' && fiscal !== 'not_applicable') return 'awaiting_invoice';
  if (label !== 'downloaded' && label !== 'completed' && label !== 'not_applicable') return 'awaiting_label';
  if (['paid', 'confirmed', 'approved'].includes(status) || order.invoice_id) return 'ready_to_ship';
  return 'payment_pending';
}

export function saleStageForInvoice(invoice: Invoice): SaleStageCode {
  if (invoice.status === 'cancelled') return 'cancelled';
  if (invoice.after_sale?.kind === 'return') return 'returned';
  const shipping = String(invoice.tracking?.shipping_status || '').toLowerCase();
  if (shipping === 'delivered') return 'finalized';
  if (['shipped', 'shipped_to_carrier', 'dropped_off'].includes(shipping)) return 'dispatched';
  if (['in_transit', 'in_hub', 'on_route', 'out_for_delivery'].includes(shipping)) return 'in_transit';
  if (shipping === 'ready_to_ship') return 'ready_to_ship';
  if (invoice.source !== 'manual') return invoice.documents.length ? 'awaiting_label' : 'awaiting_invoice';
  if (invoice.status === 'draft') return 'received';
  return 'finalized';
}
