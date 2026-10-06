import { DatePipe, DecimalPipe, JsonPipe, UpperCasePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { ApiService } from '../../core/api.service';
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
                <td>{{ o.created_at | date: 'dd/MM/yyyy HH:mm' }}</td>
                <td>{{ statusLabel(o.status) }}</td>
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
                Recebido em {{ order.created_at | date: 'dd/MM/yyyy HH:mm' }}
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
              <small>Envio</small><strong>{{ statusLabel(order.shipping_status) }}</strong>
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
          @if (isWorking(order.id)) {
            <div class="document-progress" role="status" aria-live="polite">
              <span class="document-progress-spinner" aria-hidden="true"></span>
              <p>{{ documentProgressText(order) }}</p>
            </div>
          }
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
                      <span class="fulfillment-state">{{
                        automationLabel(order.fiscal_status)
                      }}</span>
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
                        {{
                          isWorking(order.id, 'fiscal') ? 'Consultando…' : fiscalActionLabel(order)
                        }}
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
                order.synchronized_at
                  ? 'Atualizado ' + (order.synchronized_at | date: 'dd/MM/yyyy HH:mm')
                  : 'Aguardando sincronização'
              }}</span>
            </div>
            <div class="timeline">
              <div>
                <strong>Pedido recebido</strong
                ><span>{{ order.created_at | date: 'dd/MM/yyyy HH:mm' }}</span>
              </div>
              <div>
                <strong>Status atual: {{ statusLabel(order.status) }}</strong
                ><span>{{
                  order.synchronized_at
                    ? (order.synchronized_at | date: 'dd/MM/yyyy HH:mm')
                    : 'Ainda não sincronizado'
                }}</span>
              </div>
              @if (order.payload?.['shipping']) {
                <div>
                  <strong>Envio {{ order.payload?.['shipping']?.['id'] || '' }}</strong
                  ><span>{{
                    statusLabel(order.payload?.['shipping']?.['status'] || order.shipping_status)
                  }}</span>
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
export class MarketplacePage implements OnInit, OnDestroy {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  readonly status = signal<MarketplaceStatus | null>(null);
  readonly orders = signal<MarketplaceOrder[]>([]);
  readonly syncing = signal(false);
  readonly feedback = signal<{ kind: 'success' | 'error' | 'info'; message: string } | null>(null);
  readonly working = signal<{
    id: string;
    kind: 'fiscal' | 'label';
    startedAt: number;
  } | null>(null);
  readonly detail = signal<MarketplaceOrder | null>(null);
  readonly history = signal<MarketplaceOrderEvent[]>([]);
  private progressTimer: number | null = null;
  readonly statusLabel = statusLabel;
  readonly trackingEventLabel = trackingEventLabel;
  canProcess() {
    const role = this.auth.user()?.role;
    return role === 'admin' || role === 'manager';
  }
  ngOnInit() {
    this.load();
  }
  ngOnDestroy() {
    if (this.progressTimer !== null) window.clearTimeout(this.progressTimer);
  }
  load() {
    this.api.marketplaceStatus().subscribe((v) => this.status.set(v));
    this.api.marketplaceOrders().subscribe({
      next: (v) => this.orders.set(v),
      error: () =>
        this.showFeedback('error', 'Não foi possível carregar os pedidos do Mercado Livre.'),
    });
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
    if (this.isWorking(order.id)) return 'Acompanhando…';
    return order.external_invoice_id ? 'Verificar NF-e' : 'Solicitar NF-e';
  }
  documentProgressText(order: MarketplaceOrder) {
    const current = this.working();
    if (!current || current.id !== order.id) return '';
    if (current.kind === 'label') {
      if (
        order.fiscal_status === 'authorized' &&
        !this.documentFor(order, 'pdf') &&
        !this.documentFor(order, 'xml')
      ) {
        return 'NF-e emitida. Estamos sincronizando os arquivos fiscais e acompanhando a etiqueta…';
      }
      return 'Acompanhando a liberação da etiqueta e anexando o arquivo à fatura…';
    }
    if (order.fiscal_status === 'authorized') {
      return 'NF-e emitida. Estamos sincronizando o documento e acompanhando a etiqueta…';
    }
    return 'Solicitação enviada. Aguardando o Mercado Livre processar a NF-e…';
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
    if (
      ['delivered', 'shipped', 'returned', 'not_delivered'].includes(order.shipping_status ?? '')
    ) {
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
    if (
      ['delivered', 'shipped', 'returned', 'not_delivered'].includes(order.shipping_status ?? '')
    ) {
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
    this.working.set({ id: order.id, kind, startedAt: Date.now() });
    this.dismissFeedback();
    const request =
      kind === 'fiscal'
        ? this.api.requestMarketplaceInvoice(order.id)
        : this.api.retryMarketplaceLabel(order.id);
    request.subscribe({
      next: (updated) => {
        this.applyOrderUpdate(updated);
        if (this.shouldKeepChecking(updated, kind)) {
          this.showFeedback(
            'info',
            kind === 'fiscal'
              ? 'Pedido enviado. Vou acompanhar a NF-e e a etiqueta automaticamente.'
              : 'Vou acompanhar a liberação da etiqueta automaticamente.',
          );
          this.checkOrderProgress(updated, kind, Date.now());
          return;
        }
        this.finishOrderAction(updated, kind);
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
  private applyOrderUpdate(updated: MarketplaceOrder) {
    this.orders.update((orders) => orders.map((item) => (item.id === updated.id ? updated : item)));
    if (this.detail()?.id === updated.id) this.detail.set(updated);
  }
  private shouldKeepChecking(order: MarketplaceOrder, kind: 'fiscal' | 'label') {
    if (kind === 'fiscal' && order.fiscal_status === 'error') return false;
    if (kind === 'label') {
      return (
        !['downloaded', 'completed', 'not_applicable'].includes(order.label_status) &&
        !['delivered', 'shipped', 'returned', 'not_delivered', 'cancelled', 'canceled'].includes(
          order.shipping_status?.toLowerCase() ?? '',
        )
      );
    }
    if (order.fiscal_status !== 'authorized') return true;
    const hasInvoiceFile = Boolean(
      this.documentFor(order, 'pdf') || this.documentFor(order, 'xml'),
    );
    const labelReady =
      ['downloaded', 'completed', 'not_applicable'].includes(order.label_status) ||
      ['delivered', 'shipped', 'returned', 'not_delivered', 'cancelled', 'canceled'].includes(
        order.shipping_status?.toLowerCase() ?? '',
      );
    return !hasInvoiceFile || !labelReady;
  }
  private checkOrderProgress(order: MarketplaceOrder, kind: 'fiscal' | 'label', startedAt: number) {
    const elapsed = Date.now() - startedAt;
    const pollInterval = elapsed < 180_000 ? 5_000 : 15_000;
    this.progressTimer = window.setTimeout(() => {
      this.api.marketplaceOrder(order.id).subscribe({
        next: (updated) => {
          this.applyOrderUpdate(updated);
          if (updated.fiscal_status === 'authorized' && kind === 'fiscal') {
            this.working.set({ id: order.id, kind: 'label', startedAt });
          }
          if (this.shouldKeepChecking(updated, kind)) {
            this.checkOrderProgress(updated, kind, startedAt);
          } else {
            this.finishOrderAction(updated, kind);
          }
        },
        error: () => {
          this.checkOrderProgress(order, kind, startedAt);
        },
      });
    }, pollInterval);
  }
  private finishOrderAction(order: MarketplaceOrder, kind: 'fiscal' | 'label') {
    if (order.fiscal_status === 'error' || order.label_status === 'error') {
      this.showFeedback(
        'error',
        order.fiscal_error ||
          order.label_error ||
          'Não foi possível concluir a emissão dos documentos.',
      );
      this.working.set(null);
      return;
    }
    if (kind === 'fiscal') {
      const invoiceReady = Boolean(
        this.documentFor(order, 'pdf') || this.documentFor(order, 'xml'),
      );
      const labelReady = Boolean(this.documentFor(order, 'label_pdf'));
      this.showFeedback(
        'success',
        labelReady
          ? 'NF-e emitida e etiqueta anexada à fatura.'
          : invoiceReady
            ? 'NF-e emitida e anexada à fatura. A etiqueta será atualizada automaticamente assim que o Mercado Livre liberar.'
            : 'A etapa fiscal do pedido foi atualizada.',
      );
    } else {
      this.showFeedback(
        order.label_status === 'downloaded' ? 'success' : 'info',
        order.label_status === 'downloaded'
          ? 'Etiqueta anexada à fatura. Você já pode abri-la nesta tela.'
          : this.labelStatusHelp(order),
      );
    }
    this.working.set(null);
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
