import type { Invoice } from './invoices';

export interface MarketplaceStatus {
  configured: boolean;
  connected: boolean;
  seller_id: string | null;
  nickname: string | null;
  token_expires_at: string | null;
  auto_issue_invoice: boolean;
  auto_download_label: boolean;
}
export interface MarketplaceConfig {
  client_id: string;
  client_secret_configured: boolean;
  redirect_uri: string;
  site_id: string;
  study_default_commission_pct: number;
  import_orders: boolean;
  automatic_stock: boolean;
  sync_documents: boolean;
  auto_issue_invoice: boolean;
  auto_download_label: boolean;
}
export interface MarketplaceOrder {
  id: string;
  external_order_id: string;
  seller_id: string;
  status: string;
  sync_status: string;
  sync_error: string | null;
  invoice_id: string | null;
  shipment_id: string | null;
  shipping_status: string | null;
  shipping_substatus: string | null;
  fiscal_status: string;
  fiscal_error: string | null;
  external_invoice_id: string | null;
  label_status: string;
  label_error: string | null;
  automation_updated_at: string | null;
  synchronized_at: string | null;
  created_at: string;
  provider?: string;
  payload?: Record<string, any> | null;
  invoice?: Invoice | null;
}
export interface MarketplaceOrderEvent {
  id: string;
  order_id: string;
  event_type: string;
  status: string;
  detail: string | null;
  payload: Record<string, any>;
  created_at: string;
}

export interface ShopeeStatus {
  configured: boolean;
  connected: boolean;
  shop_id: string | null;
  token_expires_at: string | null;
}
export interface ShopeeConfig {
  partner_id: string;
  partner_key_configured: boolean;
  shop_id: string | null;
  redirect_uri: string;
  region: string;
  import_orders: boolean;
  automatic_stock: boolean;
  sync_documents: boolean;
}
