import { CurrencyPipe, DatePipe, DecimalPipe, UpperCasePipe } from '@angular/common';
import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { debounceTime } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { LiveUpdatesService } from '../../core/live-updates.service';
import { AuthService } from '../../core/auth.service';
import { DashboardFinancialMetrics, DashboardSummary, Invoice } from '../../core/models';
import { canAdjustStock, canManageCatalog, canSell } from '../../core/user-access';
import { statusLabel, trackingEventLabel } from '../../core/status-labels';
import { PageHeader } from '../../shared/page-header';
import { PeriodFilter } from '../../shared/period-filter';
import { AfterSaleWorkflow } from '../../shared/after-sale-workflow';

@Component({
  selector: 'app-dashboard',
  imports: [CurrencyPipe, DatePipe, DecimalPipe, UpperCasePipe, RouterLink, PageHeader, PeriodFilter, AfterSaleWorkflow],
  template: `
    <app-page-header
      eyebrow="Centro de controle"
      title="Visão geral"
      subtitle="O pulso da sua operação, agora."
      >@if (canSell()) { <a class="primary" routerLink="/invoices">+ Nova venda</a> }</app-page-header
    >
    @if (data(); as summary) {
      <section class="metric-grid">
        <article class="metric featured metric-clickable" tabindex="0" role="button" (click)="openFinancial()" (keydown.enter)="openFinancial()" (keydown.space)="$event.preventDefault(); openFinancial()">
          <div>
            <span>Faturamento no período</span
            ><strong>{{ summary.revenue_month | currency: 'BRL' }}</strong>
          </div>
          <i>↗</i><small>Vendas confirmadas</small>
        </article>
        <article class="metric metric-clickable" tabindex="0" role="button" (click)="navigate('/invoices')" (keydown.enter)="navigate('/invoices')">
          <span>Vendas confirmadas</span><strong>{{ summary.confirmed_sales }}</strong
          ><small>{{ summary.cancelled_sales }} cancelada(s) · {{ summary.cancelled_amount | currency:'BRL' }} fora da receita</small>
        </article>
        <article class="metric metric-clickable" tabindex="0" role="button" (click)="navigate('/products')" (keydown.enter)="navigate('/products')">
          <span>Produtos ativos</span><strong>{{ summary.products_count }}</strong
          ><small>no catálogo</small>
        </article>
        <article class="metric metric-clickable" [class.warning]="summary.low_stock_count" tabindex="0" role="button" (click)="navigate('/products')" (keydown.enter)="navigate('/products')">
          <span>Estoque baixo</span><strong>{{ summary.low_stock_count }}</strong
          ><small>itens pedem atenção</small>
        </article>
      </section>
      <app-period-filter
        heading="Período da visão geral"
        description="Faturamento, vendas e vendas recentes"
        ariaLabel="Filtrar visão geral por período"
        [initialStartDate]="startDate"
        [initialEndDate]="endDate"
        (rangeChange)="applyDateFilter($event)"
      />
      <section class="dashboard-grid">
        <article class="card table-card">
          <div class="card-head">
            <div>
              <h2>Vendas recentes</h2>
              <p>Últimas movimentações da loja</p>
            </div>
            <a routerLink="/invoices">Ver todas →</a>
          </div>
          @if (summary.recent_invoices.length) {
            <div class="table-wrap">
              <table>
                <thead>
                  <tr><th>Fatura</th><th>Cliente</th><th>Origem</th><th>Emissão</th><th>Status</th><th>Documentos</th><th class="right">Total</th></tr>
                </thead>
                <tbody>
                  @for (invoice of summary.recent_invoices; track invoice.id) {
                    <tr class="clickable-row" (click)="openRecent(invoice)">
                      <td><strong>{{ invoice.number }}</strong><small class="block">{{ invoice.marketplace_order_id ? 'Pedido #' + invoice.marketplace_order_id : 'Venda local' }}</small></td>
                      <td class="dashboard-customer"><strong>{{ invoice.customer?.name || 'Consumidor não identificado' }}</strong><small>{{ invoice.customer?.document || invoice.customer?.email || 'Sem cadastro vinculado' }}</small></td>
                      <td>{{ invoice.source === 'mercadolivre' ? 'Mercado Livre' : 'Balcão' }}</td>
                      <td>{{ invoice.issued_at || invoice.created_at | date: 'dd/MM/yyyy HH:mm' }}</td>
                      <td><span class="badge" [class]="invoice.status">{{ status(invoice.status) }}</span>@if (invoice.after_sale) { <small class="post-sale-summary">{{ afterSaleLabel(invoice) }}</small> }</td>
                      <td>@if (invoice.documents.length) { @for (doc of invoice.documents; track doc.id) { <a class="doc" href="#" (click)="$event.preventDefault(); $event.stopPropagation(); openDocument(invoice.id, doc.id)">{{ doc.document_type | uppercase }}</a> } } @else { <span class="muted">—</span> }</td>
                      <td class="right"><strong>{{ invoice.total | currency: 'BRL' }}</strong></td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          } @else {
            <div class="empty">Nenhuma venda registrada ainda.</div>
          }
        </article>
        <aside class="card quick">
          <h2>Ações rápidas</h2>
          <p>Atalhos para o dia a dia</p>
          @if (canManageCatalog()) { <a routerLink="/products"
            ><span>◇</span>
            <div><strong>Cadastrar produto</strong><small>Adicione uma nova peça</small></div>
            <b>→</b></a
          > }
          @if (canAdjustStock()) { <a routerLink="/products"
            ><span>±</span>
            <div><strong>Ajustar estoque</strong><small>Entrada, perda ou inventário</small></div>
            <b>→</b></a
          > }
          <a routerLink="/marketplace"
            ><span>M</span>
            <div><strong>Revisar pedidos</strong><small>Acompanhe a conciliação</small></div>
            <b>→</b></a
          >
        </aside>
      </section>
      @if (financial(); as finance) {
        <div class="modal-backdrop" (click)="financial.set(null)">
          <section class="modal wide object-modal financial-modal" (click)="$event.stopPropagation()">
            <div class="modal-head financial-head"><div><p class="eyebrow">Financeiro · {{ finance.period_label }}</p><h2>Faturamento no período</h2><p class="detail-subtitle">Uma leitura rápida da receita, do ritmo de vendas e da composição do caixa.</p></div><button class="close" aria-label="Fechar métricas financeiras" (click)="financial.set(null)">×</button></div>
            <div class="financial-kpis"><div class="financial-kpi primary-kpi"><span>Receita confirmada</span><strong>{{ finance.revenue | currency:'BRL' }}</strong><small [class.positive-text]="finance.revenue_change_percent >= 0" [class.negative-text]="finance.revenue_change_percent < 0">{{ finance.revenue_change_percent >= 0 ? '↑' : '↓' }} {{ abs(finance.revenue_change_percent) | number:'1.0-2' }}% vs. período anterior</small></div><div class="financial-kpi"><span>Ticket médio</span><strong>{{ finance.average_ticket | currency:'BRL' }}</strong><small>{{ finance.sales_count }} vendas confirmadas</small></div><div class="financial-kpi"><span>Documentos emitidos</span><strong>{{ finance.documents_count }}</strong><small>Notas e arquivos da operação</small></div><div class="financial-kpi"><span>Pedidos cancelados</span><strong>{{ finance.cancelled_count }}</strong><small>no período</small></div><div class="financial-kpi"><span>Valor cancelado</span><strong>{{ finance.cancelled_amount | currency:'BRL' }}</strong><small>excluído da receita confirmada</small></div></div>
            <div class="financial-grid"><section class="financial-panel"><div class="section-heading"><div><p class="eyebrow">Ritmo de vendas</p><h3>Receita diária no período</h3></div><span class="muted">{{ finance.period_label }}</span></div><div class="revenue-chart" aria-label="Receita diária">@for (day of finance.daily; track day.date) { <div class="chart-column"><span class="chart-value">{{ day.amount | currency:'BRL':'symbol':'1.0-0' }}</span><div class="chart-track"><i [style.height.%]="chartHeight(day.amount, finance.daily)"></i></div><small>{{ day.label }}</small></div> }</div></section><section class="financial-panel"><div class="section-heading"><div><p class="eyebrow">Composição</p><h3>Por canal de venda</h3></div></div><div class="source-breakdown">@for (source of finance.by_source; track source.label) { <div><div class="source-row"><strong>{{ source.label }}</strong><span>{{ source.amount | currency:'BRL' }}</span></div><div class="source-bar"><i [style.width.%]="sourceWidth(source.amount, finance.revenue)"></i></div><small>{{ source.count }} venda(s)</small></div> } @empty { <p class="muted">Nenhuma venda confirmada no período.</p> }</div></section></div>
          </section>
        </div>
      }
      @if (detail(); as invoice) {
        <div class="modal-backdrop" (click)="detail.set(null)">
          <section class="modal wide object-modal" (click)="$event.stopPropagation()">
            <div class="modal-head detail-hero"><div><p class="eyebrow">Venda {{ invoice.source === 'mercadolivre' ? 'Mercado Livre' : 'manual' }}</p><h2>{{ invoice.number }}</h2><p class="detail-subtitle">Criada em {{ invoice.created_at | date:'dd/MM/yyyy HH:mm' }}{{ invoice.issued_at ? ' · emitida em ' + (invoice.issued_at | date:'dd/MM/yyyy HH:mm') : '' }}</p></div><div class="hero-actions"><span class="badge" [class]="invoice.status">{{ status(invoice.status) }}</span><button class="close" aria-label="Fechar detalhe" (click)="detail.set(null)">×</button></div></div>
            <div class="detail-summary"><div><span>Cliente</span><strong>{{ invoice.customer?.name || 'Consumidor não identificado' }}</strong><small>{{ invoice.customer?.document || invoice.customer?.email || 'Sem cadastro vinculado' }}</small></div><div><span>Pedido relacionado</span><strong>{{ invoice.marketplace_order_id ? '#' + invoice.marketplace_order_id : 'Venda local' }}</strong><small>{{ invoice.items.length }} item(ns) · {{ invoice.total | currency:'BRL' }}</small></div></div>
            <nav class="detail-tabs" aria-label="Detalhes da venda"><button [class.active]="invoiceTab() === 'items'" (click)="invoiceTab.set('items')">Itens <small>{{ invoice.items.length }}</small></button><button [class.active]="invoiceTab() === 'tracking'" (click)="invoiceTab.set('tracking')">Rastreio</button><button [class.active]="invoiceTab() === 'documents'" (click)="invoiceTab.set('documents')">Documentos <small>{{ invoice.documents.length }}</small></button>@if (invoice.after_sale) { <button [class.active]="invoiceTab() === 'aftersale'" (click)="invoiceTab.set('aftersale')">Pós-venda</button> }</nav>
            @if (invoiceTab() === 'items') { <section class="detail-section"><div class="section-heading"><div><p class="eyebrow">Composição</p><h3>Itens vendidos</h3></div><strong>{{ invoice.total | currency:'BRL' }}</strong></div><div class="invoice-detail-lines">@for (item of invoice.items; track item.id) { <div><span class="item-main"><strong>{{ item.description }}</strong><small>SKU {{ item.sku }} · {{ item.quantity }} unidade(s) · {{ item.unit_price | currency:'BRL' }} cada</small></span><strong>{{ item.total | currency:'BRL' }}</strong></div> }</div></section> }
            @if (invoiceTab() === 'tracking') { <section class="detail-section">@if (invoice.tracking; as tracking) { <div class="tracking-cards"><div><span>Status do pedido</span><strong>{{ statusLabel(tracking.status) }}</strong></div><div><span>Envio</span><strong>{{ statusLabel(tracking.shipping_status) }}</strong></div><div><span>Etiqueta</span><strong>{{ statusLabel(tracking.label_status) }}</strong></div><div><span>Código de rastreio</span><strong>{{ tracking.shipment_id || '—' }}</strong></div></div><div class="section-heading"><div><p class="eyebrow">Mercado Envios</p><h3>Linha do tempo do rastreio</h3></div><small>{{ tracking.last_update ? ('Atualizado ' + (tracking.last_update | date:'dd/MM/yyyy HH:mm')) : '' }}</small></div><div class="timeline">@for (event of tracking.history; track event.created_at + event.status) { <div><strong>{{ trackingEventLabel(event.status, event.detail) }}</strong><span>{{ event.created_at | date:'dd/MM/yyyy HH:mm' }}</span></div> } @empty { <p class="muted">Ainda não há eventos de rastreio registrados.</p> }</div> } @else { <div class="empty">Esta venda não está vinculada a um pedido de marketplace.</div> }</section> }
            @if (invoiceTab() === 'documents') { <section class="detail-section"><div class="section-heading"><div><p class="eyebrow">Fiscal</p><h3>Documentos da venda</h3></div><span class="muted">Clique para abrir em nova guia</span></div>@if (invoice.documents.length) { <div class="document-list">@for (doc of invoice.documents; track doc.id) { <a class="document-card" href="#" (click)="$event.preventDefault(); openDocument(invoice.id, doc.id)"><span class="document-icon">{{ doc.document_type === 'pdf' ? 'PDF' : 'XML' }}</span><span><strong>{{ doc.filename }}</strong><small>{{ doc.document_type === 'pdf' ? 'DANFE para visualização' : 'Nota fiscal eletrônica' }}</small></span><b>↗</b></a> }</div> } @else { <div class="empty">Nenhum documento anexado ainda.</div> }</section> }
            @if (invoiceTab() === 'aftersale' && invoice.after_sale) { <app-after-sale-workflow [afterSale]="invoice.after_sale" /> }
          </section>
        </div>
      }
    } @else {
      <div class="loading">Carregando sua operação…</div>
    }
  `,
  styleUrl: './dashboard.scss',
})
export class DashboardPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly live = inject(LiveUpdatesService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly auth = inject(AuthService);
  canSell() { return canSell(this.auth.user()?.role); }
  canManageCatalog() { return canManageCatalog(this.auth.user()?.role); }
  canAdjustStock() { return canAdjustStock(this.auth.user()?.role); }
  private readonly router = inject(Router);
  readonly data = signal<DashboardSummary | null>(null);
  readonly financial = signal<DashboardFinancialMetrics | null>(null);
  readonly detail = signal<Invoice | null>(null);
  readonly invoiceTab = signal<'items' | 'tracking' | 'documents' | 'aftersale'>('items');
  startDate = this.monthStart();
  endDate = this.today();
  readonly statusLabel = statusLabel;
  readonly trackingEventLabel = trackingEventLabel;
  afterSaleLabel(invoice: Invoice) {
    if (!invoice.after_sale) return '';
    const kind = invoice.after_sale.kind === 'return' ? 'Devolução' : invoice.after_sale.kind === 'claim' ? 'Reclamação' : 'Cancelamento';
    return `${kind} · ${statusLabel(invoice.after_sale.status)}`;
  }
  afterSaleReason(value: string) {
    if (value.trim().toLowerCase() === 'mediations cancel the order') return 'A mediação cancelou o pedido';
    return value;
  }
  requesterLabel(value: string) {
    return ({ meli: 'Mercado Livre', buyer: 'Comprador', seller: 'Vendedor' } as Record<string, string>)[value.toLowerCase()] ?? value;
  }
  ngOnInit() {
    this.load();
    this.live.changes$.pipe(debounceTime(250), takeUntilDestroyed(this.destroyRef)).subscribe(() => this.load());
  }
  load() {
    if (!this.validRange()) return;
    this.api.dashboard(this.startDate, this.endDate).subscribe((v) => this.data.set(v));
    const detailId = this.detail()?.id;
    if (detailId) this.api.invoice(detailId).subscribe((full) => {
      if (this.detail()?.id === detailId) this.detail.set(full);
    });
  }
  applyDateFilter(range: { startDate: string; endDate: string }) {
    this.startDate = range.startDate;
    this.endDate = range.endDate;
    this.load();
  }
  validRange() { return !!this.startDate && !!this.endDate && this.startDate <= this.endDate; }
  private today() { return new Date().toLocaleDateString('sv-SE'); }
  private monthStart() { return `${this.today().slice(0, 7)}-01`; }
  status(value: string) {
    return (
      (
        { draft: 'Rascunho', confirmed: 'Confirmada', cancelled: 'Cancelada' } as Record<
          string,
          string
        >
      )[value] ?? statusLabel(value)
    );
  }
  openRecent(invoice: Invoice) {
    this.invoiceTab.set('items');
    this.api.invoice(invoice.id).subscribe((full) => this.detail.set(full));
  }
  navigate(path: string) {
    void this.router.navigate([path]);
  }
  openFinancial() {
    this.api.dashboardFinancial(this.startDate, this.endDate).subscribe((metrics) => this.financial.set(metrics));
  }
  abs(value: number) {
    return Math.abs(value);
  }
  chartHeight(value: number, values: { amount: number }[]) {
    const max = Math.max(...values.map((item) => item.amount), 1);
    return value ? Math.max(8, (value / max) * 100) : 3;
  }
  sourceWidth(value: number, total: number) {
    return total ? Math.max(4, (value / total) * 100) : 0;
  }
  openDocument(invoiceId: string, documentId: string) {
    const preview = window.open('about:blank', '_blank');
    this.api.downloadInvoiceDocument(invoiceId, documentId).subscribe((blob) => {
      const url = URL.createObjectURL(blob);
      if (preview) {
        preview.opener = null;
        preview.location.href = url;
      }
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    });
  }
  documentViewerUrl(invoiceId: string, documentId: string) { return `/document-viewer/${invoiceId}/${documentId}`; }
}
