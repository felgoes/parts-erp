import { CurrencyPipe, DecimalPipe, DatePipe } from '@angular/common';
import { Component, DestroyRef, Input, OnChanges, SimpleChanges, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { timer } from 'rxjs';
import { DashboardApi } from '../../core/api/dashboard-api';
import { DashboardMarketplaceMetric, DashboardMarketplaceMetrics } from '../../core/models';
import { AuthService } from '../../core/auth.service';

@Component({
  selector: 'app-dashboard-marketplace-performance',
  imports: [DatePipe, RouterLink],
  templateUrl: './marketplace-performance.html',
  styleUrl: './marketplace-performance.scss',
})
export class MarketplacePerformance implements OnChanges {
  private readonly api = inject(DashboardApi);
  private readonly auth = inject(AuthService);
  private readonly destroyRef = inject(DestroyRef);
  @Input() startDate = '';
  @Input() endDate = '';
  @Input() reloadToken = 0;
  @Input() financialHidden = false;
  @Input() financialAllowed = false;
  @Input() canRefresh = false;
  readonly data = signal<DashboardMarketplaceMetrics | null>(null);
  readonly metricKeys = ['orders', 'units', 'gross', 'average_ticket', 'visits', 'conversion'] as const;
  readonly loading = signal(true);
  readonly failed = signal(false);
  readonly refreshing = signal(false);
  private revision = 0;
  private readonly refreshPeriods = new Set<string>();
  private initialized = false;
  readonly canReadIntegration = () => this.auth.user()?.role === 'admin';

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['startDate'] || changes['endDate']) {
      this.initialized = true;
      this.data.set(null);
      this.failed.set(false);
      this.load();
      if (this.canRefresh) this.refresh(false);
      return;
    }
    if (this.initialized && changes['reloadToken']) this.load();
  }

  load(pollIfUpdating = true): void {
    if (!this.startDate || !this.endDate) return;
    const revision = ++this.revision;
    const period = this.startDate + '|' + this.endDate;
    this.loading.set(!this.data());
    this.api.dashboardMarketplace(this.startDate, this.endDate)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => {
          if (revision !== this.revision || period !== this.startDate + '|' + this.endDate) return;
          this.data.set(result);
          this.loading.set(false);
          this.failed.set(false);
          if (pollIfUpdating && result.sync_state === 'updating') this.poll(revision, 4);
        },
        error: () => {
          if (revision !== this.revision) return;
          this.loading.set(false);
          this.failed.set(true);
        },
      });
  }

  refresh(manual = true): void {
    const period = this.startDate + '|' + this.endDate;
    if (!this.canRefresh || this.refreshPeriods.has(period)) return;
    this.refreshPeriods.add(period);
    this.refreshing.set(true);
    this.failed.set(false);
    this.api.refreshDashboardMarketplace(this.startDate, this.endDate, manual)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.refreshPeriods.delete(period);
          if (period === this.startDate + '|' + this.endDate) {
            this.refreshing.set(false);
            this.load(false);
            this.poll(this.revision, 4);
          }
        },
        error: () => {
          this.refreshPeriods.delete(period);
          if (period === this.startDate + '|' + this.endDate) this.refreshing.set(false);
          if (period === this.startDate + "|" + this.endDate) this.failed.set(true);
        },
      });
  }

  retry(): void {
    if (this.canRefresh) this.refresh();
    else this.load();
  }

  private poll(revision: number, remaining = 4): void {
    timer(2500).pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      if (revision !== this.revision) return;
      this.load(false);
      if (remaining > 1) this.poll(this.revision, remaining - 1);
    });
  }

  metricFor(summary: DashboardMarketplaceMetrics, key: string): DashboardMarketplaceMetric {
    return summary.metrics[key as keyof DashboardMarketplaceMetrics['metrics']];
  }

  metricLabel(key: string): string {
    return ({
      orders: 'Pedidos confirmados', units: 'Unidades vendidas', gross: 'Vendas brutas',
      average_ticket: 'Ticket médio', visits: 'Visitas aos anúncios',
      conversion: 'Conversão operacional',
    } as Record<string, string>)[key] ?? key;
  }

  metricValue(key: string, metric: DashboardMarketplaceMetric): string {
    if (metric.value === null) return '—';
    if (key === 'gross' || key === 'average_ticket') {
      if (this.financialHidden || !this.financialAllowed) return '••••••';
      return new CurrencyPipe('pt-BR').transform(metric.value, 'BRL', 'symbol', '1.2-2') ?? '—';
    }
    if (key === 'conversion') {
      return (new DecimalPipe('pt-BR').transform(metric.value, '1.2-2') ?? metric.value) + '%';
    }
    if (key === 'units') return new DecimalPipe('pt-BR').transform(metric.value, '1.0-3') ?? String(metric.value);
    return new DecimalPipe('pt-BR').transform(metric.value, '1.0-0') ?? String(metric.value);
  }

  formatPeriodDate(value: string): string {
    const parts = value.split('-');
    return parts.length === 3 ? parts[2] + '/' + parts[1] + '/' + parts[0] : value;
  }

  syncLabel(state: string): string {
    return ({
      disconnected: 'Conta desconectada', updating: 'Atualizando…',
      failed: 'Falha na atualização', complete: 'Sincronização concluída',
      partial: 'Cobertura parcial',
    } as Record<string, string>)[state] ?? 'Dados do período';
  }
}
