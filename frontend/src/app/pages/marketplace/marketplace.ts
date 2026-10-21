import { DatePipe, DecimalPipe, JsonPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ActivatedRoute } from '@angular/router';
import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { ApiService } from '../../core/api.service';
import { LiveUpdatesService } from '../../core/live-updates.service';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { debounceTime } from 'rxjs';
import { AuthService } from '../../core/auth.service';
import { MarketplaceOrder, MarketplaceOrderEvent, MarketplaceStatus } from '../../core/models';
import { statusLabel, trackingEventLabel } from '../../core/status-labels';
import { saleStageForOrder, saleStageLabel } from '../../core/sale-stage';
import { documentLabel } from '../../core/document-labels';
import { PageHeader } from '../../shared/page-header';

@Component({
  selector: 'app-marketplace',
  imports: [DatePipe, DecimalPipe, JsonPipe, PageHeader],
  templateUrl: './marketplace.html',
  styleUrl: './marketplace.scss',
})
export class MarketplacePage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly live = inject(LiveUpdatesService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly auth = inject(AuthService);
  private readonly route = inject(ActivatedRoute);
  readonly status = signal<MarketplaceStatus | null>(null);
  readonly orders = signal<MarketplaceOrder[]>([]);
  readonly syncing = signal(false);
  readonly feedback = signal<{ kind: 'success' | 'error' | 'info'; message: string } | null>(null);
  readonly working = signal<{ id: string; kind: 'fiscal' | 'label' } | null>(null);
  readonly detail = signal<MarketplaceOrder | null>(null);
  readonly history = signal<MarketplaceOrderEvent[]>([]);
  readonly statusLabel = statusLabel;
  readonly trackingEventLabel = trackingEventLabel;
  readonly saleStageForOrder = saleStageForOrder;
  readonly saleStageLabel = saleStageLabel;
  readonly documentLabel = documentLabel;
  platformCreatedAt(order: MarketplaceOrder): string | number | null {
    const payload = order.payload || {};
    const value = payload['date_created'] ?? payload['create_time'];
    if (value === undefined || value === null || value === '') return null;
    if (order.provider === 'shopee' && /^\d+$/.test(String(value))) return Number(value) * 1000;
    return String(value);
  }
  platformUpdatedAt(order: MarketplaceOrder): string | number | null {
    const payload = order.payload || {};
    const value =
      payload['last_updated'] ?? payload['update_time'] ?? payload['_erp_source_updated_at'];
    if (value === undefined || value === null || value === '') return null;
    if (order.provider === 'shopee' && /^\d+$/.test(String(value))) return Number(value) * 1000;
    return String(value);
  }
  canProcess() {
    const role = this.auth.user()?.role;
    return role === 'admin' || role === 'manager';
  }
  ngOnInit() {
    this.route.queryParamMap
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((params) => {
        const orderId = params.get('order_id');
        if (orderId) this.openDetailsById(orderId);
      });
    this.load();
    this.live.changes$
      .pipe(debounceTime(250), takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.load());
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
          waiting_release: 'Aguardando liberação do Mercado Livre',
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
    if (order.fiscal_status === 'waiting_release') return 'Verificar liberação';
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
    this.openDetailsById(order.id);
  }
  private openDetailsById(orderId: string) {
    this.history.set([]);
    this.api.marketplaceOrder(orderId).subscribe((full) => this.detail.set(full));
    this.api.marketplaceOrderHistory(orderId).subscribe((events) => this.history.set(events));
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
