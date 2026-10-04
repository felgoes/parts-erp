import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/api.service';
import { DashboardSummary, Invoice } from '../../core/models';
import { statusLabel, trackingEventLabel } from '../../core/status-labels';
import { PageHeader } from '../../shared/page-header';

@Component({
  selector: 'app-dashboard',
  imports: [CurrencyPipe, DatePipe, RouterLink, PageHeader],
  template: `
    <app-page-header
      eyebrow="Centro de controle"
      title="Visão geral"
      subtitle="O pulso da sua operação, agora."
      ><a class="primary" routerLink="/invoices">+ Nova venda</a></app-page-header
    >
    @if (data(); as summary) {
      <section class="metric-grid">
        <article class="metric featured">
          <div>
            <span>Faturamento no mês</span
            ><strong>{{ summary.revenue_month | currency: 'BRL' }}</strong>
          </div>
          <i>↗</i><small>Vendas confirmadas</small>
        </article>
        <article class="metric">
          <span>Vendas confirmadas</span><strong>{{ summary.confirmed_sales }}</strong
          ><small>neste mês</small>
        </article>
        <article class="metric">
          <span>Produtos ativos</span><strong>{{ summary.products_count }}</strong
          ><small>no catálogo</small>
        </article>
        <article class="metric" [class.warning]="summary.low_stock_count">
          <span>Estoque baixo</span><strong>{{ summary.low_stock_count }}</strong
          ><small>itens pedem atenção</small>
        </article>
      </section>
      <section class="dashboard-grid">
        <article class="card">
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
                  <tr>
                    <th>Fatura</th>
                    <th>Origem</th>
                    <th>Data</th>
                    <th>Status</th>
                    <th class="right">Total</th>
                  </tr>
                </thead>
                <tbody>
                  @for (invoice of summary.recent_invoices; track invoice.id) {
                    <tr class="clickable-row" (click)="openRecent(invoice)">
                      <td>
                        <strong>{{ invoice.number }}</strong>
                      </td>
                      <td>{{ invoice.source === 'mercadolivre' ? 'Mercado Livre' : 'Balcão' }}</td>
                      <td>{{ invoice.created_at | date: 'dd/MM, HH:mm' }}</td>
                      <td>
                        <span class="badge" [class]="invoice.status">{{
                          status(invoice.status)
                        }}</span>
                      </td>
                      <td class="right">
                        <strong>{{ invoice.total | currency: 'BRL' }}</strong>
                      </td>
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
          <a routerLink="/products"
            ><span>◇</span>
            <div><strong>Cadastrar produto</strong><small>Adicione uma nova peça</small></div>
            <b>→</b></a
          ><a routerLink="/products"
            ><span>±</span>
            <div><strong>Ajustar estoque</strong><small>Entrada, perda ou inventário</small></div>
            <b>→</b></a
          ><a routerLink="/marketplace"
            ><span>M</span>
            <div><strong>Revisar pedidos</strong><small>Acompanhe a conciliação</small></div>
            <b>→</b></a
          >
        </aside>
      </section>
      @if (detail(); as invoice) {
        <div class="modal-backdrop" (click)="detail.set(null)">
          <section class="modal wide" (click)="$event.stopPropagation()">
            <div class="modal-head detail-hero"><div><p class="eyebrow">Venda {{ invoice.source === 'mercadolivre' ? 'Mercado Livre' : 'manual' }}</p><h2>{{ invoice.number }}</h2><p class="detail-subtitle">Criada em {{ invoice.created_at | date:'dd/MM/yyyy HH:mm' }}{{ invoice.issued_at ? ' · emitida em ' + (invoice.issued_at | date:'dd/MM/yyyy HH:mm') : '' }}</p></div><div class="hero-actions"><span class="badge" [class]="invoice.status">{{ status(invoice.status) }}</span><button class="close" aria-label="Fechar detalhe" (click)="detail.set(null)">×</button></div></div>
            <div class="detail-summary"><div><span>Cliente</span><strong>{{ invoice.customer?.name || 'Consumidor não identificado' }}</strong><small>{{ invoice.customer?.document || invoice.customer?.email || 'Sem cadastro vinculado' }}</small></div><div><span>Pedido relacionado</span><strong>{{ invoice.marketplace_order_id ? '#' + invoice.marketplace_order_id : 'Venda local' }}</strong><small>{{ invoice.items.length }} item(ns) · {{ invoice.total | currency:'BRL' }}</small></div></div>
            <nav class="detail-tabs" aria-label="Detalhes da venda"><button [class.active]="invoiceTab() === 'items'" (click)="invoiceTab.set('items')">Itens <small>{{ invoice.items.length }}</small></button><button [class.active]="invoiceTab() === 'tracking'" (click)="invoiceTab.set('tracking')">Rastreio</button><button [class.active]="invoiceTab() === 'documents'" (click)="invoiceTab.set('documents')">Documentos <small>{{ invoice.documents.length }}</small></button></nav>
            @if (invoiceTab() === 'items') { <section class="detail-section"><div class="section-heading"><div><p class="eyebrow">Composição</p><h3>Itens vendidos</h3></div><strong>{{ invoice.total | currency:'BRL' }}</strong></div><div class="invoice-detail-lines">@for (item of invoice.items; track item.id) { <div><span class="item-main"><strong>{{ item.description }}</strong><small>SKU {{ item.sku }} · {{ item.quantity }} unidade(s) · {{ item.unit_price | currency:'BRL' }} cada</small></span><strong>{{ item.total | currency:'BRL' }}</strong></div> }</div></section> }
            @if (invoiceTab() === 'tracking') { <section class="detail-section">@if (invoice.tracking; as tracking) { <div class="tracking-cards"><div><span>Status do pedido</span><strong>{{ statusLabel(tracking.status) }}</strong></div><div><span>Envio</span><strong>{{ statusLabel(tracking.shipping_status) }}</strong></div><div><span>Etiqueta</span><strong>{{ statusLabel(tracking.label_status) }}</strong></div><div><span>Código de rastreio</span><strong>{{ tracking.shipment_id || '—' }}</strong></div></div><div class="section-heading"><div><p class="eyebrow">Mercado Envios</p><h3>Linha do tempo do rastreio</h3></div><small>{{ tracking.last_update ? ('Atualizado ' + (tracking.last_update | date:'dd/MM/yyyy HH:mm')) : '' }}</small></div><div class="timeline">@for (event of tracking.history; track event.created_at + event.status) { <div><strong>{{ trackingEventLabel(event.status, event.detail) }}</strong><span>{{ event.created_at | date:'dd/MM/yyyy HH:mm' }}</span></div> } @empty { <p class="muted">Ainda não há eventos de rastreio registrados.</p> }</div> } @else { <div class="empty">Esta venda não está vinculada a um pedido de marketplace.</div> }</section> }
            @if (invoiceTab() === 'documents') { <section class="detail-section"><div class="section-heading"><div><p class="eyebrow">Fiscal</p><h3>Documentos da venda</h3></div><span class="muted">Clique para abrir em nova guia</span></div>@if (invoice.documents.length) { <div class="document-list">@for (doc of invoice.documents; track doc.id) { <button class="document-card" (click)="openDocument(invoice.id, doc.id)"><span class="document-icon">{{ doc.document_type === 'pdf' ? 'PDF' : 'XML' }}</span><span><strong>{{ doc.filename }}</strong><small>{{ doc.document_type === 'pdf' ? 'DANFE para visualização' : 'Nota fiscal eletrônica' }}</small></span><b>↗</b></button> }</div> } @else { <div class="empty">Nenhum documento anexado ainda.</div> }</section> }
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
  readonly data = signal<DashboardSummary | null>(null);
  readonly detail = signal<Invoice | null>(null);
  readonly invoiceTab = signal<'items' | 'tracking' | 'documents'>('items');
  readonly statusLabel = statusLabel;
  readonly trackingEventLabel = trackingEventLabel;
  ngOnInit() {
    this.api.dashboard().subscribe((v) => this.data.set(v));
  }
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
  openDocument(invoiceId: string, documentId: string) {
    this.api.downloadInvoiceDocument(invoiceId, documentId).subscribe((blob) => {
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank', 'noopener,noreferrer');
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    });
  }
}
