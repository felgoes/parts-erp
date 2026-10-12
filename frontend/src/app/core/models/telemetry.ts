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
