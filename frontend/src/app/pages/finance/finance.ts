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
  template: `
    <app-page-header eyebrow="Controle financeiro" title="Financeiro" subtitle="Custos do estoque, entradas, saídas e resultado das vendas — com rastreabilidade por peça." />

    <app-period-filter heading="Período de análise" description="Movimentações pelo dia em que ocorreram; vendas pela data original da fatura." ariaLabel="Filtrar indicadores financeiros por período" initialPreset="last30" [initialStartDate]="startDate()" [initialEndDate]="endDate()" (rangeChange)="applyPeriod($event)" />

    @if (loading()) {
      <section class="finance-state card" aria-live="polite"><span class="loading-mark"></span><strong>Atualizando os números do período…</strong></section>
    } @else if (error()) {
      <section class="finance-state card" role="alert"><strong>{{ error() }}</strong><button class="secondary" type="button" (click)="load()">Tentar novamente</button></section>
    } @else if (data(); as metrics) {
      <section class="finance-highlights" aria-label="Indicadores financeiros">
        <article class="finance-highlight inventory-highlight"><span>Estoque atual a custo médio</span><strong>{{ metrics.inventory_value | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</strong><small>{{ metrics.inventory_units | number:'1.0-3':'pt-BR' }} unidades em {{ metrics.by_product.length }} {{ metrics.by_product.length === 1 ? 'peça' : 'peças' }}</small><i aria-hidden="true">◒</i></article>
        <article class="finance-highlight"><span>Entradas de estoque</span><strong>{{ metrics.inbound_value | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</strong><small>{{ metrics.inbound_quantity | number:'1.0-3':'pt-BR' }} unidades, inclui devoluções</small></article>
        <article class="finance-highlight"><span>Saídas de estoque</span><strong>{{ metrics.outbound_value | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</strong><small>{{ metrics.outbound_quantity | number:'1.0-3':'pt-BR' }} unidades baixadas</small></article>
        <article class="finance-highlight"><span>Custo líquido das vendas</span><strong>{{ metrics.net_cost_of_goods | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</strong><small>Já desconta devoluções registradas</small></article>
      </section>

      @if (metrics.unknown_cost_movements > 0 || metrics.unvalued_sales_items > 0) {
        <aside class="cost-coverage-note" role="status"><span aria-hidden="true">i</span><p><strong>Histórico de custos parcial.</strong> @if (metrics.unvalued_sales_items > 0) { {{ metrics.unvalued_sales_items }} {{ metrics.unvalued_sales_items === 1 ? 'item vendido não tem' : 'itens vendidos não têm' }} custo registrado; por isso a margem não é apresentada como se fosse completa. } @if (metrics.unknown_cost_movements > 0) { {{ metrics.unknown_cost_movements }} movimentações antigas também não têm custo salvo. } Novas entradas e saídas passam a guardar esse valor automaticamente.</p></aside>
      }

      <section class="finance-results card">
        <div class="section-title"><div><p class="eyebrow">Desempenho no período</p><h2>Vendas e custo das peças</h2><p>Margem bruta estimada: vendas confirmadas menos custo das peças vendidas.</p></div><span class="period-chip">{{ metrics.period_label }}</span></div>
        <div class="result-grid">
          <div class="result-metric"><span>Vendas confirmadas</span><strong>{{ metrics.revenue | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</strong></div>
          <div class="result-metric"><span>Custo das peças vendidas</span><strong>{{ metrics.net_cost_of_goods | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</strong></div>
          <div class="result-metric margin-metric"><span>Margem bruta estimada</span>@if (metrics.gross_margin !== null) { <strong>{{ metrics.gross_margin | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</strong><small>{{ metrics.gross_margin_percent | number:'1.0-1':'pt-BR' }}% das vendas</small> } @else { <strong class="margin-unavailable">Incompleta</strong><small>Falta custo histórico em vendas</small> }</div>
          <div class="result-metric returns-metric"><span>Devoluções ao estoque</span><strong>{{ metrics.return_value | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</strong><small>{{ metrics.return_quantity | number:'1.0-3':'pt-BR' }} unidades</small></div>
        </div>
        <div class="finance-chart-head"><div><strong>Movimentação financeira do estoque</strong><small>Valor de custo por dia · devoluções mostradas separadamente</small></div><div class="chart-legend"><span><i class="legend-in"></i>Entradas</span><span><i class="legend-out"></i>Saídas</span></div></div>
        <div class="finance-chart" role="img" [attr.aria-label]="chartDescription()">
          @if (hasChartData()) {
          @for (day of chartDays(); track day.date) {
            <div class="chart-day" [title]="chartTooltip(day)"><div class="chart-bars"><i class="bar-in" [style.height.%]="barHeight(day.inbound_value)"></i><i class="bar-out" [style.height.%]="barHeight(day.outbound_value)"></i></div><small>{{ day.label }}</small></div>
          }
          } @else { <p class="chart-empty">Sem movimentações de estoque neste período.</p> }
        </div>
      </section>

      <section class="finance-products card">
        <div class="section-title"><div><p class="eyebrow">Análise por produto</p><h2>Custo médio e movimentações</h2><p>O custo médio ponderado considera o saldo anterior e o valor de cada recebimento.</p></div><span class="result-count">{{ metrics.by_product.length }} {{ metrics.by_product.length === 1 ? 'peça' : 'peças' }}</span></div>
        @if (metrics.by_product.length) {
          <div class="product-table-wrap"><table><thead><tr><th>PEÇA / SKU</th><th>ESTOQUE</th><th>CUSTO MÉDIO</th><th>VALOR EM ESTOQUE</th><th>ENTRADAS</th><th>SAÍDAS</th><th>DEVOLUÇÕES</th></tr></thead><tbody>
            @for (product of metrics.by_product; track product.product_id) {
              <tr><td><strong>{{ product.name }}</strong><small>{{ product.sku }}</small></td><td>{{ product.current_stock | number:'1.0-3':'pt-BR' }} un.</td><td class="money-cell">{{ product.average_cost | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</td><td class="money-cell">{{ product.inventory_value | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</td><td><strong class="quantity-in">+{{ product.inbound_quantity | number:'1.0-3':'pt-BR' }}</strong><small>{{ product.inbound_value | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</small></td><td><strong class="quantity-out">−{{ product.outbound_quantity | number:'1.0-3':'pt-BR' }}</strong><small>{{ product.outbound_value | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</small></td><td><strong>{{ product.return_quantity | number:'1.0-3':'pt-BR' }}</strong><small>{{ product.return_value | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</small></td></tr>
            }
          </tbody></table></div>
          <div class="product-mobile-list">@for (product of metrics.by_product; track product.product_id) { <article class="product-mobile-card"><div class="mobile-product-title"><div><strong>{{ product.name }}</strong><small>{{ product.sku }}</small></div><span>{{ product.current_stock | number:'1.0-3':'pt-BR' }} un.</span></div><div class="mobile-cost-grid"><div><small>Custo médio</small><strong>{{ product.average_cost | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</strong></div><div><small>Estoque valorizado</small><strong>{{ product.inventory_value | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</strong></div><div><small>Entradas</small><strong class="quantity-in">+{{ product.inbound_quantity | number:'1.0-3':'pt-BR' }}</strong></div><div><small>Saídas</small><strong class="quantity-out">−{{ product.outbound_quantity | number:'1.0-3':'pt-BR' }}</strong></div><div><small>Devoluções</small><strong>{{ product.return_quantity | number:'1.0-3':'pt-BR' }}</strong></div></div></article> }</div>
        } @else { <div class="finance-empty"><strong>Nenhum produto com saldo ou movimentação</strong><span>Cadastre peças e registre recebimentos em Compras para começar a acompanhar custos.</span></div> }
      </section>
      <p class="finance-disclaimer">Entradas representam mercadorias recebidas, não pagamentos realizados ao fornecedor. Este painel ainda não é um fluxo de caixa nem substitui a conciliação contábil. O valor do estoque usa o custo médio atual.</p>
    }
  `,
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
  private readonly chartMax = computed(() => Math.max(1, ...this.chartDays().flatMap((day) => [day.inbound_value, day.outbound_value])));
  readonly hasChartData = computed(() => this.chartDays().some((day) => day.inbound_value > 0 || day.outbound_value > 0));

  ngOnInit() { this.load(); this.live.changes$.pipe(debounceTime(500), takeUntilDestroyed(this.destroyRef)).subscribe(() => this.load()); }
  applyPeriod(range: DateRange) { this.startDate.set(range.startDate); this.endDate.set(range.endDate); this.load(); }
  load() {
    this.loading.set(true); this.error.set('');
    this.api.financeOverview(this.startDate(), this.endDate()).pipe(finalize(() => this.loading.set(false))).subscribe({
      next: (result) => this.data.set(result),
      error: () => this.error.set('Não foi possível carregar as métricas financeiras. Tente novamente.'),
    });
  }
  barHeight(value: number) { return value > 0 ? Math.max(5, value / this.chartMax() * 100) : 0; }
  chartTooltip(day: FinanceDailyMetric) { return `${day.label}: entradas ${this.currency(day.inbound_value)} · saídas ${this.currency(day.outbound_value)}`; }
  chartDescription() { return `Gráfico de entradas e saídas por dia para ${this.data()?.period_label ?? 'o período selecionado'}.`; }
  private currency(value: number) { return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value); }
}
