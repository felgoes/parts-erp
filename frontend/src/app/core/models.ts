export interface User {
  id: string;
  email: string;
  full_name: string;
  role: 'admin' | 'manager' | 'operator';
}
export interface AuthToken {
  access_token: string;
  token_type: string;
  user: User;
}
export interface Product {
  id: string;
  sku: string;
  name: string;
  description: string | null;
  sale_price: number;
  cost_price: number;
  current_stock: number;
  minimum_stock: number;
  active: boolean;
  created_at: string;
  updated_at: string;
}
export interface Customer {
  id: string;
  name: string;
  document: string | null;
  email: string | null;
  phone: string | null;
  created_at: string;
}
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
}
export interface DashboardSummary {
  revenue_month: number;
  confirmed_sales: number;
  products_count: number;
  low_stock_count: number;
  recent_invoices: Invoice[];
}
export interface MarketplaceStatus {
  configured: boolean;
  connected: boolean;
  seller_id: string | null;
  nickname: string | null;
  token_expires_at: string | null;
}
export interface MarketplaceConfig {
  client_id: string;
  client_secret_configured: boolean;
  redirect_uri: string;
  site_id: string;
  import_orders: boolean;
  automatic_stock: boolean;
  sync_documents: boolean;
}
export interface MarketplaceOrder {
  id: string;
  external_order_id: string;
  seller_id: string;
  status: string;
  sync_status: string;
  sync_error: string | null;
  invoice_id: string | null;
  synchronized_at: string | null;
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

export interface CatalogProduct {
  id: string;
  sku: string;
  name: string;
  description: string | null;
  sale_price: number;
  in_stock: boolean;
}

export interface TelemetryEventCount {
  name: string;
  count: number;
}
export interface TelemetryHealth {
  check_name: string;
  ok: boolean;
  latency_ms: number;
  detail: string | null;
  checked_at: string;
}
export interface TelemetrySummary {
  days: number;
  events: TelemetryEventCount[];
  health: TelemetryHealth[];
}
