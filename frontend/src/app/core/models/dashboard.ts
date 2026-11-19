import type { Invoice } from './invoices';

export interface DashboardSummary {
  revenue_month: number;
  gross_revenue_month: number;
  marketplace_fee_amount: number;
  marketplace_shipping_amount: number;
  marketplace_costs_pending: number;
  confirmed_sales: number;
  sales_to_ship: number;
  cancelled_sales: number;
  cancelled_amount: number;
  products_count: number;
  low_stock_count: number;
  recent_invoices: Invoice[];
  recent_sales_next_offset?: number | null;
  daily: DashboardDailyMetric[];
}
export interface DashboardSalesPage {
  items: Invoice[];
  next_offset: number | null;
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
  gross_revenue: number;
  marketplace_fee_amount: number;
  marketplace_shipping_amount: number;
  marketplace_costs_pending: number;
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


export interface DashboardMarketplaceMetric {
  value: number | string | null;
  state: 'ok' | 'partial' | 'unavailable';
  note?: string | null;
}
export interface DashboardMarketplaceMetrics {
  connected: boolean;
  start_date: string;
  end_date: string;
  sync_state: 'disconnected' | 'updating' | 'failed' | 'complete' | 'partial';
  partial: boolean;
  last_synced_at: string | null;
  metrics: {
    orders: DashboardMarketplaceMetric;
    units: DashboardMarketplaceMetric;
    gross: DashboardMarketplaceMetric;
    average_ticket: DashboardMarketplaceMetric;
    visits: DashboardMarketplaceMetric;
    conversion: DashboardMarketplaceMetric;
  };
  products_state: 'partial' | 'unavailable' | 'empty' | 'complete';
  products: Array<{
    key: string; rank: number; name: string; sku: string; item_id: string;
    variation_id: string; units: string; pending_link: boolean;
  }>;
}
