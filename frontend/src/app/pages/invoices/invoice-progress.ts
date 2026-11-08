import type { Invoice } from '../../core/models/invoices';
import { saleStageForInvoice, saleStageLabel } from '../../core/sale-stage';
import { statusLabel } from '../../core/status-labels';

const dispatched = new Set([
  'shipped', 'authorized_by_carrier', 'picked_up', 'shipped_to_carrier', 'dropped_off',
]);
const inTransit = new Set(['in_transit', 'in_hub', 'on_route', 'out_for_delivery', 'at_the_branch']);
const delivered = new Set(['delivered', 'delivered_to_neighbor', 'delivered_to_reception']);
const shippingIssues = new Set([
  'not_delivered', 'delivery_failed', 'delivery_attempt_failed', 'delivery_attempts_exceeded',
  'receiver_absent', 'address_not_found', 'incorrect_address', 'refused_delivery', 'refused_by_buyer',
  'package_lost', 'package_damaged', 'package_stolen', 'lost', 'stolen', 'delayed', 'shipment_delayed',
  'shipment_cancelled', 'shipment_canceled', 'returned', 'returning_to_sender', 'returned_to_sender',
]);

const code = (value: string | null | undefined) => value?.trim().toLowerCase() || '';

function firstEvent(
  history: NonNullable<Invoice['tracking']>['history'],
  codes: ReadonlySet<string>,
): string | null {
  let first: string | null = null;
  for (const event of history) {
    if (!codes.has(code(event.status)) && !codes.has(code(event.detail))) continue;
    if (!first || event.created_at < first) first = event.created_at;
  }
  return first;
}

export function invoiceProgress(sale: Invoice) {
  const tracking = sale.tracking;
  const history = tracking?.history || [];
  const stage = saleStageForInvoice(sale);
  const rawStatus = code(tracking?.shipping_status);
  const rawDetail = code(tracking?.shipping_substatus);
  const deliveredAt = firstEvent(history, delivered);
  const dispatchedAt = firstEvent(history, dispatched);
  const isDelivered = !!deliveredAt || delivered.has(rawStatus) || delivered.has(rawDetail);
  const isDispatched = isDelivered || !!dispatchedAt || !!firstEvent(history, inTransit)
    || stage === 'dispatched' || stage === 'in_transit';
  const issueCode = [rawDetail, rawStatus].find((value) => shippingIssues.has(value));
  const issue = sale.status === 'cancelled' ? 'Venda cancelada'
    : sale.after_sale?.kind === 'return' ? 'Devolução'
    : sale.after_sale?.kind === 'claim' ? 'Reclamação'
    : sale.after_sale?.kind === 'cancellation' ? 'Cancelamento'
    : issueCode ? statusLabel(issueCode) : null;

  const label = issue || (sale.source === 'manual'
    ? sale.status === 'draft' ? 'Rascunho' : 'Venda confirmada'
    : isDelivered ? 'Entregue' : saleStageLabel(stage));

  return {
    stage,
    label,
    issue,
    canTrack: !!tracking && !isDelivered && sale.status !== 'cancelled'
      && (isDispatched || !!issueCode),
    steps: [
      { label: 'Venda registrada', date: sale.created_at, done: true },
      { label: 'Despachado', date: dispatchedAt, done: isDispatched },
      { label: 'Entregue', date: deliveredAt, done: isDelivered },
    ],
    currentStep: issue ? -1 : isDelivered ? 2 : isDispatched ? 1 : 0,
  };
}
