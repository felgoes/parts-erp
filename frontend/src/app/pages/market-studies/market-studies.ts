import { DatePipe, DecimalPipe, KeyValuePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { MarketStudiesApi } from '../../core/api/market-studies-api';
import { AuthService } from '../../core/auth.service';
import {
  MarketStudyConnector,
  MarketStudySummary,
  VehicleMarketOverview,
} from '../../core/models';
import { PageHeader } from '../../shared/page-header';
import { decisionLabel, trendWidth } from './market-study-view';

@Component({
  selector: 'app-market-studies',
  imports: [DatePipe, DecimalPipe, FormsModule, KeyValuePipe, PageHeader, RouterLink],
  templateUrl: './market-studies.html',
  styleUrl: './market-studies.scss',
})
export class MarketStudiesPage implements OnInit {
  private readonly api = inject(MarketStudiesApi);
  private readonly router = inject(Router);
  readonly auth = inject(AuthService);
  readonly tab = signal<'studies' | 'cars'>('studies');
  readonly studies = signal<MarketStudySummary[]>([]);
  readonly total = signal(0);
  readonly loading = signal(true);
  readonly carsLoading = signal(false);
  readonly error = signal('');
  readonly cars = signal<VehicleMarketOverview | null>(null);
  readonly filters = { search: '', status: '', decision: '' };
  readonly carFilters = { nationality: '', brand: '', category: '', period: '' };
  readonly connector = {
    provider: 'openai_responses' as MarketStudyConnector['provider'],
    model: 'gpt-6-luna',
    base_url: '',
    api_key: '',
    enabled: false,
    has_api_key: false,
  };
  readonly connectorOpen = signal(false);
  readonly savingConnector = signal(false);
  readonly connectorMessage = signal('');
  readonly connectorError = signal(false);

  ngOnInit(): void {
    const params = new URLSearchParams(window.location.search);
    this.tab.set(params.get('tab') === 'cars' ? 'cars' : 'studies');
    this.filters.search = params.get('search') ?? '';
    this.filters.status = params.get('status') ?? '';
    this.filters.decision = params.get('decision') ?? '';
    this.carFilters.nationality = params.get('nationality') ?? '';
    this.carFilters.brand = params.get('brand') ?? '';
    if (this.tab() === 'cars') this.loadCars();
    this.loadStudies();
    if (this.canConfigure) {
      this.api.marketStudyConnector().subscribe({
        next: (config) => {
          this.connector.provider = config.provider;
          this.connector.model = config.model;
          this.connector.base_url = config.base_url ?? '';
          this.connector.enabled = config.enabled;
          this.connector.has_api_key = config.has_api_key;
        },
      });
    }
  }

  get canRun(): boolean {
    return ['admin', 'manager'].includes(this.auth.user()?.role ?? '');
  }

  get canConfigure(): boolean {
    return this.canRun;
  }

  setTab(tab: 'studies' | 'cars'): void {
    this.tab.set(tab);
    this.syncUrl();
    this.saveListState();
    if (tab === 'cars' && !this.cars()) this.loadCars();
  }

  loadStudies(): void {
    this.loading.set(true);
    this.error.set('');
    this.api
      .marketStudies({
        search: this.filters.search.trim() || undefined,
        status: this.filters.status || undefined,
        decision: this.filters.decision || undefined,
        limit: 50,
      })
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: (result) => {
          this.studies.set(result.items);
          this.total.set(result.total);
        },
        error: () => this.error.set('Não foi possível carregar a biblioteca de estudos.'),
      });
  }

  applyFilters(): void {
    this.syncUrl();
    this.saveListState();
    this.loadStudies();
  }

  clearFilters(): void {
    this.filters.search = '';
    this.filters.status = '';
    this.filters.decision = '';
    this.applyFilters();
  }

  loadCars(): void {
    this.carsLoading.set(true);
    const params = Object.entries(this.carFilters).reduce<Record<string, string>>(
      (result, [key, value]) => {
        if (value) result[key] = value;
        return result;
      },
      {},
    );
    this.api
      .vehicleMarket(params)
      .pipe(finalize(() => this.carsLoading.set(false)))
      .subscribe({
        next: (overview) => this.cars.set(overview),
        error: () => this.error.set('Não foi possível carregar os dados de veículos.'),
      });
  }

  applyCarFilters(): void {
    this.syncUrl();
    this.saveListState();
    this.cars.set(null);
    this.loadCars();
  }

  selectionQuery(study: MarketStudySummary): Record<string, string> {
    return study.brand
      ? { mode: 'brand', brand: study.brand }
      : study.nationality
        ? { mode: 'nationality', nationality: study.nationality }
        : {};
  }

  saveConnector(): void {
    this.savingConnector.set(true);
    this.connectorMessage.set('');
    this.api
      .saveMarketStudyConnector({
        provider: this.connector.provider,
        model: this.connector.model.trim(),
        base_url: this.connector.base_url.trim() || undefined,
        api_key: this.connector.api_key.trim() || undefined,
        enabled: this.connector.enabled,
      })
      .pipe(finalize(() => this.savingConnector.set(false)))
      .subscribe({
        next: (saved) => {
          this.connector.api_key = '';
          this.connector.has_api_key = saved.has_api_key;
          this.connectorMessage.set('Conector salvo. A chave não será exibida novamente.');
          this.connectorError.set(false);
        },
        error: (err: { error?: { detail?: string } }) => {
          this.connectorMessage.set(err.error?.detail || 'Não foi possível salvar o conector.');
          this.connectorError.set(true);
        },
      });
  }

  decisionLabel(value: string | null): string {
    return decisionLabel(value);
  }

  uniqueNationalities(): string[] {
    return [...new Set(Object.values(this.cars()?.brand_nationalities ?? {}))].sort();
  }

  trendWidth(value: number, rows: Array<{ value: number }>): number {
    return trendWidth(value, rows);
  }

  private syncUrl(): void {
    const query: Record<string, string> = {};
    if (this.tab() === 'cars') {
      query['tab'] = 'cars';
      for (const [key, value] of Object.entries(this.carFilters)) {
        if (value) query[key] = value;
      }
    } else {
      for (const [key, value] of Object.entries(this.filters)) {
        if (value) query[key] = value;
      }
    }
    void this.router.navigate(['/market-studies'], { queryParams: query });
  }

  private saveListState(): void {
    sessionStorage.setItem(
      'market-studies-list-state',
      JSON.stringify({
        tab: this.tab(),
        filters: this.filters,
        carFilters: this.carFilters,
      }),
    );
  }
}
