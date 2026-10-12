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
  stock_type: 'product' | 'warehouse';
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
  attributes: {
    id: string;
    name: string;
    required: boolean;
    new_required?: boolean;
    conditional_required?: boolean;
    value_type: string;
    values: { id?: string; name?: string; value_id?: string; original_value_name?: string }[];
    max_length?: number;
  }[];
  sale_terms: {
    id: string;
    name: string;
    value_type: string;
    values?: { id: string; name: string }[];
    allowed_units?: { id: string; name: string }[];
  }[];
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
