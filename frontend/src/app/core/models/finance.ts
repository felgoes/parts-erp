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
