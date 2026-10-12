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
