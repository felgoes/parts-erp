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
    <app-page-header eyebrow="Operação" title="Monitoramento" subtitle="Saúde técnica e conversão da loja." />
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
      <section class="content-grid">
        <article class="card"><h2>Funil da loja</h2><p>Eventos anonimizados do catálogo público.</p><div class="funnel">@for (item of funnel(summary); track item.name) { <div><span>{{ item.label }}</span><b>{{ item.count }}</b></div> }</div></article>
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
  healthChecks(summary: TelemetrySummary): TelemetryHealth[] {
    const latest = new Map<string, TelemetryHealth>();
    for (const item of summary.health) if (!latest.has(item.check_name)) latest.set(item.check_name, item);
    return [...latest.values()];
  }
  healthyCount(summary: TelemetrySummary) { return this.healthChecks(summary).filter((item) => item.ok).length; }
  healthLabel(name: string) { return ({ api: 'API principal', 'API principal': 'API principal', 'Banco de dados': 'Banco de dados', 'Catálogo público': 'Catálogo público' } as Record<string, string>)[name] ?? name; }
  funnel(summary: TelemetrySummary) {
    return [
      { name: 'landing_view', label: 'Entradas na landing', count: this.eventCount(summary, 'landing_view') },
      { name: 'catalog_search', label: 'Buscas no catálogo', count: this.eventCount(summary, 'catalog_search') },
      { name: 'product_view', label: 'Visualizações de peças', count: this.eventCount(summary, 'product_view') },
      { name: 'catalog_empty_result', label: 'Buscas sem resultado', count: this.eventCount(summary, 'catalog_empty_result') },
      { name: 'mercado_livre_click', label: 'Cliques no Mercado Livre', count: this.eventCount(summary, 'mercado_livre_click') },
      { name: 'whatsapp_click', label: 'Cliques no WhatsApp', count: this.eventCount(summary, 'whatsapp_click') },
    ];
  }
}
