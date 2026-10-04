import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../core/api.service';
import { TelemetryHealth, TelemetrySummary } from '../../core/models';
import { PageHeader } from '../../shared/page-header';

@Component({
  selector: 'app-monitoring',
  imports: [DatePipe, DecimalPipe, FormsModule, PageHeader],
  template: `
    <app-page-header eyebrow="Operação" title="Monitoramento" subtitle="Saúde técnica e comportamento no catálogo." />
    <section class="period-filter card" aria-label="Filtro de período">
      <div><strong>Período analisado</strong><small>As datas consideram o horário de Brasília.</small></div>
      <label>De <input type="date" [ngModel]="startDate()" (ngModelChange)="startDate.set($event)" /></label>
      <label>Até <input type="date" [ngModel]="endDate()" (ngModelChange)="endDate.set($event)" /></label>
      <button class="apply-filter" [disabled]="loading()" (click)="load()">{{ loading() ? 'Atualizando…' : 'Aplicar período' }}</button>
    </section>
    @if (error()) { <div class="monitor-error" role="alert">Não foi possível atualizar o monitoramento. Confira o período e tente novamente.</div> }
    @if (data(); as summary) {
      <section class="monitor-grid">
        <article class="card highlight"><span>Interações no período</span><strong>{{ totalEvents(summary) }}</strong><small>{{ startDate() | date:'dd/MM/yyyy' }} a {{ endDate() | date:'dd/MM/yyyy' }}</small></article>
        <article class="card"><span>Peças visualizadas</span><strong>{{ eventCount(summary, 'product_view') }}</strong><small>Interesse no catálogo</small></article>
        <article class="card"><span>Buscas realizadas</span><strong>{{ eventCount(summary, 'catalog_search') }}</strong><small>Intenção de compra</small></article>
        <article class="card"><span>Contatos comerciais</span><strong>{{ commercialClicks(summary) }}</strong><small>Mercado Livre + WhatsApp</small></article>
      </section>
      <section class="card trend-card">
        <div class="card-title"><div><h2>Atividade da loja</h2><p>Volume diário de navegação e intenção de compra no catálogo.</p></div><span class="chart-period">{{ summary.days }} dias</span></div>
        <div class="chart-legend" aria-label="Séries do gráfico">
          @for (series of chartSeries(); track series.key) {
            <button type="button" class="legend-item" [class.legend-muted]="isSeriesHidden(series.key)" (click)="toggleSeries(series.key)"><i [style.background]="series.color"></i>{{ series.label }}</button>
          }
        </div>
        @if (totalEvents(summary)) {
          <div class="chart-scroll"><svg class="activity-chart" viewBox="0 0 820 300" role="img" aria-label="Gráfico de linhas da atividade diária no período">
            @for (tick of [0, 1, 2, 3, 4]; track tick) {
              <line x1="48" [attr.y1]="chartY(tick)" x2="804" [attr.y2]="chartY(tick)" class="grid-line" />
              <text x="38" [attr.y]="chartY(tick) + 4" class="axis-label" text-anchor="end">{{ chartTick(tick, summary) }}</text>
            }
            @for (series of chartSeries(); track series.key) {
              @if (!isSeriesHidden(series.key) && series.total) {
                <polyline [attr.points]="series.points" fill="none" [attr.stroke]="series.color" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />
                @for (point of series.coordinates; track point.date) {
                  <circle [attr.cx]="point.x" [attr.cy]="point.y" r="3.5" [attr.fill]="series.color"><title>{{ point.date | date:'dd/MM/yyyy' }} · {{ series.label }}: {{ point.value }}</title></circle>
                }
              }
            }
            @for (label of chartLabels(summary); track label.date) { <text [attr.x]="label.x" y="286" class="axis-label" text-anchor="middle">{{ label.date | date:'dd/MM' }}</text> }
          </svg></div>
        } @else { <div class="chart-empty"><strong>Nenhuma interação neste período</strong><span>Quando alguém navegar pelo catálogo, a evolução aparecerá aqui.</span></div> }
      </section>
      <section class="content-grid">
        <article class="card breakdown-card"><h2>O que as pessoas fazem</h2><p>Distribuição das interações no período; não representa visitantes únicos.</p><div class="event-bars">@for (item of eventBreakdown(summary); track item.name) { <div class="event-bar-row"><div class="event-bar-heading"><span>{{ item.label }}</span><strong>{{ item.count }}</strong></div><div class="event-bar-track"><span [style.width.%]="share(item.count, totalEvents(summary))" [style.background]="item.color"></span></div><small>{{ share(item.count, totalEvents(summary)) | number:'1.0-1' }}% das interações</small></div> }</div></article>
        <article class="card health-card"><div class="card-title"><div><h2>Saúde da operação</h2><p>Última verificação de cada serviço monitorado.</p></div><span class="health-summary">{{ healthyCount(summary) }}/{{ healthChecks(summary).length }} OK</span></div><div class="health">@for (item of healthChecks(summary); track item.check_name) { <div><span class="dot" [class.down]="!item.ok"></span><div><strong>{{ healthLabel(item.check_name) }}</strong><small>{{ item.ok ? 'Operacional' : 'Falha' }} · {{ item.latency_ms | number:'1.0-0' }} ms · {{ item.detail || 'Sem detalhe' }} · {{ item.checked_at | date:'dd/MM HH:mm' }}</small></div></div> } @empty { <p class="muted">Ainda não há verificações registradas.</p> }</div></article>
      </section>
      <section class="card product-views-card">
        <div class="card-title"><div><h2>Visualizações por peça</h2><p>Aberturas dos detalhes de cada peça no catálogo público, no período selecionado.</p></div><span class="views-total">{{ productViewTotal(summary) }} visualizações</span></div>
        @if (summary.product_views.length) {
          <div class="table-wrap"><table><thead><tr><th>Peça</th><th>SKU</th><th class="numeric">Visualizações</th><th>Participação</th></tr></thead><tbody>@for (product of summary.product_views; track product.sku) { <tr><td><strong>{{ product.product_name }}</strong></td><td><code>{{ product.sku }}</code></td><td class="numeric"><strong>{{ product.views }}</strong></td><td><div class="view-bar"><span [style.width.%]="share(product.views, productViewTotal(summary))"></span></div><small>{{ share(product.views, productViewTotal(summary)) | number:'1.0-1' }}%</small></td></tr> }</tbody></table></div>
        } @else { <div class="views-empty"><strong>Sem visualizações detalhadas neste período</strong><span>Os detalhes abertos a partir desta versão serão contabilizados por SKU.</span></div> }
      </section>
    } @else { <div class="loading">Carregando monitoramento...</div> }
  `,
  styleUrl: './monitoring.scss',
})
export class MonitoringPage implements OnInit {
  private readonly api = inject(ApiService);
  readonly data = signal<TelemetrySummary | null>(null);
  readonly loading = signal(false);
  readonly error = signal(false);
  readonly hiddenSeries = signal(new Set<string>());
  readonly startDate = signal(this.dateString(new Date(Date.now() - 29 * 24 * 60 * 60 * 1000)));
  readonly endDate = signal(this.dateString(new Date()));
  ngOnInit() { this.load(); }
  load() {
    if (!this.startDate() || !this.endDate() || this.startDate() > this.endDate()) {
      this.error.set(true);
      return;
    }
    this.loading.set(true);
    this.error.set(false);
    this.api.telemetrySummary(this.startDate(), this.endDate()).subscribe({
      next: (value) => { this.data.set(value); this.loading.set(false); },
      error: () => { this.error.set(true); this.loading.set(false); },
    });
  }
  private dateString(date: Date) {
    const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
    return local.toISOString().slice(0, 10);
  }
  totalEvents(summary: TelemetrySummary) { return summary.events.reduce((total, item) => total + item.count, 0); }
  eventCount(summary: TelemetrySummary, name: string) { return summary.events.find((item) => item.name === name)?.count ?? 0; }
  commercialClicks(summary: TelemetrySummary) { return this.eventCount(summary, 'mercado_livre_click') + this.eventCount(summary, 'whatsapp_click'); }
  productViewTotal(summary: TelemetrySummary) { return summary.product_views.reduce((total, item) => total + item.views, 0); }
  share(value: number, total: number) { return total ? (value / total) * 100 : 0; }
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
      const values = days.map((day) => ({ date: day.date, value: day.events.find((event) => event.name === series.key)?.count ?? 0 }));
      const coordinates = values.map((point, index) => ({
        ...point,
        x: days.length > 1 ? 48 + (index / (days.length - 1)) * width : 48 + width / 2,
        y: 20 + (1 - point.value / max) * 236,
      }));
      return { ...series, total: values.reduce((sum, point) => sum + point.value, 0), points: coordinates.map((point) => `${point.x},${point.y}`).join(' '), coordinates };
    });
  }
  chartY(tick: number) { return 20 + tick * 59; }
  chartTick(tick: number, summary: TelemetrySummary) {
    const max = Math.max(1, ...summary.daily_events.flatMap((day) => day.events.map((event) => event.count)));
    return Math.round((max * (4 - tick)) / 4);
  }
  chartLabels(summary: TelemetrySummary) {
    const days = summary.daily_events;
    const indexes = [...new Set([0, Math.round((days.length - 1) / 2), days.length - 1])];
    return indexes.filter((index) => days[index]).map((index) => ({ date: days[index].date, x: days.length > 1 ? 48 + (index / (days.length - 1)) * 756 : 426 }));
  }
  isSeriesHidden(key: string) { return this.hiddenSeries().has(key); }
  toggleSeries(key: string) { this.hiddenSeries.update((current) => { const next = new Set(current); next.has(key) ? next.delete(key) : next.add(key); return next; }); }
  healthChecks(summary: TelemetrySummary): TelemetryHealth[] {
    const latest = new Map<string, TelemetryHealth>();
    for (const item of summary.health) if (!latest.has(item.check_name)) latest.set(item.check_name, item);
    return [...latest.values()];
  }
  healthyCount(summary: TelemetrySummary) { return this.healthChecks(summary).filter((item) => item.ok).length; }
  healthLabel(name: string) { return ({ api: 'API principal', 'API principal': 'API principal', 'Banco de dados': 'Banco de dados', 'Catálogo público': 'Catálogo público' } as Record<string, string>)[name] ?? name; }
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
      .map((event) => ({ name: event.name, count: event.count, ...(labels[event.name] ?? { label: event.name, color: '#8b9690' }) }))
      .sort((left, right) => right.count - left.count);
  }
}
