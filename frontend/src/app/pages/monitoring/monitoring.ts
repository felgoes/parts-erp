import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { ApiService } from '../../core/api.service';
import { TelemetrySummary } from '../../core/models';
import { PageHeader } from '../../shared/page-header';

@Component({
  selector: 'app-monitoring',
  imports: [DatePipe, PageHeader],
  template: `
    <app-page-header eyebrow="Operacao" title="Monitoramento" subtitle="Saude tecnica e conversao da loja." />
    @if (data(); as summary) {
      <section class="monitor-grid">
        <article class="card highlight"><span>Eventos nos ultimos {{ summary.days }} dias</span><strong>{{ totalEvents(summary) }}</strong><small>acoes registradas sem dados pessoais</small></article>
        <article class="card"><span>Produtos vistos</span><strong>{{ eventCount(summary, 'product_view') }}</strong><small>interesse no catalogo</small></article>
        <article class="card"><span>Cliques comerciais</span><strong>{{ eventCount(summary, 'mercado_livre_click') + eventCount(summary, 'whatsapp_click') }}</strong><small>Mercado Livre + WhatsApp</small></article>
      </section>
      <section class="content-grid">
        <article class="card"><h2>Funil da loja</h2><p>Eventos anonimizados do catalogo publico.</p><div class="funnel">@for (item of funnel(summary); track item.name) { <div><span>{{ item.label }}</span><b>{{ item.count }}</b></div> }</div></article>
        <article class="card"><h2>Saude recente</h2><p>Ultimas verificacoes do monitor local.</p><div class="health">@for (item of summary.health; track item.check_name + item.checked_at) { <div><span class="dot" [class.down]="!item.ok"></span><div><strong>{{ item.check_name }}</strong><small>{{ item.ok ? 'Operacional' : 'Falha' }} · {{ item.latency_ms }} ms · {{ item.checked_at | date:'dd/MM HH:mm' }}</small></div></div> }</div></article>
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
  funnel(summary: TelemetrySummary) {
    return [
      { name: 'landing_view', label: 'Entradas na landing', count: this.eventCount(summary, 'landing_view') },
      { name: 'catalog_search', label: 'Buscas no catalogo', count: this.eventCount(summary, 'catalog_search') },
      { name: 'product_view', label: 'Visualizacoes de pecas', count: this.eventCount(summary, 'product_view') },
      { name: 'mercado_livre_click', label: 'Cliques no Mercado Livre', count: this.eventCount(summary, 'mercado_livre_click') },
      { name: 'whatsapp_click', label: 'Cliques no WhatsApp', count: this.eventCount(summary, 'whatsapp_click') },
    ];
  }
}
