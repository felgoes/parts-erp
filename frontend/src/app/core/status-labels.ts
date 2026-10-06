const labels: Record<string, string> = {
  // Pedido e pagamento
  confirmed: 'Confirmado',
  payment_required: 'Pagamento pendente',
  payment_in_process: 'Pagamento em análise',
  paid: 'Pago',
  partially_refunded: 'Parcialmente reembolsado',
  refunded: 'Reembolsado',
  return_requested: 'Devolução solicitada',
  return_in_progress: 'Devolução em andamento',
  return_completed: 'Devolução concluída',
  claim_opened: 'Reclamação aberta',
  claim_closed: 'Reclamação encerrada',
  cancellation_requested: 'Cancelamento solicitado',
  requested: 'Solicitado',
  in_process: 'Em andamento',
  resolved: 'Resolvido',
  partially_received: 'Recebimento parcial',
  inspection_pending: 'Aguardando inspeção',
  mixed: 'Apta e não apta para revenda',
  damaged: 'Danificada',
  discarded: 'Descartada',
  resolved_without_stock: 'Encerrado sem retorno ao estoque',
  closed: 'Encerrado',
  cancelled: 'Cancelado',
  canceled: 'Cancelado',
  invalid: 'Inválido',
  fulfilled: 'Concluído',
  // Envio
  pending: 'Pendente',
  handling: 'Em preparação',
  ready_to_ship: 'Pronto para envio',
  shipped: 'Despachado',
  delivered: 'Entregue · finalizado',
  not_delivered: 'Não entregue',
  delivery_failed: 'Falha na entrega',
  not_received: 'Não recebido',
  returned: 'Devolvido',
  returning_to_sender: 'Em devolução ao remetente',
  returned_to_sender: 'Devolvido ao remetente',
  waiting_for_withdrawal: 'Aguardando retirada',
  waiting_for_label_generation: 'Aguardando emissão da etiqueta',
  waiting_for_carrier_authorization: 'Aguardando autorização da transportadora',
  waiting_for_documentation: 'Aguardando documentação',
  held_for_documentation: 'Aguardando documentação',
  waiting_for_delivery: 'Aguardando entrega',
  waiting_for_pickup: 'Aguardando coleta',
  waiting_for_shipment: 'Aguardando envio',
  waiting_for_drop_off: 'Aguardando postagem',
  waiting_for_dropoff: 'Aguardando postagem',
  waiting_for_action: 'Aguardando ação',
  at_the_branch: 'Na agência',
  in_hub: 'No centro de distribuição',
  on_route: 'Em rota de entrega',
  in_packing_list: 'Em lista de despacho',
  ready_to_pack: 'Pronto para embalar',
  packed: 'Pedido embalado',
  shipped_to_carrier: 'Enviado à transportadora',
  at_pickup_point: 'Disponível para retirada',
  at_the_pickup_point: 'Disponível para retirada',
  delivery_attempt_failed: 'Tentativa de entrega sem sucesso',
  delivery_attempts_exceeded: 'Limite de tentativas de entrega atingido',
  buyer_missed_delivery_window: 'Prazo de recebimento não atendido',
  shipment_cancelled: 'Envio cancelado',
  shipment_canceled: 'Envio cancelado',
  shipment_delayed: 'Envio atrasado',
  need_review: 'Em revisão',
  reclaimed: 'Envio em análise',
  rescheduled: 'Entrega reagendada',
  rescheduled_delivery: 'Entrega reagendada',
  address_not_found: 'Endereço não localizado',
  incorrect_address: 'Endereço incorreto',
  refused_delivery: 'Entrega recusada',
  refused_by_buyer: 'Entrega recusada pelo comprador',
  package_damaged: 'Pacote danificado',
  package_lost: 'Pacote extraviado',
  package_stolen: 'Pacote roubado',
  delivered_to_neighbor: 'Entregue a um vizinho',
  delivered_to_reception: 'Entregue na portaria',
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
  const normalized = normalizeStatus(value);
  if (labels[normalized]) return labels[normalized];
  // Do not leak new Mercado Livre/carrier enum values in English into the UI.
  // Keep the raw code in the technical payload for diagnostics instead.
  return 'Status não mapeado';
}

export function trackingEventLabel(status: string, detail?: string | null): string {
  const translatedStatus = statusLabel(status);
  const translatedDetail = trackingDetailLabel(detail);
  return translatedDetail ? `${translatedStatus} · ${translatedDetail}` : translatedStatus;
}

function trackingDetailLabel(value: string | null | undefined): string | null {
  if (!value?.trim()) return null;
  const normalized = normalizeStatus(value);
  if (labels[normalized]) return labels[normalized];

  const phrases: Record<string, string> = {
    'delivery attempt was unsuccessful': 'Tentativa de entrega sem sucesso',
    'delivery attempt failed': 'Tentativa de entrega sem sucesso',
    'buyer was not at home': 'Destinatário ausente',
    'recipient was not at home': 'Destinatário ausente',
    'package is delayed': 'Pacote atrasado',
    'package was damaged': 'Pacote danificado',
    'package was lost': 'Pacote extraviado',
    'package was stolen': 'Pacote roubado',
    'returned to sender': 'Devolvido ao remetente',
  };
  const phrase = value.trim().toLowerCase().replace(/[.]/g, ' ').replace(/\s+/g, ' ');
  if (phrases[phrase]) return phrases[phrase];
  // Preserve a readable Portuguese description when the carrier supplies one.
  if (/[áàâãéêíóôõúç]/i.test(value) || /\b(entrega|pacote|destinatário|remetente|agência|coleta|pedido)\b/i.test(value)) {
    return value.trim();
  }
  return null;
}

function normalizeStatus(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[.\s-]+/g, '_')
    .replace(/_+/g, '_');
}
