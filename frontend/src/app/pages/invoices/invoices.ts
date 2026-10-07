import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { debounceTime, forkJoin } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { ApiService } from '../../core/api.service';
import { LiveUpdatesService } from '../../core/live-updates.service';
import { AuthService } from '../../core/auth.service';
import { Customer, Invoice, Product } from '../../core/models';
import { canSell } from '../../core/user-access';
import { statusLabel, trackingEventLabel } from '../../core/status-labels';
import { saleStageForInvoice, saleStageLabel } from '../../core/sale-stage';
import { documentLabel } from '../../core/document-labels';
import { PageHeader } from '../../shared/page-header';
import { PeriodFilter, PeriodFilterStatusOption } from '../../shared/period-filter';
import { AfterSaleWorkflow } from '../../shared/after-sale-workflow';

@Component({
  selector: 'app-invoices',
  imports: [CurrencyPipe, DatePipe, FormsModule, PageHeader, PeriodFilter, AfterSaleWorkflow],
  template: `
    <app-page-header
      eyebrow="Comercial"
      title="Faturas de venda"
      subtitle="Do orçamento à baixa de estoque, sem retrabalho."
      >@if (canSell()) { <button class="primary" (click)="openNew()">+ Nova venda</button> }</app-page-header
    >
    <app-period-filter
      heading="Período"
      [description]="invoices().length + ' fatura(s)'"
      ariaLabel="Filtrar faturas por período e situação"
      [initialStartDate]="startDate"
      [initialEndDate]="endDate"
      [statusOptions]="filterStatusOptions()"
      [selectedStatus]="statusFilter"
      (rangeChange)="applyDateFilter($event)"
      (statusChange)="setStatusFilter($event)"
    />
    <section class="card table-card">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Fatura</th>
              <th>Cliente</th>
              <th>Origem</th>
              <th>Emissão</th>
              <th>Status</th>
              <th>Documentos</th>
              <th class="right">Total</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            @for (i of visibleInvoices(); track i.id) {
              <tr class="clickable-row" (click)="openDetails(i)">
                <td>
                    <button class="link-button" (click)="$event.stopPropagation(); openDetails(i)">{{ i.number }}</button>
                  @if (i.marketplace_order_id) {
                    <small class="block">Pedido #{{ i.marketplace_order_id }}</small>
                  }
                </td>
                <td class="customer-cell">
                  <strong>{{ i.customer?.name || 'Consumidor não identificado' }}</strong>
                  <small>{{ i.customer?.document || i.customer?.email || 'Sem cadastro vinculado' }}</small>
                </td>
                <td>{{ i.source === 'mercadolivre' ? 'Mercado Livre' : 'Manual' }}</td>
                <td>{{ i.issued_at || i.created_at | date: 'dd/MM/yyyy HH:mm' }}</td>
                <td>
                  <span class="badge" [class]="i.status">{{ saleStageLabel(saleStageForInvoice(i)) }}</span>
                  @if (i.after_sale) { <small class="post-sale-summary">{{ afterSaleLabel(i) }}</small> }
                </td>
                <td>
                  @if (i.documents.length) {
                    @for (doc of i.documents; track doc.id) {
                      <a class="doc" href="#" (click)="$event.preventDefault(); $event.stopPropagation(); openDocument(i.id, doc.id)">
                        {{ documentLabel(doc.document_type) }}
                      </a>
                    }
                  } @else {
                    <span class="muted">—</span>
                  }
                </td>
                <td class="right">
                  <strong>{{ i.total | currency: 'BRL' }}</strong>
                </td>
                <td class="right">
                  @if (i.status === 'draft' && canSell()) {
                    <button class="secondary small" (click)="$event.stopPropagation(); confirm(i)">Confirmar</button>
                  }
                </td>
              </tr>
            } @empty {
              <tr>
                <td colspan="8"><div class="empty">{{ invoices().length ? 'Nenhuma fatura nesta situação.' : 'Nenhuma fatura registrada neste período.' }}</div></td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    </section>
    @if (modal()) {
      <div class="modal-backdrop" (click)="modal.set(false)">
        <section class="modal wide object-modal" (click)="$event.stopPropagation()">
          <div class="modal-head">
            <div>
              <p class="eyebrow">Nova operação</p>
              <h2>Fatura de venda</h2>
            </div>
            <button class="close" (click)="modal.set(false)">×</button>
          </div>
          <label
            >Cliente (opcional)<select [(ngModel)]="customerId">
              <option value="">Consumidor não identificado</option>
              @for (c of customers(); track c.id) {
                <option [value]="c.id">{{ c.name }}</option>
              }
            </select></label
          >
          <div class="line-builder">
            <label
              >Produto<select [(ngModel)]="selectedProduct">
                <option value="">Selecione…</option>
                @for (p of products(); track p.id) {
                  <option [value]="p.id">
                    {{ p.sku }} · {{ p.name }} ({{ p.current_stock }} un.)
                  </option>
                }
              </select></label
            ><label
              >Qtd.<input type="number" min="0.001" step="0.001" [(ngModel)]="quantity" /></label
            ><button class="secondary" (click)="addLine()">Adicionar</button>
          </div>
          <div class="invoice-lines">
            @for (line of lines(); track line.product.id) {
              <div>
                <span
                  ><strong>{{ line.product.name }}</strong
                  ><small
                    >{{ line.quantity }} × {{ line.product.sale_price | currency: 'BRL' }}</small
                  ></span
                ><strong>{{ line.quantity * line.product.sale_price | currency: 'BRL' }}</strong
                ><button class="close" (click)="removeLine(line.product.id)">×</button>
              </div>
            } @empty {
              <div class="empty">Adicione ao menos um produto.</div>
            }
          </div>
          <div class="invoice-total">
            <span>Total</span><strong>{{ total() | currency: 'BRL' }}</strong>
          </div>
          <button class="primary full" [disabled]="!lines().length" (click)="save()">
            Criar fatura em rascunho
          </button>
        </section>
      </div>
    }
    @if (detail(); as invoice) {
      <div class="modal-backdrop" (click)="detail.set(null)">
        <section class="modal wide object-modal" (click)="$event.stopPropagation()">
          <div class="modal-head detail-hero"><div><p class="eyebrow">Venda {{ invoice.source === 'mercadolivre' ? 'Mercado Livre' : 'manual' }}</p><h2>{{ invoice.number }}</h2><p class="detail-subtitle">Criada em {{ invoice.created_at | date:'dd/MM/yyyy HH:mm' }}{{ invoice.issued_at ? ' · emitida em ' + (invoice.issued_at | date:'dd/MM/yyyy HH:mm') : '' }}</p></div><div class="hero-actions"><span class="badge" [class]="invoice.status">{{ label(invoice.status) }}</span><button class="close" aria-label="Fechar detalhe" (click)="detail.set(null)">×</button></div></div>
          <div class="detail-summary"><div><span>Cliente</span><strong>{{ invoice.customer?.name || 'Consumidor não identificado' }}</strong><small>{{ invoice.customer?.document || invoice.customer?.email || 'Sem cadastro vinculado' }}</small></div><div><span>Pedido relacionado</span><strong>{{ invoice.marketplace_order_id ? '#' + invoice.marketplace_order_id : 'Venda local' }}</strong><small>{{ invoice.items.length }} item(ns) · {{ invoice.total | currency:'BRL' }}</small></div></div>
          <nav class="detail-tabs" aria-label="Detalhes da venda"><button [class.active]="invoiceTab() === 'items'" (click)="invoiceTab.set('items')">Itens <small>{{ invoice.items.length }}</small></button><button [class.active]="invoiceTab() === 'tracking'" (click)="invoiceTab.set('tracking')">Rastreio</button><button [class.active]="invoiceTab() === 'documents'" (click)="invoiceTab.set('documents')">Documentos <small>{{ invoice.documents.length }}</small></button>@if (invoice.after_sale) { <button [class.active]="invoiceTab() === 'aftersale'" (click)="invoiceTab.set('aftersale')">Pós-venda</button> }</nav>
          @if (invoiceTab() === 'items') { <section class="detail-section"><div class="section-heading"><div><p class="eyebrow">Composição</p><h3>Itens vendidos</h3></div><strong>{{ invoice.total | currency:'BRL' }}</strong></div><div class="invoice-detail-lines">@for (item of invoice.items; track item.id) { <div><span class="item-main"><strong>{{ item.description }}</strong><small>SKU {{ item.sku }} · {{ item.quantity }} unidade(s) · {{ item.unit_price | currency:'BRL' }} cada</small></span><strong>{{ item.total | currency:'BRL' }}</strong></div> }</div></section> }
          @if (invoiceTab() === 'tracking') { <section class="detail-section">@if (invoice.tracking; as tracking) { <div class="tracking-cards"><div><span>Status do pedido</span><strong>{{ statusLabel(tracking.status) }}</strong></div><div><span>Envio</span><strong>{{ statusLabel(tracking.shipping_status) }}</strong></div><div><span>Etiqueta</span><strong>{{ statusLabel(tracking.label_status) }}</strong></div><div><span>Código de rastreio</span><strong>{{ tracking.shipment_id || '—' }}</strong></div></div><div class="section-heading"><div><p class="eyebrow">Mercado Envios</p><h3>Linha do tempo do rastreio</h3></div><small>{{ tracking.last_update ? ((tracking.last_update_source === 'platform' ? 'Atualizado na plataforma ' : 'Recebido pelo ERP ') + (tracking.last_update | date:'dd/MM/yyyy HH:mm')) : '' }}</small></div><div class="timeline">@for (event of tracking.history; track event.created_at + event.status) { <div><strong>{{ trackingEventLabel(event.status, event.detail) }}</strong><span>{{ event.created_at | date:'dd/MM/yyyy HH:mm' }}</span></div> } @empty { <p class="muted">Ainda não há eventos de rastreio registrados.</p> }</div> } @else { <div class="empty">Esta venda não está vinculada a um pedido de marketplace.</div> }</section> }
          @if (invoiceTab() === 'documents') { <section class="detail-section"><div class="section-heading"><div><p class="eyebrow">Fiscal</p><h3>Documentos da venda</h3></div><span class="muted">Clique para abrir em nova guia</span></div>@if (invoice.documents.length) { <div class="document-list">@for (doc of invoice.documents; track doc.id) { <a class="document-card" href="#" (click)="$event.preventDefault(); openDocument(invoice.id, doc.id)"><span class="document-icon">{{ documentLabel(doc.document_type) }}</span><span><strong>{{ doc.filename }}</strong><small>{{ doc.document_type === 'pdf' ? 'Nota fiscal (DANFE)' : doc.document_type === 'label_pdf' ? 'Etiqueta de envio' : 'Nota fiscal eletrônica (XML)' }}</small></span><b>↗</b></a> }</div> } @else { <div class="empty">Nenhum documento anexado ainda.</div> }</section> }
          @if (invoiceTab() === 'aftersale' && invoice.after_sale) { <app-after-sale-workflow [afterSale]="invoice.after_sale" /> }
        </section>
      </div>
    }
  `,
  styleUrl: './invoices.scss',
})
export class InvoicesPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly live = inject(LiveUpdatesService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly auth = inject(AuthService);
  canSell() { return canSell(this.auth.user()?.role); }
  readonly invoices = signal<Invoice[]>([]);
  readonly products = signal<Product[]>([]);
  readonly customers = signal<Customer[]>([]);
  readonly modal = signal(false);
  readonly detail = signal<Invoice | null>(null);
  readonly invoiceTab = signal<'items' | 'tracking' | 'documents' | 'aftersale'>('items');
  statusFilter: 'all' | 'open' | 'post_sale' = 'all';
  readonly filterStatusOptions = computed<PeriodFilterStatusOption[]>(() => [
    { value: 'all', label: 'Todas', count: this.invoices().length },
    { value: 'open', label: 'Em andamento', count: this.countByStatus('open') },
    { value: 'post_sale', label: 'Canceladas / devoluções', count: this.countByStatus('post_sale') },
  ]);
  readonly statusLabel = statusLabel;
  readonly trackingEventLabel = trackingEventLabel;
  readonly saleStageForInvoice = saleStageForInvoice;
  readonly saleStageLabel = saleStageLabel;
  readonly documentLabel = documentLabel;
  visibleInvoices() {
    const invoices = this.invoices();
    if (this.statusFilter === 'open') {
      return invoices.filter((invoice) => invoice.status !== 'cancelled' && !invoice.after_sale);
    }
    if (this.statusFilter === 'post_sale') {
      return invoices.filter((invoice) => invoice.status === 'cancelled' || !!invoice.after_sale);
    }
    return invoices;
  }
  countByStatus(filter: 'open' | 'post_sale') {
    return this.invoices().filter((invoice) =>
      filter === 'open'
        ? invoice.status !== 'cancelled' && !invoice.after_sale
        : invoice.status === 'cancelled' || !!invoice.after_sale,
    ).length;
  }
  afterSaleLabel(invoice: Invoice) {
    if (!invoice.after_sale) return '';
    const title = invoice.after_sale.kind === 'return' ? 'Devolução' : invoice.after_sale.kind === 'claim' ? 'Reclamação' : 'Cancelamento';
    return `${title} · ${statusLabel(invoice.after_sale.status)}`;
  }
  afterSaleReason(value: string) {
    if (value.trim().toLowerCase() === 'mediations cancel the order') return 'A mediação cancelou o pedido';
    return value;
  }
  requesterLabel(value: string) {
    return ({ meli: 'Mercado Livre', buyer: 'Comprador', seller: 'Vendedor' } as Record<string, string>)[value.toLowerCase()] ?? value;
  }
  readonly lines = signal<{ product: Product; quantity: number }[]>([]);
  customerId = '';
  selectedProduct = '';
  quantity = 1;
  startDate = this.monthStart();
  endDate = this.today();
  ngOnInit() {
    this.load();
    this.live.changes$.pipe(debounceTime(250), takeUntilDestroyed(this.destroyRef)).subscribe(() => this.load());
  }
  load() {
    if (!this.validRange()) return;
    this.api.invoices(this.startDate, this.endDate).subscribe((v) => this.invoices.set(v));
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
  setStatusFilter(value: string) {
    if (value === 'all' || value === 'open' || value === 'post_sale') this.statusFilter = value;
  }
  validRange() { return !!this.startDate && !!this.endDate && this.startDate <= this.endDate; }
  private today() { return new Date().toLocaleDateString('sv-SE'); }
  private monthStart() { return `${this.today().slice(0, 7)}-01`; }
  openNew() {
    forkJoin([this.api.products(), this.api.customers()]).subscribe(([p, c]) => {
      this.products.set(p);
      this.customers.set(c);
      this.lines.set([]);
      this.modal.set(true);
    });
  }
  addLine() {
    const p = this.products().find((x) => x.id === this.selectedProduct);
    if (!p || this.quantity <= 0) return;
    this.lines.update((lines) => [
      ...lines.filter((x) => x.product.id !== p.id),
      { product: p, quantity: this.quantity },
    ]);
    this.selectedProduct = '';
    this.quantity = 1;
  }
  removeLine(id: string) {
    this.lines.update((v) => v.filter((x) => x.product.id !== id));
  }
  total() {
    return this.lines().reduce((sum, x) => sum + x.quantity * x.product.sale_price, 0);
  }
  save() {
    this.api
      .createInvoice({
        customer_id: this.customerId || null,
        items: this.lines().map((x) => ({ product_id: x.product.id, quantity: x.quantity })),
      })
      .subscribe(() => {
        this.modal.set(false);
        this.load();
      });
  }
  confirm(i: Invoice) {
    this.api.confirmInvoice(i.id).subscribe(() => this.load());
  }
  openDetails(i: Invoice) {
    this.invoiceTab.set('items');
    this.api.invoice(i.id).subscribe((full) => this.detail.set(full));
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
  label(s: string) {
    return ({ draft: 'Rascunho', confirmed: 'Confirmada', cancelled: 'Cancelada' } as Record<string, string>)[s] ?? statusLabel(s);
  }
}
