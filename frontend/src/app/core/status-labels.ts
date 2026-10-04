const labels: Record<string, string> = {
  // Pedido e pagamento
  confirmed: 'Confirmado',
  payment_required: 'Pagamento pendente',
  payment_in_process: 'Pagamento em análise',
  paid: 'Pago',
  partially_refunded: 'Parcialmente reembolsado',
  refunded: 'Reembolsado',
  cancelled: 'Cancelado',
  canceled: 'Cancelado',
  invalid: 'Inválido',
  fulfilled: 'Concluído',
  // Envio
  pending: 'Pendente',
  handling: 'Em preparação',
  ready_to_ship: 'Pronto para envio',
  shipped: 'Em trânsito',
  delivered: 'Entregue',
  not_delivered: 'Não entregue',
  returned: 'Devolvido',
  not_verified: 'Aguardando validação',
  unknown: 'Não informado',
  // Substatus comuns do Mercado Envios
  ready_to_print: 'Pronto para imprimir',
  printed: 'Etiqueta impressa',
  picked_up: 'Coletado',
  in_transit: 'Em trânsito',
  out_for_delivery: 'Saiu para entrega',
  receiver_absent: 'Destinatário ausente',
  delayed: 'Atrasado',
  lost: 'Extraviado',
  damaged: 'Danificado',
  stolen: 'Roubado',
  waiting: 'Aguardando',
  waiting_shipment: 'Aguardando envio',
  downloaded: 'Baixada',
  authorized: 'Autorizada',
  requesting: 'Solicitando',
  not_applicable: 'Não aplicável',
  error: 'Requer atenção',
};

export function statusLabel(value: string | null | undefined): string {
  if (!value) return '—';
  return labels[value.toLowerCase()] ?? value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function trackingEventLabel(status: string, detail?: string | null): string {
  const translatedStatus = statusLabel(status);
  return detail ? `${translatedStatus} · ${statusLabel(detail)}` : translatedStatus;
}
