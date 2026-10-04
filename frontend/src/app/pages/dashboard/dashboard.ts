import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/api.service';
import { DashboardSummary, Invoice } from '../../core/models';
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
            <div class="modal-head"><div><p class="eyebrow">Venda recente</p><h2>{{ invoice.number }}</h2></div><button class="close" (click)="detail.set(null)">×</button></div>
            <div class="detail-grid"><div><small>Status</small><strong>{{ status(invoice.status) }}</strong></div><div><small>Origem</small><strong>{{ invoice.source === 'mercadolivre' ? 'Mercado Livre' : 'Manual' }}</strong></div><div><small>Total</small><strong>{{ invoice.total | currency:'BRL' }}</strong></div></div>
            <h3>Itens vendidos</h3><div class="invoice-detail-lines">@for (item of invoice.items; track item.id) { <div><span><strong>{{ item.description }}</strong><small>{{ item.sku }} · {{ item.quantity }} un.</small></span><strong>{{ item.total | currency:'BRL' }}</strong></div> }</div>
            <h3>Documentos</h3>@for (doc of invoice.documents; track doc.id) { <button class="doc" (click)="download(invoice.id, doc.id, doc.filename)">{{ doc.document_type }} · {{ doc.filename }}</button> } @empty { <p class="muted">Nenhum documento anexado.</p> }
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
      )[value] ?? value
    );
  }
  openRecent(invoice: Invoice) {
    this.api.invoice(invoice.id).subscribe((full) => this.detail.set(full));
  }
  download(invoiceId: string, documentId: string, filename: string) {
    this.api.downloadInvoiceDocument(invoiceId, documentId).subscribe((blob) => {
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      URL.revokeObjectURL(url);
    });
  }
}
