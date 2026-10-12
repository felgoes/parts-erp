import { CurrencyPipe, DatePipe } from '@angular/common';
import { Router } from '@angular/router';
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
  templateUrl: './invoices.html',
  styleUrl: './invoices.scss',
})
export class InvoicesPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
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
    forkJoin([this.api.products('', false, 'product'), this.api.customers()]).subscribe(([p, c]) => {
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
    // Popup + blob falha no WebView Android e resulta em about:blank.
    this.router.navigate(['/document-viewer', invoiceId, documentId]);
  }
  documentViewerUrl(invoiceId: string, documentId: string) { return `/document-viewer/${invoiceId}/${documentId}`; }
  label(s: string) {
    return ({ draft: 'Rascunho', confirmed: 'Confirmada', cancelled: 'Cancelada' } as Record<string, string>)[s] ?? statusLabel(s);
  }
}
