import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { debounceTime } from 'rxjs';
import { CurrencyPipe, DecimalPipe, registerLocaleData } from '@angular/common';
import localePtBr from '@angular/common/locales/pt';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { finalize } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { LiveUpdatesService } from '../../core/live-updates.service';
import { FinanceDailyMetric, FinanceOverview } from '../../core/models';
import { DateRange, quickDateRange } from '../../core/quick-date-ranges';
import { PageHeader } from '../../shared/page-header';
import { PeriodFilter } from '../../shared/period-filter';

registerLocaleData(localePtBr);

@Component({
  selector: 'app-finance',
  imports: [CurrencyPipe, DecimalPipe, PageHeader, PeriodFilter],
  templateUrl: './finance.html',
  styleUrl: './finance.scss',
})
export class FinancePage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly live = inject(LiveUpdatesService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly initialRange = quickDateRange('last30');
  readonly startDate = signal(this.initialRange.startDate);
  readonly endDate = signal(this.initialRange.endDate);
  readonly data = signal<FinanceOverview | null>(null);
  readonly loading = signal(false);
  readonly error = signal('');
  readonly chartDays = computed(() => {
    const days = this.data()?.daily ?? [];
    return days.length > 31 ? days.slice(-31) : days;
  });
  private readonly chartMax = computed(() =>
    Math.max(1, ...this.chartDays().flatMap((day) => [day.inbound_value, day.outbound_value])),
  );
  readonly hasChartData = computed(() =>
    this.chartDays().some((day) => day.inbound_value > 0 || day.outbound_value > 0),
  );

  ngOnInit() {
    this.load();
    this.live.changes$
      .pipe(debounceTime(500), takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.load());
  }
  applyPeriod(range: DateRange) {
    this.startDate.set(range.startDate);
    this.endDate.set(range.endDate);
    this.load();
  }
  load() {
    this.loading.set(true);
    this.error.set('');
    this.api
      .financeOverview(this.startDate(), this.endDate())
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: (result) => this.data.set(result),
        error: () =>
          this.error.set('Não foi possível carregar as métricas financeiras. Tente novamente.'),
      });
  }
  barHeight(value: number) {
    return value > 0 ? Math.max(5, (value / this.chartMax()) * 100) : 0;
  }
  chartTooltip(day: FinanceDailyMetric) {
    return `${day.label}: entradas ${this.currency(day.inbound_value)} · saídas ${this.currency(day.outbound_value)}`;
  }
  chartDescription() {
    return `Gráfico de entradas e saídas por dia para ${this.data()?.period_label ?? 'o período selecionado'}.`;
  }
  private currency(value: number) {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value);
  }
}
