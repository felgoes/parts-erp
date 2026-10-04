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
export interface ProductListing {
  id: string;
  provider: string;
  external_item_id: string;
  title: string | null;
  permalink: string | null;
  thumbnail: string | null;
  images: string[];
  marketplace_price: number | null;
  available_quantity: number | null;
  sold_quantity: number | null;
  visits: number | null;
  status: string | null;
  synchronized_at: string | null;
}
export interface ProductDetail extends Product {
  listings: ProductListing[];
}
export interface StockMovement {
  id: string;
  product_id: string;
  movement_type: string;
  quantity: number;
  balance_after: number;
  reason: string;
  reference: string | null;
  created_at: string;
}
export interface Customer {
  id: string;
  name: string;
  document: string | null;
  email: string | null;
  phone: string | null;
  created_at: string;
}
export interface CustomerPurchase {
  id: string;
  number: string;
  status: string;
  source: string;
  marketplace_order_id: string | null;
  total: number;
  issued_at: string | null;
  created_at: string;
  item_count: number;
}
export interface CustomerDetail extends Customer {
  purchase_count: number;
  confirmed_purchase_count: number;
  total_purchased: number;
  average_purchase: number;
  last_purchase_at: string | null;
  marketplace_order_count: number;
  cancelled_order_count: number;
  purchases: CustomerPurchase[];
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
  tracking?: InvoiceTracking | null;
  customer?: InvoiceCustomer | null;
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
  label_status: string | null;
  last_update: string | null;
  history: InvoiceTrackingEvent[];
}
export interface DashboardSummary {
  revenue_month: number;
  confirmed_sales: number;
  products_count: number;
  low_stock_count: number;
  recent_invoices: Invoice[];
}
export interface DashboardBreakdown {
  label: string;
  amount: number;
  count: number;
}
export interface DashboardDailyMetric {
  date: string;
  label: string;
  amount: number;
  count: number;
}
export interface DashboardFinancialMetrics {
  period_label: string;
  revenue: number;
  sales_count: number;
  average_ticket: number;
  previous_revenue: number;
  revenue_change_percent: number;
  cancelled_count: number;
  documents_count: number;
  by_source: DashboardBreakdown[];
  daily: DashboardDailyMetric[];
}
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

export interface CatalogProduct {
  id: string;
  sku: string;
  name: string;
  description: string | null;
  sale_price: number;
  in_stock: boolean;
  listings: CatalogListing[];
}

export interface CatalogListing {
  provider: string;
  external_item_id: string;
  title: string | null;
  permalink: string | null;
  thumbnail: string | null;
  images: string[];
  marketplace_price: number | null;
  available_quantity: number | null;
  sold_quantity: number | null;
  visits: number | null;
  status: string | null;
  attributes: { name: string; value: string }[];
  synchronized_at: string | null;
}

export interface TelemetryEventCount {
  name: string;
  count: number;
}
export interface TelemetryDailyCount {
  date: string;
  events: TelemetryEventCount[];
}
export interface TelemetryProductViews {
  sku: string;
  product_name: string;
  views: number;
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
  daily_events: TelemetryDailyCount[];
  product_views: TelemetryProductViews[];
  health: TelemetryHealth[];
}
