import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { ApiService } from '../../core/api.service';
import { TelemetryHealth, TelemetrySummary } from '../../core/models';
import { PageHeader } from '../../shared/page-header';

@Component({
  selector: 'app-monitoring',
  imports: [DatePipe, DecimalPipe, PageHeader],
  template: `
    <app-page-header eyebrow="Operação" title="Monitoramento" subtitle="Saúde técnica e conversão da loja." />
    @if (data(); as summary) {
      <section class="monitor-grid">
        <article class="card highlight"><span>Interações nos últimos {{ summary.days }} dias</span><strong>{{ totalEvents(summary) }}</strong><small>Eventos anônimos da operação</small></article>
        <article class="card"><span>Peças visualizadas</span><strong>{{ eventCount(summary, 'product_view') }}</strong><small>Interesse no catálogo</small></article>
        <article class="card"><span>Buscas realizadas</span><strong>{{ eventCount(summary, 'catalog_search') }}</strong><small>Intenção de compra</small></article>
        <article class="card"><span>Contatos comerciais</span><strong>{{ commercialClicks(summary) }}</strong><small>Mercado Livre + WhatsApp</small></article>
      </section>
      <section class="content-grid">
        <article class="card"><h2>Funil da loja</h2><p>Eventos anonimizados do catálogo público.</p><div class="funnel">@for (item of funnel(summary); track item.name) { <div><span>{{ item.label }}</span><b>{{ item.count }}</b></div> }</div></article>
        <article class="card health-card"><div class="card-title"><div><h2>Saúde da operação</h2><p>Última verificação de cada serviço monitorado.</p></div><span class="health-summary">{{ healthyCount(summary) }}/{{ healthChecks(summary).length }} OK</span></div><div class="health">@for (item of healthChecks(summary); track item.check_name) { <div><span class="dot" [class.down]="!item.ok"></span><div><strong>{{ healthLabel(item.check_name) }}</strong><small>{{ item.ok ? 'Operacional' : 'Falha' }} · {{ item.latency_ms | number:'1.0-0' }} ms · {{ item.detail || 'Sem detalhe' }} · {{ item.checked_at | date:'dd/MM HH:mm' }}</small></div></div> } @empty { <p class="muted">Ainda não há verificações registradas.</p> }</div></article>
      </section>
    } @else { <div class="loading">Carregando monitoramento...</div> }
  `,
  styleUrl: './monitoring.scss',
})
export class MonitoringPage implements OnInit {
  private readonly api = inject(ApiService);
  readonly data = signal<TelemetrySummary | null>(null);
  ngOnInit() { this.api.telemetrySummary().subscribe((value) => this.data.set(value)); }
  totalEvents(summary: TelemetrySummary) { return summary.events.reduce((total, item) => total + item.count, 0); }
  eventCount(summary: TelemetrySummary, name: string) { return summary.events.find((item) => item.name === name)?.count ?? 0; }
  commercialClicks(summary: TelemetrySummary) { return this.eventCount(summary, 'mercado_livre_click') + this.eventCount(summary, 'whatsapp_click'); }
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
