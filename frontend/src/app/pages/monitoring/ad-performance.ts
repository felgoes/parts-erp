import { DatePipe, DecimalPipe } from "@angular/common";
import { Component, inject, signal } from "@angular/core";
import { FormsModule } from "@angular/forms";
import { RouterLink } from "@angular/router";
import { forkJoin } from "rxjs";
import { ApiService } from "../../core/api.service";
import { DateRange, quickDateRange } from "../../core/quick-date-ranges";
import { AdPerformanceRow, AdPerformanceSummary } from "../../core/models";
import { PeriodFilter } from "../../shared/period-filter";

@Component({
  selector: "app-ad-performance",
  imports: [DatePipe, DecimalPipe, FormsModule, PeriodFilter, RouterLink],
  templateUrl: "./ad-performance.html",
  styleUrl: "./ad-performance.scss",
})
export class AdPerformance {
  private readonly api = inject(ApiService);
  readonly initial = quickDateRange("last30");
  readonly start = signal(this.initial.startDate);
  readonly end = signal(this.initial.endDate);
  readonly data = signal<AdPerformanceSummary | null>(null);
  readonly loading = signal(false);
  readonly error = signal(false);
  readonly refreshing = signal(false);
  readonly search = signal("");
  readonly channel = signal("all");
  readonly status = signal("all");
  readonly sortBy = signal("visits");
  readonly sortDirection = signal("desc");
  readonly page = signal(1);
  readonly pageSize = signal(25);
  readonly selected = signal<AdPerformanceRow | null>(null);
  readonly exporting = signal(false);
  readonly filtersOpen = signal(false);
  get activeFilterCount() {
    return Number(this.channel() !== "all") + Number(this.status() !== "all") +
      Number(!!this.search().trim()) + Number(this.start() !== this.initial.startDate || this.end() !== this.initial.endDate);
  }
  readonly Math = Math;
  private debounce: ReturnType<typeof setTimeout> | null = null;

  constructor() { this.load(true); }

  applyPeriod(range: DateRange) {
    this.start.set(range.startDate);
    this.end.set(range.endDate);
    this.page.set(1);
    this.load();
  }

  setSearch(value: string) {
    this.search.set(value);
    if (this.debounce) clearTimeout(this.debounce);
    this.debounce = setTimeout(() => { this.page.set(1); this.load(); }, 300);
  }

  private params() {
    return {
      start_date: this.start(), end_date: this.end(),
      channel: this.channel() === "all" ? "" : this.channel(),
      status: this.status() === "all" ? "" : this.status(),
      search: this.search(), page: this.page(), page_size: this.pageSize(),
      sort_by: this.sortBy(), sort_direction: this.sortDirection(),
    };
  }

  load(autoRefresh = false) {
    this.loading.set(true);
    this.error.set(false);
    this.api.adPerformance(this.params()).subscribe({
      next: (value) => {
        this.data.set(value);
        this.loading.set(false);
        if (autoRefresh && value.connected) this.refresh();
      },
      error: () => { this.error.set(true); this.loading.set(false); },
    });
  }

  refresh() {
    const baseline = this.data()?.last_synced_at ?? null;
    this.refreshing.set(true);
    this.api.refreshAdPerformance().subscribe({
      next: () => this.pollForFreshData(baseline, 0),
      error: () => { this.refreshing.set(false); this.error.set(true); },
    });
  }

  private pollForFreshData(baseline: string | null, attempt: number) {
    if (attempt >= 18) {
      this.refreshing.set(false);
      this.load();
      return;
    }
    setTimeout(() => this.api.adPerformance(this.params()).subscribe({
      next: (value) => {
        this.data.set(value);
        if (value.last_synced_at && value.last_synced_at !== baseline) this.refreshing.set(false);
        else this.pollForFreshData(baseline, attempt + 1);
      },
      error: () => this.pollForFreshData(baseline, attempt + 1),
    }), 5000);
  }

