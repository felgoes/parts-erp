export interface InvoiceItem {
  id: string;
  product_id: string;
  sku: string;
  description: string;
  quantity: number;
  unit_price: number;
  total: number;
}
export interface InvoiceDocument {
  id: string;
  document_type: string;
  filename: string;
  created_at: string;
}
export interface Invoice {
  id: string;
  number: string;
  customer_id: string | null;
  status: 'draft' | 'confirmed' | 'cancelled';
  source: 'manual' | 'mercadolivre' | 'shopee';
  marketplace_order_id: string | null;
  subtotal: number;
  discount: number;
  shipping: number;
  total: number;
  issued_at: string | null;
  notes: string | null;
  created_at: string;
  items: InvoiceItem[];
  documents: InvoiceDocument[];
  tracking?: InvoiceTracking | null;
  after_sale?: InvoiceAfterSale | null;
  customer?: InvoiceCustomer | null;
}
export interface InvoiceAfterSale {
  kind: 'return' | 'claim' | 'cancellation' | string;
  status: string;
  reason: string | null;
  requested_by: string | null;
  return_id: string | null;
  payment_status: string | null;
  refund_amount: number | null;
  requested_at: string | null;
  history: InvoiceTrackingEvent[];
  cases: AfterSaleCase[];
}
export interface AfterSaleCase {
  id: string;
  provider: string;
  external_case_id: string;
  marketplace_order_id: string;
  invoice_id: string | null;
  kind: string;
  workflow_status: string;
  marketplace_status: string;
  reason: string | null;
  requested_by: string | null;
  payment_status: string | null;
  refund_amount: number | null;
  requested_at: string | null;
  completed_at: string | null;
  notes: string | null;
  items: AfterSaleCaseItem[];
  events: AfterSaleCaseEvent[];
}
export interface AfterSaleCaseItem {
  id: string;
  invoice_item_id: string | null;
  product_id: string;
  sku: string;
  description: string;
  requested_quantity: number;
  received_quantity: number;
  inspected_quantity: number;
  restocked_quantity: number;
  disposition: string;
  notes: string | null;
}
export interface AfterSaleCaseEvent {
  event_type: string;
  status: string;
  detail: string | null;
  created_at: string;
}
export interface InvoiceCustomer {
  name: string;
  document: string | null;
  email: string | null;
  phone: string | null;
}
export interface InvoiceTrackingEvent {
  status: string;
  detail: string | null;
  created_at: string;
}
export interface InvoiceTracking {
  shipment_id: string | null;
  status: string | null;
  shipping_status: string | null;
  shipping_substatus: string | null;
  label_status: string | null;
  last_update: string | null;
  last_update_source: 'platform' | 'erp';
  history: InvoiceTrackingEvent[];
}
