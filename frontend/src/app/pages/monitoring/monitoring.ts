import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { debounceTime } from 'rxjs';
import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { ApiService } from '../../core/api.service';
import { LiveUpdatesService } from '../../core/live-updates.service';
import { TelemetryHealth, TelemetrySummary } from '../../core/models';
import { DateRange, quickDateRange } from '../../core/quick-date-ranges';
import { PageHeader } from '../../shared/page-header';
import { PeriodFilter } from '../../shared/period-filter';

@Component({
  selector: 'app-monitoring',
  imports: [DatePipe, DecimalPipe, PageHeader, PeriodFilter],
  templateUrl: './monitoring.html',
  styleUrl: './monitoring.scss',
})
export class MonitoringPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly live = inject(LiveUpdatesService);
  private readonly destroyRef = inject(DestroyRef);
  readonly data = signal<TelemetrySummary | null>(null);
  readonly loading = signal(false);
  readonly error = signal(false);
  readonly hiddenSeries = signal(new Set<string>());
  private readonly initialRange = quickDateRange('last30');
  readonly startDate = signal(this.initialRange.startDate);
  readonly endDate = signal(this.initialRange.endDate);
  ngOnInit() {
    this.load();
    this.live.changes$
      .pipe(debounceTime(2000), takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.load());
  }
  applyPeriod(range: DateRange) {
    this.startDate.set(range.startDate);
    this.endDate.set(range.endDate);
    this.load();
  }
  load() {
    if (!this.startDate() || !this.endDate() || this.startDate() > this.endDate()) {
      this.error.set(true);
      return;
    }
    this.loading.set(true);
    this.error.set(false);
    this.api.telemetrySummary(this.startDate(), this.endDate()).subscribe({
      next: (value) => {
        this.data.set(value);
        this.loading.set(false);
      },
      error: () => {
        this.error.set(true);
        this.loading.set(false);
      },
    });
  }
  totalEvents(summary: TelemetrySummary) {
    return summary.events.reduce((total, item) => total + item.count, 0);
  }
  eventCount(summary: TelemetrySummary, name: string) {
    return summary.events.find((item) => item.name === name)?.count ?? 0;
  }
  commercialClicks(summary: TelemetrySummary) {
    return (
      this.eventCount(summary, 'mercado_livre_click') + this.eventCount(summary, 'whatsapp_click')
    );
  }
  productViewTotal(summary: TelemetrySummary) {
    return summary.product_views.reduce((total, item) => total + item.views, 0);
  }
  share(value: number, total: number) {
    return total ? (value / total) * 100 : 0;
  }
  private readonly trackedSeries = [
    { key: 'landing_view', label: 'Acessos ao site', color: '#203f32' },
    { key: 'catalog_search', label: 'Buscas', color: '#90b83f' },
    { key: 'catalog_empty_result', label: 'Buscas sem resultado', color: '#c76c54' },
    { key: 'product_view', label: 'Peças abertas', color: '#3478bd' },
    { key: 'mercado_livre_click', label: 'Anúncios ML', color: '#ed9e32' },
    { key: 'whatsapp_click', label: 'Contatos WhatsApp', color: '#46a77a' },
  ];
  chartSeries() {
    const days = this.data()?.daily_events ?? [];
    const max = Math.max(1, ...days.flatMap((day) => day.events.map((event) => event.count)));
    const width = 756;
    return this.trackedSeries.map((series) => {
      const values = days.map((day) => ({
        date: day.date,
        value: day.events.find((event) => event.name === series.key)?.count ?? 0,
      }));
      const coordinates = values.map((point, index) => ({
        ...point,
        x: days.length > 1 ? 48 + (index / (days.length - 1)) * width : 48 + width / 2,
        y: 20 + (1 - point.value / max) * 236,
      }));
      return {
        ...series,
        total: values.reduce((sum, point) => sum + point.value, 0),
        points: coordinates.map((point) => `${point.x},${point.y}`).join(' '),
        coordinates,
      };
    });
  }
  chartY(tick: number) {
    return 20 + tick * 59;
  }
  chartTick(tick: number, summary: TelemetrySummary) {
    const max = Math.max(
      1,
      ...summary.daily_events.flatMap((day) => day.events.map((event) => event.count)),
    );
    return Math.round((max * (4 - tick)) / 4);
  }
  chartLabels(summary: TelemetrySummary) {
    const days = summary.daily_events;
    const indexes = [...new Set([0, Math.round((days.length - 1) / 2), days.length - 1])];
    return indexes
      .filter((index) => days[index])
      .map((index) => ({
        date: days[index].date,
        x: days.length > 1 ? 48 + (index / (days.length - 1)) * 756 : 426,
      }));
  }
  isSeriesHidden(key: string) {
    return this.hiddenSeries().has(key);
  }
  toggleSeries(key: string) {
    this.hiddenSeries.update((current) => {
      const next = new Set(current);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  }
  healthChecks(summary: TelemetrySummary): TelemetryHealth[] {
    const latest = new Map<string, TelemetryHealth>();
    for (const item of summary.health)
      if (!latest.has(item.check_name)) latest.set(item.check_name, item);
    return [...latest.values()];
  }
  healthyCount(summary: TelemetrySummary) {
    return this.healthChecks(summary).filter((item) => item.ok).length;
  }
  healthLabel(name: string) {
    return (
      (
        {
          api: 'API principal',
          'API principal': 'API principal',
          'Banco de dados': 'Banco de dados',
          'Catálogo público': 'Catálogo público',
        } as Record<string, string>
      )[name] ?? name
    );
  }
  eventBreakdown(summary: TelemetrySummary) {
    const labels: Record<string, { label: string; color: string }> = {
      landing_view: { label: 'Acessos ao site', color: '#203f32' },
      catalog_search: { label: 'Buscas no catálogo', color: '#90b83f' },
      product_view: { label: 'Peças abertas', color: '#3478bd' },
      catalog_empty_result: { label: 'Buscas sem resultado', color: '#c76c54' },
      mercado_livre_click: { label: 'Cliques em anúncios do ML', color: '#ed9e32' },
      whatsapp_click: { label: 'Contatos pelo WhatsApp', color: '#46a77a' },
    };
    return summary.events
      .filter((event) => event.count > 0)
      .map((event) => ({
        name: event.name,
        count: event.count,
        ...(labels[event.name] ?? { label: event.name, color: '#8b9690' }),
      }))
      .sort((left, right) => right.count - left.count);
  }
}
