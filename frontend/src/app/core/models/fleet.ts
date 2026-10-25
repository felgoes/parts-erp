export interface FleetRankRow {
  label: string;
  value: number;
  share_pct: number | null;
}

export type FleetCategory = 'cars' | 'motorcycles';

export interface FleetOverview {
  available: boolean;
  message?: string;
  period: string;
  category: FleetCategory;
  collected_at: string;
  source: string;
  source_url: string;
  periods: string[];
  total: number;
  previous_period: string | null;
  previous_total: number | null;
  change_pct: number | null;
  brand_count: number;
  model_count: number;
  brands: FleetRankRow[];
  nationalities: FleetRankRow[];
  models: Array<{
    brand: string;
    model: string;
    value: number;
    share_pct: number | null;
  }>;
  age_bands: FleetRankRow[];
  years: FleetRankRow[];
  filters: {
    brands: string[];
    nationalities: string[];
    age_bands: string[];
  };
  import_status: {
    status: 'not_started' | 'running' | 'completed' | 'failed';
    period: string | null;
    source_rows: number | null;
    aggregate_count: number | null;
    error: string | null;
  };
}

export interface FleetRecordPage {
  total: number;
  page: number;
  page_size: number;
  period?: string;
  category?: FleetCategory;
  items: Array<{
    brand: string;
    model: string;
    year: number | null;
    age_band: string | null;
    value: number;
    share_pct: number | null;
  }>;
}
