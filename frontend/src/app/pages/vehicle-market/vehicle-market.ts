import { DatePipe, DecimalPipe, KeyValuePipe } from '@angular/common';
import { Component, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { MarketStudiesApi } from '../../core/api/market-studies-api';
import { VehicleMarketOverview } from '../../core/models';
import { PageHeader } from '../../shared/page-header';

@Component({
  selector: 'app-vehicle-market',
  imports: [DatePipe, DecimalPipe, FormsModule, KeyValuePipe, PageHeader, RouterLink],
  templateUrl: './vehicle-market.html',
  styleUrl: './vehicle-market.scss',
})
export class VehicleMarketPage implements OnInit, OnDestroy {
  private readonly api = inject(MarketStudiesApi);
  readonly overview = signal<VehicleMarketOverview | null>(null);
  readonly loading = signal(true);
  readonly error = signal('');
  readonly filters = { nationality: '', brand: '', category: '', period: '' };
  private refreshTimer?: ReturnType<typeof setInterval>;

  ngOnInit(): void {
    const params = new URLSearchParams(window.location.search);
    this.filters.brand = params.get('brand') ?? '';
    this.filters.nationality = params.get('nationality') ?? '';
    this.filters.category = params.get('category') ?? '';
    this.filters.period = params.get('period') ?? '';
    this.load();
    this.refreshTimer = setInterval(() => this.load(false), 60_000);
  }

  ngOnDestroy(): void {
    if (this.refreshTimer) clearInterval(this.refreshTimer);
  }

  load(showLoading = true): void {
    if (showLoading) this.loading.set(true);
    this.error.set('');
    this.api
      .vehicleMarket(
        Object.fromEntries(
          Object.entries(this.filters).filter(([, value]) => Boolean(value)),
        ),
      )
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: (overview) => this.overview.set(overview),
        error: () =>
          this.error.set(
            this.overview()
              ? 'A fonte está temporariamente indisponível. Exibindo a última publicação válida.'
              : 'Não foi possível carregar os rankings automotivos.',
          ),
      });
  }

  nationals(): string[] {
    return [...new Set(Object.values(this.overview()?.brand_nationalities ?? {}))].sort();
  }

  trendWidth(value: number): number {
    const rows = this.overview()?.trend ?? [];
    return Math.round((value / Math.max(...rows.map((row) => row.value), 1)) * 100);
  }

  sourceLabel(metric: string | null): string {
    return metric === 'fleet' ? 'Frota registrada' : 'Emplacamentos';
  }
}
