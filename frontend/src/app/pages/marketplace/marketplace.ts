import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { ApiService } from '../../core/api.service';
import { MarketplaceOrder, MarketplaceStatus } from '../../core/models';
import { PageHeader } from '../../shared/page-header';

@Component({
  selector: 'app-marketplace',
  imports: [DatePipe, PageHeader],
  template: `
    <app-page-header
      eyebrow="Marketplace"
      title="Pedidos do Mercado Livre"
      subtitle="Importação, conciliação e baixa automática de estoque."
      ><button class="secondary" (click)="load()">↻ Atualizar</button></app-page-header
    >
    @if (status(); as s) {
      @if (!s.connected) {
        <section class="notice">
          <span>M</span>
          <div>
            <strong>Conta ainda não conectada</strong>
            <p>Conecte sua conta para começar a receber pedidos automaticamente.</p>
          </div>
          <a class="primary" href="/integrations">Configurar integração</a>
        </section>
      } @else {
        <section class="connection">
          <span class="pulse"></span>
          <div>
            <strong>{{ s.nickname || 'Conta Mercado Livre' }}</strong
            ><small>Seller ID {{ s.seller_id }} · sincronização ativa</small>
          </div>
        </section>
      }
    }
    <section class="card table-card">
      <div class="card-head">
        <div>
          <h2>Fila de pedidos</h2>
          <p>Uma venda só baixa o estoque depois da conciliação do SKU.</p>
        </div>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Pedido</th>
              <th>Recebido</th>
              <th>Status no ML</th>
              <th>Sincronização</th>
              <th>Fatura</th>
              <th>NF-e</th>
              <th>Etiqueta</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            @for (o of orders(); track o.id) {
              <tr>
                <td>
                  <strong>#{{ o.external_order_id }}</strong>
                </td>
                <td>{{ o.created_at | date: 'dd/MM/yyyy HH:mm' }}</td>
                <td>{{ o.status }}</td>
                <td>
                  <span
                    class="badge"
                    [class.success]="o.sync_status === 'synced'"
                    [class.warning]="o.sync_status === 'pending'"
                    [class.cancelled]="o.sync_status === 'error'"
                    >{{ syncLabel(o.sync_status) }}</span
                  >
                  @if (o.sync_error) {
                    <small class="error-text">{{ o.sync_error }}</small>
                  }
                </td>
                <td>{{ o.invoice_id ? 'Gerada' : '—' }}</td>
                <td>
                  <span
                    class="badge"
                    [class.success]="o.fiscal_status === 'authorized'"
                    [class.cancelled]="o.fiscal_status === 'error'"
                    >{{ automationLabel(o.fiscal_status) }}</span
                  >
                  @if (o.fiscal_error) {
                    <small class="error-text">{{ o.fiscal_error }}</small>
                  }
                </td>
                <td>
                  <span
                    class="badge"
                    [class.success]="o.label_status === 'downloaded'"
                    [class.cancelled]="o.label_status === 'error'"
                    >{{ automationLabel(o.label_status) }}</span
                  >
                  @if (o.label_error) {
                    <small class="error-text">{{ o.label_error }}</small>
                  }
                </td>
                <td>
                  <button
                    class="secondary small"
                    [disabled]="!o.invoice_id || retrying() === o.id"
                    (click)="retry(o)"
                  >
                    {{ retrying() === o.id ? 'Tentando…' : 'Tentar agora' }}
                  </button>
                </td>
              </tr>
            } @empty {
              <tr>
                <td colspan="8"><div class="empty">Os novos pedidos aparecerão aqui.</div></td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    </section>
  `,
  styleUrl: './marketplace.scss',
})
export class MarketplacePage implements OnInit {
  private readonly api = inject(ApiService);
  readonly status = signal<MarketplaceStatus | null>(null);
  readonly orders = signal<MarketplaceOrder[]>([]);
  readonly retrying = signal<string | null>(null);
  ngOnInit() {
    this.load();
  }
  load() {
    this.api.marketplaceStatus().subscribe((v) => this.status.set(v));
    this.api.marketplaceOrders().subscribe((v) => this.orders.set(v));
  }
  syncLabel(s: string) {
    return (
      (
        { synced: 'Sincronizado', pending: 'Pendente', error: 'Requer atenção' } as Record<
          string,
          string
        >
      )[s] ?? s
    );
  }
  automationLabel(s: string) {
    return (
      (
        {
          authorized: 'Emitida',
          downloaded: 'Anexada',
          pending: 'Pendente',
          requesting: 'Solicitando',
          waiting: 'Aguardando envio',
          waiting_shipment: 'Sem envio',
          not_applicable: 'Não aplicável',
          error: 'Requer atenção',
        } as Record<string, string>
      )[s] ?? s
    );
  }
  retry(order: MarketplaceOrder) {
    this.retrying.set(order.id);
    this.api.automateMarketplaceOrder(order.id).subscribe({
      next: (updated) => {
        this.orders.update((orders) =>
          orders.map((item) => (item.id === updated.id ? updated : item)),
        );
        this.retrying.set(null);
      },
      error: () => this.retrying.set(null),
    });
  }
}
