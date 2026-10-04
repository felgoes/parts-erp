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
  delivery_failed: 'Falha na entrega',
  not_received: 'Não recebido',
  returned: 'Devolvido',
  returning_to_sender: 'Em devolução ao remetente',
  returned_to_sender: 'Devolvido ao remetente',
  waiting_for_withdrawal: 'Aguardando retirada',
  waiting_for_action: 'Aguardando ação',
  at_the_branch: 'Na agência',
  in_hub: 'No centro de distribuição',
  on_route: 'Em rota de entrega',
  in_packing_list: 'Em lista de despacho',
  buffered: 'Aguardando processamento',
  claimed: 'Com reclamação aberta',
  estimated_delivery: 'Entrega estimada',
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
  completed: 'Etapa concluída',
  downloaded: 'Baixada',
  authorized: 'Autorizada',
  requesting: 'Solicitando',
  not_applicable: 'Não aplicável',
  error: 'Requer atenção',
  // Eventos de pagamento, nota e sincronização
  approved: 'Aprovado',
  rejected: 'Recusado',
  pending_payment: 'Pagamento pendente',
  payment_approved: 'Pagamento aprovado',
  payment_rejected: 'Pagamento recusado',
  invoice_pending: 'Nota pendente',
  invoice_ready: 'Nota disponível',
  label_pending: 'Etiqueta pendente',
  label_ready: 'Etiqueta disponível',
  sync_pending: 'Sincronização pendente',
  sync_error: 'Falha na sincronização',
};

export function statusLabel(value: string | null | undefined): string {
  if (!value) return '—';
  const normalized = value.trim().toLowerCase();
  if (labels[normalized]) return labels[normalized];
  return normalized
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function trackingEventLabel(status: string, detail?: string | null): string {
  const translatedStatus = statusLabel(status);
  return detail ? `${translatedStatus} · ${statusLabel(detail)}` : translatedStatus;
}
