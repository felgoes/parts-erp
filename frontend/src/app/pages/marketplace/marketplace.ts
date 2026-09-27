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
              </tr>
            } @empty {
              <tr>
                <td colspan="5"><div class="empty">Os novos pedidos aparecerão aqui.</div></td>
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
}