  setChannel(value: string) { this.channel.set(value); this.page.set(1); this.load(); }
  setStatus(value: string) { this.status.set(value); this.page.set(1); this.load(); }
  setPageSize(value: string) { this.pageSize.set(Number(value)); this.page.set(1); this.load(); }
  setSort(value: string) { this.sortBy.set(value); this.page.set(1); this.load(); }
  toggleSortDirection() { this.sortDirection.update((value) => value === "desc" ? "asc" : "desc"); this.page.set(1); this.load(); }
  movePage(delta: number) {
    const max = Math.max(1, Math.ceil((this.data()?.total_ads ?? 0) / this.pageSize()));
    this.page.set(Math.min(max, Math.max(1, this.page() + delta)));
    this.load();
  }
  get pageCount() { return Math.max(1, Math.ceil((this.data()?.total_ads ?? 0) / this.pageSize())); }
  localDate(value: string) {
    const [year, month, day] = value.split("-").map(Number);
    return new Date(year, month - 1, day, 12);
  }
  hasDailyVisits() { return (this.data()?.daily ?? []).some((row) => row.visits !== null); }
  detailPoints(ad: AdPerformanceRow, metric: "visits" | "conversion") {
    const values = ad.daily.map((row) => row[metric]);
    const valid = values.filter((value): value is number => value !== null);
    if (!valid.length) return "";
    const max = Math.max(1, ...valid);
    return values.map((value, index) => value === null ? null : String(index * 700 / Math.max(1, values.length - 1) + 10) + "," + String(10 + (1 - value / max) * 100)).filter((point): point is string => point !== null).join(" ");
  }
  chartSegments(metric: "visits" | "conversion") {
    const rows = this.data()?.daily ?? [];
    const values = rows.map((row) => row[metric]);
    const max = Math.max(1, ...values.filter((value): value is number => value !== null));
    const segments: string[] = [];
    let segment: string[] = [];
    values.forEach((value, index) => {
      if (value === null) {
        if (segment.length) segments.push(segment.join(" "));
        segment = [];
        return;
      }
      const x = rows.length > 1 ? 48 + (index / (rows.length - 1)) * 756 : 426;
      const y = 20 + (1 - value / max) * 236;
      segment.push(`${x},${y}`);
    });
    if (segment.length) segments.push(segment.join(" "));
    return segments;
  }
  statusLabel(value: string) {
    return ({ active: "Ativo", paused: "Pausado", closed: "Encerrado", unavailable: "Indisponível" } as Record<string, string>)[value] ?? value;
  }
  clearFilters() {
    this.channel.set("all"); this.status.set("all"); this.search.set("");
    this.start.set(this.initial.startDate); this.end.set(this.initial.endDate);
    this.page.set(1); this.load();
  }

  exportCsv() {
    this.exporting.set(true);
    const base = { ...this.params(), page_size: 100 };
    this.api.adPerformance({ ...base, page: 1 }).subscribe({
      next: (first) => {
        const pages = Array.from({ length: Math.max(0, Math.ceil(first.total_ads / 100) - 1) }, (_, index) =>
          this.api.adPerformance({ ...base, page: index + 2 }),
        );
        const completeExport = (rest: AdPerformanceSummary[]) => {
          const ads = [...first.ads, ...rest.flatMap((result) => result.ads)];
          const header = ["canal", "item_id", "parent_item_id", "sku", "titulo", "data", "visitas", "pedidos", "conversao", "status_dado", "atualizado_em"];
          const rows = ads.flatMap((ad) => ad.daily.map((day) => [
            ad.channel, ad.item_id, ad.parent_item_id, ad.sku, ad.title, day.date,
            day.visits, day.orders, day.conversion === null ? "" : day.conversion.toFixed(2),
            day.sync_status, ad.updated_at,
          ]));
          const escapeCsv = (value: unknown) => `"${String(value ?? "").replaceAll('"', '""')}"`;
          const csv = [header, ...rows].map((row) => row.map(escapeCsv).join(",")).join(String.fromCharCode(13, 10));
          const blob = new Blob([String.fromCharCode(0xfeff), csv], { type: "text/csv;charset=utf-8" });
          const link = document.createElement("a");
          link.href = URL.createObjectURL(blob);
          link.download = `desempenho-anuncios-${this.start()}-a-${this.end()}.csv`;
          link.click();
          setTimeout(() => URL.revokeObjectURL(link.href), 1000);
          this.exporting.set(false);
        };
        if (pages.length) forkJoin(pages).subscribe({next: completeExport, error: () => { this.exporting.set(false); this.error.set(true); }});
        else completeExport([]);
      },
      error: () => { this.exporting.set(false); this.error.set(true); },
    });
  }
}
