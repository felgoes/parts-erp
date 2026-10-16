export type PurchaseStatus =
  | 'negotiating'
  | 'approved'
  | 'ordered'
  | 'partially_received'
  | 'received'
  | 'closed'
  | 'cancelled';
export interface PurchaseItem {
  id: string;
  product_id: string | null;
  sku: string;
  description: string;
  unit: string;
  quantity: number;
  received_quantity: number;
  returned_quantity?: number;
  base_unit_cost: number | null;
  unit_cost: number | null;
  freight_amount: number | null;
  tax_amount: number | null;
  /** P5: taxa de pagamento/processamento rateada nesta peça. */
  extras_amount: number | null;
  discount_amount: number | null;
  discount_percent?: number | null;
}
export interface PurchasePayable {
  id: string;
  supplier_name: string | null;
  amount: number;
  paid_amount?: number;
  due_date: string;
  payment_terms?: string | null;
  installment_count?: number;
  installments?: PayableInstallment[];
  status: 'open' | 'partial' | 'paid' | 'cancelled';
  paid_at: string | null;
  payment_method: string | null;
  payment_notes: string | null;
  cancelled_at: string | null;
  cancel_reason: string | null;
  created_at: string;
}
export type PayableStatus = 'open' | 'partial' | 'paid' | 'cancelled';
export interface PayablePayment {
  id: string;
  amount: number;
  paid_at: string;
  method: string | null;
  notes: string | null;
  reconciled: boolean;
  reconciled_at: string | null;
  reconciled_by_id: string | null;
  created_by_id: string | null;
  created_at: string;
}
export interface PayableListItem {
  id: string;
  purchase_id: string;
  purchase_number: string;
  purchase_type: 'parts' | 'expense';
  purchase_status: string;
  expense_category: string | null;
  /** Título do gasto lançado no tópico (ex.: "Certificado digital A1"). */
  expense_description?: string | null;
  supplier_id: string | null;
  supplier_name: string | null;
  amount: number;
  paid_amount: number;
  balance: number;
  due_date: string;
  payment_terms?: string | null;
  installment_count?: number;
  status: PayableStatus;
  days_overdue: number;
  payment_count: number;
  reconciled_payment_count: number;
  last_payment_at: string | null;
  created_at: string;
}
export interface PayableDetail extends PayableListItem {
  payment_type?: PaymentConditionType;
  first_due_days?: number;
  interval_days?: number;
  payments: PayablePayment[];
  installments: PayableInstallment[];
}
export type PaymentConditionType = 'cash' | 'installments' | 'entry';
export interface PayableInstallment {
  id: string;
  number: number;
  due_date: string;
  amount: number;
  paid_amount: number;
  balance: number;
}
export interface PayableAgingBucket {
  label: string;
  count: number;
  balance: number;
}
export interface PayableSummary {
  open_balance: number;
  overdue_balance: number;
  due_next_days_balance: number;
  paid_in_period: number;
  open_count: number;
  overdue_count: number;
  partial_count: number;
  paid_count: number;
  unreconciled_payments: number;
}
export interface PayableListResponse {
  items: PayableListItem[];
  summary: PayableSummary;
  aging: PayableAgingBucket[];
  next_days: number;
}
export interface PayableReport {
  period_label: string;
  start_date: string;
  end_date: string;
  summary: PayableSummary;
  aging: PayableAgingBucket[];
  by_supplier: Array<{
    supplier_name: string;
    open_balance: number;
    overdue_balance: number;
    paid_in_period: number;
    titles: number;
  }>;
  by_month: Array<{ month: string; paid: number; titles: number }>;
}
export interface PurchaseQuote {
  id: string;
  supplier_name: string;
  supplier_contact: string | null;
  total: number | null;
  freight_amount: number;
  tax_amount: number;
  /** P5: taxa de pagamento/processamento cobrada por fora do valor das peças. */
  extras_amount: number | null;
  discount_amount: number;
  allocation_method: 'proportional' | 'quantity';
  item_costs: Record<string, number> | null;
  delivery_days: number | null;
  payment_type?: PaymentConditionType | null;
  installment_count?: number | null;
  first_due_days?: number | null;
  interval_days?: number | null;
  payment_terms: string | null;
  notes: string | null;
  created_at: string;
}
export interface PurchaseEvent {
  id: string;
  item_id: string | null;
  user_id: string | null;
  event_type: string;
  detail: string;
  created_at: string;
}
export interface Purchase {
  id: string;
  number: string;
  status: PurchaseStatus;
  purchase_type: 'parts' | 'expense';
  expense_category: string | null;
  expense_amount: number | null;
  /** Título do gasto: identifica a despesa na lista e no painel de detalhe. */
  expense_description: string | null;
  supplier_name: string | null;
  supplier_id?: string | null;
  supplier_order_number?: string | null;
  document_date?: string | null;
  selected_quote_id: string | null;
  needed_by: string | null;
  ordered_at: string | null;
  cancel_reason?: string | null;
  cancelled_at?: string | null;
  closed_at?: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
  total_amount?: number | null;
  items: PurchaseItem[];
  quotes: PurchaseQuote[];
  events: PurchaseEvent[];
  attachments: PurchaseAttachment[];
  payables?: PurchasePayable[];
}

/** Linha de item na lista: só o que a lista mostra e usa (o detalhe traz o registro completo). */
export interface PurchaseListRowItem {
  id: string;
  product_id: string | null;
  sku: string;
  description: string;
  unit: string;
  quantity: number;
  received_quantity: number;
}

/** Cotação na lista: fornecedor e total, sem rateio nem condição. */
export interface PurchaseListRowQuote {
  id: string;
  supplier_name: string;
  total: number | null;
}

export interface PurchaseListItem extends Omit<
  Purchase,
  'events' | 'attachments' | 'payables' | 'items' | 'quotes'
> {
  items: PurchaseListRowItem[];
  quotes: PurchaseListRowQuote[];
}

/** Contagens dos cartões, sempre do período escolhido. */
export interface PurchaseListSummary {
  negotiating: number;
  ordered: number;
  received: number;
}

/** Envelope da lista: a página, o total filtrado e o resumo do período. */
export interface PurchaseListOut {
  items: PurchaseListItem[];
  total: number;
  summary: PurchaseListSummary;
  limit: number;
  offset: number;
}

export interface PurchaseAttachment {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
}
