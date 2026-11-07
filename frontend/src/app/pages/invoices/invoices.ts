import { CurrencyPipe, DatePipe } from '@angular/common';
import { Router, RouterLink } from '@angular/router';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { debounceTime, forkJoin } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { ApiService } from '../../core/api.service';
import { LiveUpdatesService } from '../../core/live-updates.service';
import { AuthService } from '../../core/auth.service';
import { Customer, Invoice, Product } from '../../core/models';
import { canSell } from '../../core/user-access';
import { statusLabel } from '../../core/status-labels';
import { saleStageForInvoice, saleStageLabel } from '../../core/sale-stage';
import { invoiceDocumentLabel } from '../../core/document-labels';
import { documentsWithoutXml } from '../../core/document-visibility';
import { PageHeader } from '../../shared/page-header';
import { PeriodFilter, PeriodFilterStatusOption } from '../../shared/period-filter';
import { QuickDatePreset, matchingDatePreset } from '../../core/quick-date-ranges';
import { RecordOrigin, recordOrigin, restoreRecordPosition } from '../../shared/record-origin';

@Component({
  selector: 'app-invoices',
  imports: [
    CurrencyPipe,
    DatePipe,
    FormsModule,
    PageHeader,
    PeriodFilter,
    RouterLink,
  ],
  templateUrl: './invoices.html',
  styleUrl: './invoices.scss',
})
export class InvoicesPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  private readonly live = inject(LiveUpdatesService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly auth = inject(AuthService);
  canSell() {
    return canSell(this.auth.user()?.role);
  }
  readonly invoices = signal<Invoice[]>([]);
  readonly products = signal<Product[]>([]);
  readonly customers = signal<Customer[]>([]);
  readonly modal = signal(false);
  private pendingReturn = window.history.state?.recordReturn as RecordOrigin | undefined;
  readonly loadError = signal(false);
  readonly loading = signal(true);
  statusFilter: 'all' | 'open' | 'post_sale' = 'all';
  readonly filterStatusOptions = computed<PeriodFilterStatusOption[]>(() => [
    { value: 'all', label: 'Todas', count: this.invoices().length },
    { value: 'open', label: 'Em andamento', count: this.countByStatus('open') },
    {
      value: 'post_sale',
      label: 'Canceladas / devoluções',
      count: this.countByStatus('post_sale'),
    },
  ]);
  readonly statusLabel = statusLabel;
  readonly saleStageForInvoice = saleStageForInvoice;
  readonly saleStageLabel = saleStageLabel;
  readonly invoiceDocumentLabel = invoiceDocumentLabel;
  readonly listingDocuments = documentsWithoutXml;
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
    const title =
      invoice.after_sale.kind === 'return'
        ? 'Devolução'
        : invoice.after_sale.kind === 'claim'
          ? 'Reclamação'
          : 'Cancelamento';
    return `${title} · ${statusLabel(invoice.after_sale.status)}`;
  }
  readonly lines = signal<{ product: Product; quantity: number }[]>([]);
  customerId = '';
  selectedProduct = '';
  quantity = 1;
  startDate = this.monthStart();
  endDate = this.today();
  initialPreset: QuickDatePreset = 'thisMonth';

  ngOnInit() {
    const view = this.pendingReturn?.view as { startDate?: string; endDate?: string; status?: string } | undefined;
    if (view?.startDate && view.endDate) {
      this.startDate = view.startDate;
      this.endDate = view.endDate;
      this.setStatusFilter(view.status || 'all');
      this.initialPreset = matchingDatePreset(this.startDate, this.endDate);
    }
    this.load();
    this.live.changes$
      .pipe(debounceTime(250), takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.load());
  }
  load() {
    if (!this.validRange()) return;
    const { startDate, endDate } = this;
    this.api.invoices(startDate, endDate).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (invoices) => {
        if (startDate !== this.startDate || endDate !== this.endDate) return;
        this.invoices.set(invoices);
        this.loadError.set(false);
        this.loading.set(false);
        restoreRecordPosition(this.pendingReturn);
        this.pendingReturn = undefined;
      },
      error: () => {
        if (startDate !== this.startDate || endDate !== this.endDate) return;
        this.loading.set(false);
        this.loadError.set(true);
      },
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
  validRange() {
    return !!this.startDate && !!this.endDate && this.startDate <= this.endDate;
  }
  private today() {
    return new Date().toLocaleDateString('sv-SE');
  }
  private monthStart() {
    return `${this.today().slice(0, 7)}-01`;
  }
  openNew() {
    forkJoin([this.api.products('', false, 'product'), this.api.customers()]).subscribe(
      ([p, c]) => {
        this.products.set(p);
        this.customers.set(c);
        this.lines.set([]);
        this.modal.set(true);
      },
    );
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
  openDetails(event: MouseEvent, invoice: Invoice): void {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    void this.router.navigate(['/invoices', invoice.id], {
      state: recordOrigin(this.router.url, 'Vendas', invoice.id, {
        startDate: this.startDate,
        endDate: this.endDate,
        status: this.statusFilter,
      }),
    });
  }
  openDocument(invoiceId: string, documentId: string) {
    // Popup + blob falha no WebView Android e resulta em about:blank.
    this.router.navigate(['/document-viewer', invoiceId, documentId]);
  }
  documentViewerUrl(invoiceId: string, documentId: string) {
    return `/document-viewer/${invoiceId}/${documentId}`;
  }
}
