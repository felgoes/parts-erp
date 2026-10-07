export interface User {
  id: string;
  email: string;
  full_name: string;
  role: 'admin' | 'manager' | 'operator' | 'stock' | 'finance' | 'viewer';
  active: boolean;
}
export interface ErpSettings {
  company_name: string;
  company_short_name: string;
  logo_data_url: string | null;
  backup_enabled: boolean;
  backup_frequency: 'daily' | 'weekly';
  backup_time: string;
  backup_retention_days: number;
  backup_destination: 'google_drive';
  backup_ready: boolean;
  backup_status: 'setup_required' | 'ready';
  drive_client_id: string | null;
  drive_client_secret_configured: boolean;
  drive_folder_id: string | null;
  drive_connected: boolean;
  backup_last_at: string | null;
  backup_last_status: string;
  backup_last_error: string | null;
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
  brand: string | null;
  manufacturer: string | null;
  manufacturer_part_number: string | null;
  barcode: string | null;
  category: string | null;
  item_condition: 'new' | 'used' | 'refurbished';
  warranty_days: number | null;
  origin_country: string | null;
  weight_g: number | null;
  package_length_cm: number | null;
  package_width_cm: number | null;
  package_height_cm: number | null;
  attributes: Record<string, string>;
  fitments: ProductFitment[];
  images: ProductImage[];
  sale_price: number;
  cost_price: number | null;
  current_stock: number;
  minimum_stock: number;
  active: boolean;
  created_at: string;
  updated_at: string;
}
export interface ProductImage {
  id: string;
  filename: string;
  url: string;
  position: number;
  width: number;
  height: number;
  uploaded_at: string;
}
export interface ProductFitment {
  make: string;
  model: string;
  year_from?: number | null;
  year_to?: number | null;
  engine?: string | null;
  version?: string | null;
  notes?: string | null;
}
export interface ProductListing {
  id: string;
  provider: string;
  external_item_id: string | null;
  title: string | null;
  permalink: string | null;
  thumbnail: string | null;
  images: string[];
  marketplace_price: number | null;
  available_quantity: number | null;
  sold_quantity: number | null;
  visits: number | null;
  status: string | null;
  sync_status: 'draft' | 'published' | 'partial' | 'blocked' | 'error' | 'imported';
  sync_error: string | null;
  category_id: string | null;
  channel_data: ProductChannelDraft;
  synchronized_at: string | null;
}
export interface ProductChannelDraft {
  category_id: string;
  title?: string | null;
  family_name?: string | null;
  description?: string | null;
  price?: number | null;
  listing_type_id?: string | null;
  item_condition?: 'new' | 'used' | 'refurbished' | null;
  attributes: { id: string; value_id?: string; value_name?: string }[];
  sale_terms: Record<string, unknown>[];
  shipping: Record<string, unknown>;
  logistic_info: Record<string, unknown>[];
}
export interface ProductChannelMetadata {
  provider: 'mercadolivre' | 'shopee';
  connected: boolean;
  user_product_seller: boolean;
  categories: { id: string; name: string; domain_id?: string | null; path?: unknown[] }[];
  attributes: { id: string; name: string; required: boolean; new_required?: boolean; conditional_required?: boolean; value_type: string; values: { id?: string; name?: string; value_id?: string; original_value_name?: string }[]; max_length?: number }[];
  sale_terms: { id: string; name: string; value_type: string; values?: { id: string; name: string }[]; allowed_units?: { id: string; name: string }[] }[];
  listing_types: { id: string; name: string; listing_exposure?: string }[];
  logistics: { id: number; name: string }[];
  limits: { max_pictures?: number; max_title_length?: number; category_name?: string };
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
  unit_cost: number | null;
  movement_value: number | null;
  reason: string;
  reference: string | null;
  created_at: string;
}
export interface FinanceProductMetric {
  product_id: string;
  sku: string;
  name: string;
  current_stock: number;
  average_cost: number;
  inventory_value: number;
  inbound_quantity: number;
  inbound_value: number;
  outbound_quantity: number;
  outbound_value: number;
  return_quantity: number;
  return_value: number;
  net_cost_of_goods: number;
}
export interface FinanceDailyMetric {
  date: string;
  label: string;
  inbound_value: number;
  outbound_value: number;
  return_value: number;
  revenue: number;
}
export interface FinanceOverview {
  period_label: string;
  inventory_units: number;
  inventory_value: number;
  inbound_quantity: number;
  inbound_value: number;
  outbound_quantity: number;
  outbound_value: number;
  return_quantity: number;
  return_value: number;
  net_cost_of_goods: number;
  revenue: number;
  gross_margin: number | null;
  gross_margin_percent: number | null;
  known_movements: number;
  unknown_cost_movements: number;
  unvalued_sales_items: number;
  by_product: FinanceProductMetric[];
  daily: FinanceDailyMetric[];
}
export type PurchaseStatus = 'negotiating' | 'approved' | 'ordered' | 'partially_received' | 'received' | 'cancelled';
export interface PurchaseItem {
  id: string;
  product_id: string | null;
  sku: string;
  description: string;
  quantity: number;
  received_quantity: number;
  base_unit_cost: number | null;
  unit_cost: number | null;
  freight_amount: number | null;
  tax_amount: number | null;
  discount_amount: number | null;
}
export interface PurchaseQuote {
  id: string;
  supplier_name: string;
  supplier_contact: string | null;
  total: number | null;
  freight_amount: number;
  tax_amount: number;
  discount_amount: number;
  allocation_method: 'proportional' | 'quantity';
  item_costs: Record<string, number> | null;
  delivery_days: number | null;
  payment_terms: string | null;
  notes: string | null;
  created_at: string;
}
export interface PurchaseEvent {
  id: string;
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
  supplier_name: string | null;
  selected_quote_id: string | null;
  needed_by: string | null;
  ordered_at: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
  items: PurchaseItem[];
  quotes: PurchaseQuote[];
  events: PurchaseEvent[];
  attachments: PurchaseAttachment[];
}
export interface PurchaseAttachment {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
}
export interface MarketStudyConnector {
  provider: 'openai_responses' | 'openai_compatible';
  model: string;
  base_url: string | null;
  enabled: boolean;
  configured: boolean;
  has_api_key: boolean;
}
export interface MarketStudyOffer {
  id: string;
  title: string;
  price: string;
  available_quantity_reference: number | null;
  sold_quantity_lifetime: number | null;
  seller_id: string | null;
  permalink: string | null;
  thumbnail: string | null;
  similarity: number;
}
export interface MarketStudy {
  id: string;
  created_by_id: string;
  search_term: string;
  sku: string | null;
  category_id: string | null;
  landed_cost: number;
  target_margin_pct: number;
  marketplace_fee_pct: number;
  shipping_cost: number;
  status: string;
  provider_used: string | null;
  result: {
    observed_at: string;
    site_id: string;
    market_metrics: {
      offers_found: number;
      comparable_offers: number;
      median_price: string | null;
      min_price: string | null;
      max_price: string | null;
      sold_units_lifetime_in_comparables: number;
      trend_keyword_matches: number;
    };
    price_scenario: {
      landed_cost: string;
      marketplace_fee_pct: string;
      target_margin_pct: string;
      break_even_price: string | null;
      target_price: string | null;
      market_margin_at_median_pct: string | null;
      competitive_at_target_price: boolean;
    };
    internal_sales: {
      units_last_90_days: number | string;
      units_per_month: number | string;
      stock_units: number | string;
      coverage_months: number | string | null;
    };
    trend_matches: { keyword: string; url: string }[];
    offers: MarketStudyOffer[];
    possible_sources_note: string;
    data_limitations: string[];
    ai_report: null | {
      summary?: string;
      opportunities?: string[];
      risks?: string[];
      next_steps?: string[];
      confidence?: 'low' | 'medium' | 'high';
      error?: string;
    };
  };
  linked_purchase_id: string | null;
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
export interface DashboardSummary {
  revenue_month: number;
  confirmed_sales: number;
  cancelled_sales: number;
  cancelled_amount: number;
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
  cancelled_amount: number;
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

export interface CatalogProduct {
  id: string;
  sku: string;
  name: string;
  description: string | null;
  brand: string | null;
  manufacturer_part_number: string | null;
  barcode: string | null;
  category: string | null;
  attributes: Record<string, string>;
  fitments: ProductFitment[];
  images: ProductImage[];
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
