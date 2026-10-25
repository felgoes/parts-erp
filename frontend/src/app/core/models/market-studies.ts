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
  compatibility?: 'oem_exact' | 'catalog' | 'fitment_confirmed' | 'attribute_match' | 'unconfirmed';
  compatibility_label?: string;
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
    site_id?: string;
    schema_version?: string;
    error?: string;
    scope?: {
      mode: 'brand' | 'nationality';
      brand: string | null;
      nationality: string | null;
      region: string;
      vehicle_categories: string[];
    };
    company_snapshot?: Record<string, unknown>;
    company_profile_pending?: {
      needs_company_profile: boolean;
      missing_company_fields: string[];
      completion_url: string;
      message: string;
    } | null;
    executive_summary?: string;
    best_candidate?: MarketStudyCandidate | null;
    candidates?: MarketStudyCandidate[];
    competitor_links?: MarketStudyCompetitorLink[];
    supplier_research?: {
      status: string;
      source: string;
      message: string;
      leads: Record<string, unknown>[];
    } | null;
    market_context?: VehicleMarketOverview;
    tax_rules?: { status: string; message: string };
    partial_result?: boolean;
    source_errors?: string[];
    product_context?: {
      oem?: string | null;
      application?: string | null;
      fitments?: {
        make: string;
        model: string;
        year_from?: number | null;
        year_to?: number | null;
        engine?: string | null;
        version?: string | null;
      }[];
    };
    market_metrics: {
      offers_found: number;
      consulted_limit?: number;
      comparable_offers: number;
      sample_confidence?: 'low' | 'medium' | 'high';
      conclusion?: string;
      conclusion_reason?: string;
      small_sample?: boolean;
      median_price: string | null;
      min_price: string | null;
      max_price: string | null;
      sold_units_lifetime_in_comparables: number;
      trend_keyword_matches: number;
    };
    price_scenario: {
      landed_cost: string | null;
      cost_post?: string | null;
      marketplace_fee_pct: string;
      target_margin_pct: string;
      break_even_price: string | null;
      target_price: string | null;
      commission_pct?: string;
      fixed_fee?: string | null;
      outbound_shipping?: string | null;
      cost_known?: boolean;
      inbound_shipping_known?: boolean;
      inbound_shipping?: string | null;
      calculation_components?: string[];
      unknown_components: string[];
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
    ai_report?: null | {
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

export interface MarketStudySummary {
  id: string;
  mode: string;
  selection: string;
  nationality: string | null;
  brand: string | null;
  conclusion: string;
  best_candidate: string | null;
  decision: string | null;
  score: number | null;
  confidence: string | null;
  estimated_margin_pct: string | null;
  status: string;
  created_at: string;
}

export interface MarketStudyList {
  total: number;
  items: MarketStudySummary[];
}

export interface MarketStudyCandidate {
  candidate_id: string;
  part_family: string;
  product_name: string;
  sku: string;
  oem: string | null;
  models: Array<{
    brand: string | null;
    model: string | null;
    year_from: number | null;
    year_to: number | null;
  }>;
  addressable_fleet: number | null;
  offers_comparable: number;
  market_price: { median: string | null; min: string | null; max: string | null };
  unit_economics: {
    known_cost: string | null;
    partial_contribution_margin_pct: string | null;
    target_margin_pct: string | null;
    components_known: string[];
    components_unknown: string[];
    partial: boolean;
  };
  facts: string[];
  hypotheses: string[];
  limitations: string[];
  risks: string[];
  score: number;
  confidence: 'low' | 'medium' | 'high';
  decision: string;
  decision_ceiling: string;
  blocking_gate: string;
  next_validation: {
    action: string;
    success_criteria: string;
    stop_criteria: string;
  };
  ai_explanation?: {
    why: string;
    facts: string[];
    hypotheses: string[];
    missing_data: string[];
    risks: string[];
  };
}

export interface MarketStudyCompetitorLink {
  offer_id: string;
  title: string;
  url: string;
  seller_url: string | null;
  observed_price: string;
  observed_at: string;
  compatibility: string;
}

export interface VehicleMarketOverview {
  scope: Record<string, string | null>;
  monthly: VehicleMarketRanking;
  ytd: VehicleMarketRanking;
  trend: Array<{ period: string; value: number }>;
  comparisons: {
    previous_period: { period: string; total: number } | null;
    year_ago: { period: string; total: number } | null;
  };
  fleet: VehicleMarketRanking;
  sources: Array<{
    available: boolean;
    source: string | null;
    metric: string | null;
    period: string | null;
    source_url: string | null;
    retrieved_at: string | null;
    published_at: string | null;
    status: string;
  }>;
  brand_nationalities: Record<string, string>;
  available_brands?: string[];
  catalog_status?: string;
  selected_brand?: {
    brand: string;
    found: boolean;
    in_top_20: boolean;
    models: string[];
    families: Array<{ name: string; versions: number }>;
    status: string;
    retrieved_at: string | null;
  };
  live_sync?: {
    status: 'updated' | 'cached' | 'updating' | 'unavailable';
    period: string | null;
    retrieved_at: string | null;
    message?: string;
  };
  fleet_publication?: {
    status: 'available' | 'unavailable';
    dataset_url: string;
    resource_url: string | null;
    period: string | null;
    published_at: string | null;
    format: string | null;
    source: string;
  };
  fleet_import?: {
    status: 'running' | 'completed' | 'failed';
    period: string;
    source_rows: number | null;
    aggregate_count: number | null;
    total_vehicles: number | null;
    error: string | null;
    started_at: string;
    completed_at: string | null;
  } | null;
  definitions: { registrations: string; fleet: string };
}

export interface VehicleMarketRanking {
  period: string | null;
  total: number | null;
  nationalities: VehicleMarketRankRow[];
  brands: VehicleMarketRankRow[];
  models: VehicleMarketRankRow[];
  age_bands?: VehicleMarketRankRow[];
}

export interface VehicleMarketRankRow {
  label: string;
  value: number;
  share_pct: number | null;
}
