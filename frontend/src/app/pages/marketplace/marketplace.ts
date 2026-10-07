import { DatePipe, DecimalPipe, JsonPipe, UpperCasePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { ApiService } from '../../core/api.service';
import { LiveUpdatesService } from '../../core/live-updates.service';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { debounceTime } from 'rxjs';
import { AuthService } from '../../core/auth.service';
import { MarketplaceOrder, MarketplaceOrderEvent, MarketplaceStatus } from '../../core/models';
import { statusLabel, trackingEventLabel } from '../../core/status-labels';
import { PageHeader } from '../../shared/page-header';

@Component({
  selector: 'app-marketplace',
  imports: [DatePipe, DecimalPipe, JsonPipe, UpperCasePipe, PageHeader],
  template: `
    <app-page-header
      eyebrow="Marketplace"
      title="Pedidos do Mercado Livre"
      subtitle="Importação, conciliação e baixa automática de estoque."
    >
      @if (canProcess()) {
        <button
          class="secondary"
          [disabled]="syncing() || status()?.connected !== true"
          (click)="syncNow()"
        >
          {{ syncing() ? 'Enviando sincronização…' : 'Sincronizar agora' }}
        </button>
      }
    </app-page-header>
    @if (feedback(); as toast) {
      <div class="toast-host">
        <div
          class="toast"
          [class.toast-error]="toast.kind === 'error'"
          [class.toast-info]="toast.kind === 'info'"
          [attr.role]="toast.kind === 'error' ? 'alert' : 'status'"
        >
          <span class="toast-indicator" aria-hidden="true"></span>
          <p>{{ toast.message }}</p>
          <button
            class="toast-close"
            type="button"
            aria-label="Fechar aviso"
            (click)="dismissFeedback()"
          >
            ×
          </button>
        </div>
      </div>
    }
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
            </tr>
          </thead>
          <tbody>
            @for (o of orders(); track o.id) {
              <tr class="clickable-row" (click)="openDetails(o)">
                <td>
                  <button class="link-button" (click)="openDetails(o)">
                    #{{ o.external_order_id }}
                  </button>
                </td>
                <td>{{ (platformCreatedAt(o) || o.created_at) | date: 'dd/MM/yyyy HH:mm' }}</td>
                <td>
                  {{ statusLabel(o.status) }}
                  @if (o.shipping_status) {
                    <small class="block">{{ trackingEventLabel(o.shipping_status, o.shipping_substatus) }}</small>
                  }
                </td>
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
                  @if (documentFor(o, 'pdf'); as fiscalPdf) {
                    <button
                      class="document-action"
                      (click)="
                        $event.stopPropagation();
                        download(o.invoice_id!, fiscalPdf.id, fiscalPdf.filename)
                      "
                    >
                      Abrir NF-e <span>↗</span>
                    </button>
                  } @else if (documentFor(o, 'xml'); as fiscalXml) {
                    <button
                      class="document-action"
                      (click)="
                        $event.stopPropagation();
                        download(o.invoice_id!, fiscalXml.id, fiscalXml.filename)
                      "
                    >
                      Abrir XML <span>↗</span>
                    </button>
                  } @else if (canRequestInvoice(o)) {
                    <button
                      class="secondary small"
                      [disabled]="isWorking(o.id)"
                      (click)="$event.stopPropagation(); requestInvoice(o)"
                    >
                      {{ fiscalActionLabel(o) }}
                    </button>
                  }
                </td>
                <td>
                  <span
                    class="badge"
                    [class.success]="o.label_status === 'downloaded'"
                    [class.cancelled]="o.label_status === 'error'"
                    [class.warning]="o.label_status === 'waiting'"
                    >{{ labelStatusLabel(o) }}</span
                  >
                  @if (o.label_error) {
                    <small class="error-text">{{ o.label_error }}</small>
                  }
                  @if (documentFor(o, 'label_pdf'); as labelPdf) {
                    <button
                      class="document-action"
                      (click)="
                        $event.stopPropagation();
                        download(o.invoice_id!, labelPdf.id, labelPdf.filename)
                      "
                    >
                      Baixar etiqueta <span>↗</span>
                    </button>
                  } @else if (canGetLabel(o)) {
                    <button
                      class="secondary small"
                      [disabled]="isWorking(o.id)"
                      (click)="$event.stopPropagation(); retryLabel(o)"
                    >
                      {{ isWorking(o.id, 'label') ? 'Preparando…' : 'Preparar etiqueta' }}
                    </button>
                  }
                </td>
              </tr>
            } @empty {
              <tr>
                <td colspan="7"><div class="empty">Os novos pedidos aparecerão aqui.</div></td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    </section>
    @if (detail(); as order) {
      <div class="modal-backdrop" (click)="detail.set(null)">
        <section class="modal wide object-modal" (click)="$event.stopPropagation()">
          <div class="modal-head object-hero">
            <div>
              <p class="eyebrow">Marketplace · Pedido Mercado Livre</p>
              <h2>#{{ order.external_order_id }}</h2>
              <p class="detail-subtitle">
                Recebido em {{ (platformCreatedAt(order) || order.created_at) | date: 'dd/MM/yyyy HH:mm' }}
              </p>
            </div>
            <div class="object-hero-actions">
              <span
                class="badge"
                [class.cancelled]="order.status === 'cancelled'"
                [class.success]="order.status === 'paid'"
                >{{ statusLabel(order.status) }}</span
              ><button class="close" aria-label="Fechar pedido" (click)="detail.set(null)">
                ×
              </button>
            </div>
          </div>
          <div class="detail-grid">
            <div>
              <small>Status no ML</small><strong>{{ statusLabel(order.status) }}</strong>
            </div>
            <div>
              <small>Sincronização</small><strong>{{ syncLabel(order.sync_status) }}</strong>
            </div>
            <div>
              <small>Envio</small><strong>{{ trackingEventLabel(order.shipping_status || 'unknown', order.shipping_substatus) }}</strong>
            </div>
            <div>
              <small>NF-e</small><strong>{{ automationLabel(order.fiscal_status) }}</strong>
            </div>
            <div>
              <small>Etiqueta</small><strong>{{ labelStatusLabel(order) }}</strong>
            </div>
            <div>
              <small>Fatura</small
              ><strong>{{ order.invoice_id ? 'Vinculada' : 'Não gerada' }}</strong>
            </div>
          </div>
          @if (canProcess()) {
            <section class="fulfillment-panel" aria-label="Documentos e expedição do pedido">
              <div class="fulfillment-heading">
                <div>
                  <p class="eyebrow">Próximas etapas</p>
                  <h3>Documentos e expedição</h3>
                </div>
              </div>
              <div class="fulfillment-grid">
                <article class="fulfillment-card">
                  <div class="fulfillment-card-heading">
                    <span class="fulfillment-icon fiscal-icon" aria-hidden="true">NF</span>
                    <div>
                      <h4>Nota fiscal</h4>
                      <span class="fulfillment-state">{{ automationLabel(order.fiscal_status) }}</span>
                    </div>
                  </div>
                  <p class="fulfillment-help">
                    Documento fiscal vinculado à venda e usado para liberar o envio quando exigido.
                  </p>
                  <div class="fulfillment-control">
                    @if (documentFor(order, 'pdf'); as fiscalPdf) {
                      <button
                        class="primary small"
                        (click)="download(order.invoice_id!, fiscalPdf.id, fiscalPdf.filename)"
                      >
                        Abrir NF-e <span>↗</span>
                      </button>
                    } @else if (documentFor(order, 'xml'); as fiscalXml) {
                      <button
                        class="primary small"
                        (click)="download(order.invoice_id!, fiscalXml.id, fiscalXml.filename)"
                      >
                        Abrir XML <span>↗</span>
                      </button>
                    } @else if (canRequestInvoice(order)) {
                      <button
                        class="primary small"
                        [disabled]="isWorking(order.id)"
                        (click)="requestInvoice(order)"
                      >
                        {{ isWorking(order.id, 'fiscal') ? 'Consultando…' : fiscalActionLabel(order) }}
                      </button>
                    } @else {
                      <span class="muted">Sem documento fiscal vinculado</span>
                    }
                  </div>
                </article>
                <article class="fulfillment-card">
                  <div class="fulfillment-card-heading">
                    <span class="fulfillment-icon label-icon" aria-hidden="true">ET</span>
                    <div>
                      <h4>Etiqueta de envio</h4>
                      <span class="fulfillment-state">{{ labelStatusLabel(order) }}</span>
                    </div>
                  </div>
                  <p class="fulfillment-help">{{ labelStatusHelp(order) }}</p>
                  <div class="fulfillment-control">
                    @if (documentFor(order, 'label_pdf'); as labelPdf) {
                      <button
                        class="secondary small"
                        (click)="download(order.invoice_id!, labelPdf.id, labelPdf.filename)"
                      >
                        Abrir etiqueta <span>↗</span>
                      </button>
                    } @else if (canGetLabel(order)) {
                      <button
                        class="secondary small"
                        [disabled]="isWorking(order.id)"
                        (click)="retryLabel(order)"
                      >
                        {{ isWorking(order.id, 'label') ? 'Preparando…' : 'Obter etiqueta' }}
                      </button>
                    } @else {
                      <span class="muted fulfillment-unavailable">Indisponível no momento</span>
                    }
                  </div>
                </article>
              </div>
            </section>
          }
          @if (order.invoice; as invoice) {
            <section class="order-section">
              <div class="section-heading">
                <div>
                  <p class="eyebrow">Comercial</p>
                  <h3>Fatura e itens</h3>
                </div>
                <strong>{{ invoice.total | number: '1.2-2' }}</strong>
              </div>
              <div class="invoice-detail-lines">
                @for (item of invoice.items; track item.id) {
                  <div>
                    <span
                      ><strong>{{ item.description }}</strong
                      ><small
                        >{{ item.sku }} · {{ item.quantity }} unidade(s) ·
                        {{ item.unit_price | number: '1.2-2' }} cada</small
                      ></span
                    ><strong>{{ item.total | number: '1.2-2' }}</strong>
                  </div>
                }
              </div>
              <div class="detail-documents">
                <span class="documents-label">Arquivos do pedido</span>
                @for (doc of invoice.documents; track doc.id) {
                  <button class="doc" (click)="download(order.invoice_id!, doc.id, doc.filename)">
                    <span>{{ doc.document_type | uppercase }}</span
                    >{{ doc.filename }}<b>↗</b>
                  </button>
                } @empty {
                  <span class="muted">Nenhum documento anexado à fatura.</span>
                }
              </div>
            </section>
          }
          <section class="order-section">
            <div class="section-heading">
              <div>
                <p class="eyebrow">Mercado Envios</p>
                <h3>Rastreamento e etapas</h3>
              </div>
              <span class="muted">{{
                (platformUpdatedAt(order) || order.synchronized_at)
                  ? 'Atualizado ' + ((platformUpdatedAt(order) || order.synchronized_at) | date: 'dd/MM/yyyy HH:mm')
                  : 'Aguardando sincronização'
              }}</span>
            </div>
            <div class="timeline">
              <div>
                <strong>Pedido recebido</strong
                ><span>{{ order.created_at | date: 'dd/MM/yyyy HH:mm' }}</span>
              </div>
              <div>
                <strong>Status do pedido: {{ statusLabel(order.status) }}</strong
                ><span>{{
                  (platformUpdatedAt(order) || order.synchronized_at)
                    ? ((platformUpdatedAt(order) || order.synchronized_at) | date: 'dd/MM/yyyy HH:mm')
                    : 'Ainda não sincronizado'
                }}</span>
              </div>
              @if (order.shipment_id) {
                <div>
                  <strong>Envio {{ order.shipment_id }}</strong
                  ><span>{{ trackingEventLabel(order.shipping_status || 'unknown', order.shipping_substatus) }}</span>
                </div>
              }
            </div>
          </section>
          <section class="order-section">
            <div class="section-heading">
              <div>
                <p class="eyebrow">Histórico</p>
                <h3>Histórico de status</h3>
              </div>
            </div>
            @if (history().length) {
              <div class="timeline">
                @for (event of history(); track event.id) {
                  <div>
                    <strong>{{ trackingEventLabel(event.status, event.detail) }}</strong
                    ><span>{{ event.created_at | date: 'dd/MM/yyyy HH:mm' }}</span>
                  </div>
                }
              </div>
            } @else {
              <p class="muted">Nenhum evento histórico registrado.</p>
            }
          </section>
          <section class="order-section">
            <div class="section-heading">
              <div>
                <p class="eyebrow">Pós-venda</p>
                <h3>Devolução ou cancelamento</h3>
              </div>
            </div>
            @if (
              order.status === 'cancelled' ||
              order.payload?.['status'] === 'cancelled' ||
              order.payload?.['returns']
            ) {
              @if (order.payload?.['cancel_detail']) {
                <div class="detail-grid">
                  <div>
                    <small>Motivo</small
                    ><strong>{{
                      cancelReason(order.payload?.['cancel_detail']?.['description'])
                    }}</strong>
                  </div>
                  <div>
                    <small>Solicitado por</small
                    ><strong>{{
                      cancelRequester(order.payload?.['cancel_detail']?.['requested_by'])
                    }}</strong>
                  </div>
                  <div>
                    <small>Pagamento</small
                    ><strong>{{
                      statusLabel(order.payload?.['payments']?.[0]?.['status'])
                    }}</strong>
                  </div>
                </div>
              }
              <details class="technical-details">
                <summary>Ver dados técnicos do Mercado Livre</summary>
                <pre class="payload">{{
                  order.payload?.['returns'] || order.payload?.['cancellations'] || order.payload
                    | json
                }}</pre>
              </details>
            } @else {
              <p class="muted">Nenhuma devolução ou cancelamento registrado neste pedido.</p>
            }
          </section>
          @if (order.sync_error || order.fiscal_error || order.label_error) {
            <section class="order-section">
              <div class="section-heading">
                <div>
                  <p class="eyebrow">Atenção</p>
                  <h3>Ocorrências</h3>
                </div>
              </div>
              <p class="error-text">
                {{ order.sync_error || order.fiscal_error || order.label_error }}
              </p>
            </section>
          }
        </section>
      </div>
    }
  `,
  styleUrl: './marketplace.scss',
})
export class MarketplacePage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly live = inject(LiveUpdatesService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly auth = inject(AuthService);
  readonly status = signal<MarketplaceStatus | null>(null);
  readonly orders = signal<MarketplaceOrder[]>([]);
  readonly syncing = signal(false);
  readonly feedback = signal<{ kind: 'success' | 'error' | 'info'; message: string } | null>(null);
  readonly working = signal<{ id: string; kind: 'fiscal' | 'label' } | null>(null);
  readonly detail = signal<MarketplaceOrder | null>(null);
  readonly history = signal<MarketplaceOrderEvent[]>([]);
  readonly statusLabel = statusLabel;
  readonly trackingEventLabel = trackingEventLabel;
  platformCreatedAt(order: MarketplaceOrder): string | number | null {
    const payload = order.payload || {};
    const value = payload['date_created'] ?? payload['create_time'];
    if (value === undefined || value === null || value === '') return null;
    if (order.provider === 'shopee' && /^\d+$/.test(String(value))) return Number(value) * 1000;
    return String(value);
  }
  platformUpdatedAt(order: MarketplaceOrder): string | number | null {
    const payload = order.payload || {};
    const value = payload['last_updated'] ?? payload['update_time'] ?? payload['_erp_source_updated_at'];
    if (value === undefined || value === null || value === '') return null;
    if (order.provider === 'shopee' && /^\d+$/.test(String(value))) return Number(value) * 1000;
    return String(value);
  }
  canProcess() {
    const role = this.auth.user()?.role;
    return role === 'admin' || role === 'manager';
  }
  ngOnInit() {
    this.load();
    this.live.changes$.pipe(debounceTime(250), takeUntilDestroyed(this.destroyRef)).subscribe(() => this.load());
  }
  load() {
    this.api.marketplaceStatus().subscribe((v) => this.status.set(v));
    this.api.marketplaceOrders().subscribe({
      next: (v) => this.orders.set(v),
      error: () =>
        this.showFeedback('error', 'Não foi possível carregar os pedidos do Mercado Livre.'),
    });
    const openOrderId = this.detail()?.id;
    if (openOrderId) {
      this.api.marketplaceOrder(openOrderId).subscribe((full) => {
        if (this.detail()?.id === openOrderId) this.detail.set(full);
      });
      this.api.marketplaceOrderHistory(openOrderId).subscribe((events) => {
        if (this.detail()?.id === openOrderId) this.history.set(events);
      });
    }
  }
  syncNow() {
    this.syncing.set(true);
    this.dismissFeedback();
    this.api.syncMarketplace().subscribe({
      next: (result) => {
        this.syncing.set(false);
        this.showFeedback(
          result.accepted ? 'success' : 'error',
          result.accepted
            ? 'Busca enviada ao Mercado Livre. Os pedidos serão atualizados assim que a importação terminar.'
            : 'A sincronização não foi iniciada. Tente novamente.',
        );
        if (!result.accepted) return;
        const refreshUntil = Date.now() + 60_000;
        const refresh = () => {
          this.load();
          if (Date.now() < refreshUntil) window.setTimeout(refresh, 5_000);
        };
        window.setTimeout(refresh, 3_000);
      },
      error: (error: { error?: { detail?: unknown } }) => {
        this.syncing.set(false);
        const detail = error.error?.detail;
        this.showFeedback(
          'error',
          typeof detail === 'string'
            ? detail
            : 'Não foi possível iniciar a sincronização. Verifique a conexão com o Mercado Livre e tente novamente.',
        );
      },
    });
  }
  syncLabel(s: string) {
    return (
      (
        { synced: 'Sincronizado', pending: 'Pendente', error: 'Requer atenção' } as Record<
          string,
          string
        >
      )[s] ?? statusLabel(s)
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
          waiting: 'Aguardando liberação',
          waiting_shipment: 'Sem envio',
          completed: 'Etapa concluída',
          not_applicable: 'Não aplicável',
          error: 'Requer atenção',
        } as Record<string, string>
      )[s] ?? statusLabel(s)
    );
  }
  cancelReason(value: unknown) {
    const reason = String(value || '').trim();
    if (!reason) return 'Não informado';
    const normalized = reason.toLowerCase();
    if (normalized === 'mediations cancel the order') return 'A mediação cancelou o pedido';
    if (normalized.includes('buyer')) return reason.replace(/buyer/gi, 'comprador');
    if (normalized.includes('seller')) return reason.replace(/seller/gi, 'vendedor');
    return reason;
  }
  cancelRequester(value: unknown) {
    const requester = String(value || '')
      .trim()
      .toLowerCase();
    return (
      ({ meli: 'Mercado Livre', buyer: 'Comprador', seller: 'Vendedor' } as Record<string, string>)[
        requester
      ] ?? (requester ? this.cancelReason(requester) : 'Não informado')
    );
  }
  isWorking(id: string, kind?: 'fiscal' | 'label') {
    const current = this.working();
    return current?.id === id && (!kind || current.kind === kind);
  }
  documentFor(order: MarketplaceOrder, documentType: string) {
    return order.invoice?.documents.find((document) => document.document_type === documentType);
  }
  canRequestInvoice(order: MarketplaceOrder) {
    return (
      this.canProcess() &&
      Boolean(order.invoice_id) &&
      order.status !== 'cancelled' &&
      order.status !== 'canceled' &&
      order.fiscal_status !== 'authorized'
    );
  }
  fiscalActionLabel(order: MarketplaceOrder) {
    if (this.isWorking(order.id, 'fiscal')) return 'Consultando…';
    return order.external_invoice_id ? 'Verificar NF-e' : 'Solicitar NF-e';
  }
  canGetLabel(order: MarketplaceOrder) {
    return this.canProcess() && this.isLabelAvailable(order);
  }
  isLabelAvailable(order: MarketplaceOrder) {
    const terminalStatuses = ['delivered', 'shipped', 'cancelled', 'canceled'];
    const finishedLabels = ['downloaded', 'completed', 'not_applicable'];
    return (
      Boolean(order.invoice_id) &&
      !['cancelled', 'canceled'].includes(order.status.toLowerCase()) &&
      !terminalStatuses.includes(order.shipping_status?.toLowerCase() ?? '') &&
      order.shipping_status === 'ready_to_ship' &&
      ['ready_to_print', 'printed'].includes(order.shipping_substatus ?? '') &&
      !finishedLabels.includes(order.label_status)
    );
  }
  labelStatusLabel(order: MarketplaceOrder) {
    if (this.documentFor(order, 'label_pdf')) return 'Anexada à fatura';
    if (order.shipping_substatus === 'invoice_pending') return 'Aguardando NF-e/DC-e';
    if (order.shipping_substatus === 'waiting_for_label_generation') {
      return 'Gerando no Mercado Livre';
    }
    if (this.isLabelAvailable(order)) return 'Pronta para obter';
    if (['delivered', 'shipped', 'returned', 'not_delivered'].includes(order.shipping_status ?? '')) {
      return 'Etapa de envio encerrada';
    }
    return this.automationLabel(order.label_status);
  }
  labelStatusHelp(order: MarketplaceOrder) {
    if (this.documentFor(order, 'label_pdf')) {
      return 'Arquivo salvo na fatura. Abra por aqui quando precisar.';
    }
    if (order.shipping_substatus === 'invoice_pending') {
      return 'O Mercado Livre libera a etiqueta depois que a NF-e ou DC-e for emitida/importada.';
    }
    if (order.shipping_substatus === 'waiting_for_label_generation') {
      return 'O Mercado Livre ainda está preparando o arquivo. Atualize o pedido em instantes.';
    }
    if (this.isLabelAvailable(order)) {
      return 'A etiqueta já está liberada. Ao obter, o PDF será anexado à fatura.';
    }
    if (['delivered', 'shipped', 'returned', 'not_delivered'].includes(order.shipping_status ?? '')) {
      return 'O pedido já passou da etapa de impressão da etiqueta.';
    }
    if (order.label_status === 'error') {
      return 'Não foi possível obter o arquivo. Confira o status no Mercado Livre e tente novamente.';
    }
    if (!order.shipment_id) return 'O Mercado Livre ainda não associou um envio a este pedido.';
    return 'A etiqueta ainda não foi liberada pelo Mercado Livre.';
  }
  requestInvoice(order: MarketplaceOrder) {
    if (
      !window.confirm(
        `Solicitar ao Mercado Livre a emissão da NF-e do pedido #${order.external_order_id}?`,
      )
    ) {
      return;
    }
    this.runOrderAction(order, 'fiscal');
  }
  retryLabel(order: MarketplaceOrder) {
    this.runOrderAction(order, 'label');
  }
  private runOrderAction(order: MarketplaceOrder, kind: 'fiscal' | 'label') {
    this.working.set({ id: order.id, kind });
    this.dismissFeedback();
    const request =
      kind === 'fiscal'
        ? this.api.requestMarketplaceInvoice(order.id)
        : this.api.retryMarketplaceLabel(order.id);
    request.subscribe({
      next: (updated) => {
        this.orders.update((orders) =>
          orders.map((item) => (item.id === updated.id ? updated : item)),
        );
        if (this.detail()?.id === updated.id) this.detail.set(updated);
        if (kind === 'fiscal') {
          this.showFeedback(
            'success',
            updated.fiscal_status === 'authorized'
              ? 'NF-e encontrada e vinculada à fatura.'
              : 'Solicitação enviada ao Mercado Livre; acompanhe o status neste pedido.',
          );
        } else {
          this.showFeedback(
            updated.label_status === 'downloaded' ? 'success' : 'info',
            updated.label_status === 'downloaded'
              ? 'Etiqueta anexada à fatura. Você já pode abri-la nesta tela.'
              : this.labelStatusHelp(updated),
          );
        }
        this.working.set(null);
      },
      error: (error: unknown) => {
        const detail =
          error instanceof HttpErrorResponse
            ? error.error?.detail || error.message
            : 'Não foi possível concluir a ação. Tente novamente.';
        this.showFeedback('error', String(detail));
        this.working.set(null);
      },
    });
  }
  showFeedback(kind: 'success' | 'error' | 'info', message: string) {
    this.feedback.set({ kind, message });
  }
  dismissFeedback() {
    this.feedback.set(null);
  }
  openDetails(order: MarketplaceOrder) {
    this.history.set([]);
    this.api.marketplaceOrder(order.id).subscribe((full) => this.detail.set(full));
    this.api.marketplaceOrderHistory(order.id).subscribe((events) => this.history.set(events));
  }
  download(invoiceId: string, documentId: string, filename: string) {
    const documentTab = window.open('about:blank', '_blank');
    if (!documentTab) {
      this.showFeedback('error', 'Permita a abertura de novas guias para visualizar este arquivo.');
      return;
    }
    this.api.downloadInvoiceDocument(invoiceId, documentId).subscribe(
      (blob) => {
        const url = URL.createObjectURL(blob);
        documentTab.opener = null;
        documentTab.document.title = filename;
        documentTab.location.href = url;
        window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
      },
      (error: unknown) => {
        documentTab.close();
        const detail =
          error instanceof HttpErrorResponse
            ? error.error?.detail || error.message
            : 'Não foi possível abrir o arquivo.';
        this.showFeedback('error', String(detail));
      },
    );
  }
}
