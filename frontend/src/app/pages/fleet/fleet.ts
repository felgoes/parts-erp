import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { FleetApi } from '../../core/api/fleet-api';
import { FleetOverview, FleetRankRow, FleetRecordPage } from '../../core/models/fleet';
import { PageHeader } from '../../shared/page-header';

@Component({
  selector: 'app-fleet',
  imports: [DatePipe, DecimalPipe, FormsModule, PageHeader, RouterLink],
  templateUrl: './fleet.html',
  styleUrl: './fleet.scss',
})
export class FleetPage implements OnInit {
  private readonly api = inject(FleetApi);
  private readonly router = inject(Router);
  readonly overview = signal<FleetOverview | null>(null);
  readonly records = signal<FleetRecordPage | null>(null);
  readonly loading = signal(true);
  readonly recordsLoading = signal(true);
  readonly error = signal('');
  readonly filters = {
    period: '',
    brand: '',
    nationality: '',
    model: '',
    age_band: '',
    year_from: '',
    year_to: '',
    sort: 'fleet_desc',
  };
  readonly page = signal(1);
  readonly pageSize = 25;
  private readonly colors = ['#214d3b', '#6f9c3d', '#8fb7a1', '#d2a13a', '#7598ad', '#9a7868'];

  ngOnInit(): void {
    const params = new URLSearchParams(window.location.search);
    for (const key of Object.keys(this.filters) as Array<keyof typeof this.filters>) {
      const value = params.get(key);
      if (value) this.filters[key] = value;
    }
    this.page.set(Math.max(1, Number(params.get('page') || 1)));
    this.load();
  }

  applyFilters(page = 1): void {
    this.page.set(page);
    this.syncUrl();
    this.load();
  }

  resetFilters(): void {
    Object.assign(this.filters, {
      period: '',
      brand: '',
      nationality: '',
      model: '',
      age_band: '',
      year_from: '',
      year_to: '',
      sort: 'fleet_desc',
    });
    this.applyFilters(1);
  }

  selectFilter(key: 'brand' | 'nationality' | 'age_band', value: string): void {
    this.filters[key] = this.filters[key] === value ? '' : value;
    this.applyFilters(1);
  }

  selectModel(brand: string, model: string): void {
    this.filters.brand = brand;
    this.filters.model = model;
    this.applyFilters(1);
  }

  selectYear(year: string): void {
    this.filters.year_from = year;
    this.filters.year_to = year;
    this.applyFilters(1);
  }

  nextPage(direction: -1 | 1): void {
    const total = this.records()?.total ?? 0;
    const pages = Math.max(1, Math.ceil(total / this.pageSize));
    const next = Math.min(pages, Math.max(1, this.page() + direction));
    if (next !== this.page()) this.applyFilters(next);
  }

  pages(): number {
    return Math.max(1, Math.ceil((this.records()?.total ?? 0) / this.pageSize));
  }

  barWidth(value: number, rows: FleetRankRow[]): number {
    return Math.max(2, Math.round((value / Math.max(...rows.map((row) => row.value), 1)) * 100));
  }

  modelBarWidth(value: number): number {
    const rows = this.overview()?.models ?? [];
    return Math.max(2, Math.round((value / Math.max(...rows.map((row) => row.value), 1)) * 100));
  }

  donutBackground(): string {
    const rows = this.overview()?.nationalities ?? [];
    if (!rows.length) return 'conic-gradient(#d8dfd9 0 100%)';
    const total = rows.reduce((sum, row) => sum + row.value, 0) || 1;
    let cursor = 0;
    const segments = rows.slice(0, this.colors.length).map((row, index) => {
      const start = cursor;
      cursor += (row.value / total) * 100;
      return `${this.colors[index]} ${start}% ${cursor}%`;
    });
    if (cursor < 100) segments.push(`#aebbb3 ${cursor}% 100%`);
    return `conic-gradient(${segments.join(', ')})`;
  }

  ageColor(index: number): string {
    return this.colors[index % this.colors.length];
  }

  studyQuery(): Record<string, string> {
    if (this.filters.brand) {
      return { mode: 'brand', brand: this.filters.brand };
    }
    if (this.filters.nationality) {
      return { mode: 'nationality', nationality: this.filters.nationality };
    }
    return {};
  }

  private load(): void {
    const params = this.query();
    this.loading.set(true);
    this.recordsLoading.set(true);
    this.error.set('');
    this.api
      .overview(params)
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: (overview) => this.overview.set(overview),
        error: () => this.error.set('Não foi possível carregar o panorama da frota.'),
      });
    this.api
      .records({ ...params, page: this.page(), page_size: this.pageSize })
      .pipe(finalize(() => this.recordsLoading.set(false)))
      .subscribe({
        next: (records) => this.records.set(records),
        error: () => this.error.set('Não foi possível carregar a lista da frota.'),
      });
  }

  private query(): Record<string, string> {
    return Object.fromEntries(
      Object.entries(this.filters).filter(([, value]) => Boolean(value)),
    );
  }

  private syncUrl(): void {
    void this.router.navigate(['/fleet'], {
      queryParams: { ...this.query(), page: this.page() > 1 ? this.page() : null },
      replaceUrl: true,
    });
  }
}
