import { DatePipe, JsonPipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { ApiService } from '../../core/api.service';
import { MarketplaceOrder, MarketplaceOrderEvent, MarketplaceStatus } from '../../core/models';
import { PageHeader } from '../../shared/page-header';

@Component({
  selector: 'app-marketplace',
  imports: [DatePipe, JsonPipe, PageHeader],
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
                  <button class="link-button" (click)="openDetails(o)">#{{ o.external_order_id }}</button>
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
    @if (detail(); as order) {
      <div class="modal-backdrop" (click)="detail.set(null)">
        <section class="modal wide" (click)="$event.stopPropagation()">
          <div class="modal-head"><div><p class="eyebrow">Pedido Mercado Livre</p><h2>#{{ order.external_order_id }}</h2></div><button class="close" (click)="detail.set(null)">×</button></div>
          <div class="detail-grid"><div><small>Status no ML</small><strong>{{ order.status }}</strong></div><div><small>Sincronização</small><strong>{{ syncLabel(order.sync_status) }}</strong></div><div><small>Envio</small><strong>{{ order.shipping_status || 'Não informado' }}</strong></div><div><small>NF-e</small><strong>{{ automationLabel(order.fiscal_status) }}</strong></div><div><small>Etiqueta</small><strong>{{ automationLabel(order.label_status) }}</strong></div><div><small>Fatura</small><strong>{{ order.invoice_id ? 'Vinculada' : 'Não gerada' }}</strong></div></div>
          <h3>Rastreamento e etapas</h3><div class="timeline"><div><strong>Pedido recebido</strong><span>{{ order.created_at | date:'dd/MM/yyyy HH:mm' }}</span></div><div><strong>Status atual: {{ order.status }}</strong><span>{{ order.synchronized_at ? (order.synchronized_at | date:'dd/MM/yyyy HH:mm') : 'Ainda não sincronizado' }}</span></div>@if (order.payload?.['shipping']) { <div><strong>Envio {{ order.payload?.['shipping']?.['id'] || '' }}</strong><span>{{ order.payload?.['shipping']?.['status'] || order.shipping_status || 'Em processamento' }}</span></div> }</div>
          <h3>Histórico de status</h3>@if (history().length) { <div class="timeline">@for (event of history(); track event.id) { <div><strong>{{ event.status }}{{ event.detail ? ' · ' + event.detail : '' }}</strong><span>{{ event.created_at | date:'dd/MM/yyyy HH:mm' }}</span></div> }</div> } @else { <p class="muted">Nenhum evento histórico registrado.</p> }
          <h3>Devolução/cancelamento</h3>@if (order.status === 'cancelled' || order.payload?.['status'] === 'cancelled' || order.payload?.['returns']) { @if (order.payload?.['cancel_detail']) { <div class="detail-grid"><div><small>Motivo</small><strong>{{ order.payload?.['cancel_detail']?.['description'] || 'Não informado' }}</strong></div><div><small>Solicitado por</small><strong>{{ order.payload?.['cancel_detail']?.['requested_by'] || 'Não informado' }}</strong></div><div><small>Pagamento</small><strong>{{ order.payload?.['payments']?.[0]?.['status'] || 'Não informado' }}</strong></div></div> } <pre class="payload">{{ order.payload?.['returns'] || order.payload?.['cancellations'] || order.payload | json }}</pre> } @else { <p class="muted">Nenhuma devolução ou cancelamento registrado neste pedido.</p> }
          @if (order.sync_error || order.fiscal_error || order.label_error) { <h3>Ocorrências</h3><p class="error-text">{{ order.sync_error || order.fiscal_error || order.label_error }}</p> }
        </section>
      </div>
    }
  `,
  styleUrl: './marketplace.scss',
})
export class MarketplacePage implements OnInit {
  private readonly api = inject(ApiService);
  readonly status = signal<MarketplaceStatus | null>(null);
  readonly orders = signal<MarketplaceOrder[]>([]);
  readonly retrying = signal<string | null>(null);
  readonly detail = signal<MarketplaceOrder | null>(null);
  readonly history = signal<MarketplaceOrderEvent[]>([]);
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
  openDetails(order: MarketplaceOrder) {
    this.history.set([]);
    this.api.marketplaceOrder(order.id).subscribe((full) => this.detail.set(full));
    this.api.marketplaceOrderHistory(order.id).subscribe((events) => this.history.set(events));
  }
}
