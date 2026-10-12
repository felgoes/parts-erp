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
