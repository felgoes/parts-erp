import { CurrencyPipe, DatePipe, DecimalPipe } from '@angular/common';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { debounceTime } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { UsersApi } from '../../core/api/users-api';
import { LiveUpdatesService } from '../../core/live-updates.service';
import { AuthService } from '../../core/auth.service';
import { DashboardFinancialMetrics, DashboardSummary, Invoice } from '../../core/models';
import { canSell } from '../../core/user-access';
import { statusLabel } from '../../core/status-labels';
import { saleStageForInvoice, saleStageLabel } from '../../core/sale-stage';
import { documentLabel } from '../../core/document-labels';
import { documentsWithoutXml } from '../../core/document-visibility';
import { PageHeader } from '../../shared/page-header';
import { PeriodFilter } from '../../shared/period-filter';
import { AfterSaleWorkflow } from '../../shared/after-sale-workflow';
import { TrackingPanel } from '../../shared/tracking-panel';
import { DashboardMetrics } from './metrics/dashboard-metrics';

@Component({
  selector: 'app-dashboard',
  imports: [
    CurrencyPipe,
    DatePipe,
    DecimalPipe,
    RouterLink,
    PageHeader,
    PeriodFilter,
    AfterSaleWorkflow,
    TrackingPanel,
    DashboardMetrics,
  ],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.scss',
})
export class DashboardPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly usersApi = inject(UsersApi);
  private readonly live = inject(LiveUpdatesService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly auth = inject(AuthService);
  canSell() {
    return canSell(this.auth.user()?.role);
  }
  private readonly router = inject(Router);
  readonly data = signal<DashboardSummary | null>(null);
  readonly financial = signal<DashboardFinancialMetrics | null>(null);
  readonly detail = signal<Invoice | null>(null);
  readonly financialSummaryHidden = computed(() => !!this.auth.user()?.financial_summary_hidden);
  readonly invoiceTab = signal<'items' | 'tracking' | 'documents' | 'aftersale'>('items');
  startDate = this.monthStart();
  endDate = this.today();
  readonly statusLabel = statusLabel;
  readonly saleStageForInvoice = saleStageForInvoice;
  readonly saleStageLabel = saleStageLabel;
  readonly documentLabel = documentLabel;
  readonly documentsForDownload = documentsWithoutXml;
  afterSaleLabel(invoice: Invoice) {
    if (!invoice.after_sale) return '';
    const kind =
      invoice.after_sale.kind === 'return'
        ? 'Devolução'
        : invoice.after_sale.kind === 'claim'
          ? 'Reclamação'
          : 'Cancelamento';
    return `${kind} · ${statusLabel(invoice.after_sale.status)}`;
  }
  afterSaleReason(value: string) {
    if (value.trim().toLowerCase() === 'mediations cancel the order')
      return 'A mediação cancelou o pedido';
    return value;
  }
  requesterLabel(value: string) {
    return (
      ({ meli: 'Mercado Livre', buyer: 'Comprador', seller: 'Vendedor' } as Record<string, string>)[
        value.toLowerCase()
      ] ?? value
    );
  }
  ngOnInit() {
    this.load();
    this.live.changes$
      .pipe(debounceTime(250), takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.load());
  }
  load() {
    if (!this.validRange()) return;
    this.api.dashboard(this.startDate, this.endDate).subscribe((v) => this.data.set(v));
    const detailId = this.detail()?.id;
    if (detailId)
      this.api.invoice(detailId).subscribe((full) => {
        if (this.detail()?.id === detailId) this.detail.set(full);
      });
  }
  applyDateFilter(range: { startDate: string; endDate: string }) {
    this.startDate = range.startDate;
    this.endDate = range.endDate;
    this.load();
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
  status(value: string) {
    return (
      (
        { draft: 'Rascunho', confirmed: 'Confirmada', cancelled: 'Cancelada' } as Record<
          string,
          string
        >
      )[value] ?? statusLabel(value)
    );
  }
  openRecent(invoice: Invoice) {
    this.invoiceTab.set('items');
    this.api.invoice(invoice.id).subscribe((full) => this.detail.set(full));
  }
  openFinancial() {
    this.api
      .dashboardFinancial(this.startDate, this.endDate)
      .subscribe((metrics) => this.financial.set(metrics));
  }
  setFinancialSummaryHidden(hidden: boolean) {
    this.usersApi.updateMyPreferences(hidden).subscribe({
      next: (user) => this.auth.updateCurrentUser(user),
    });
  }
  abs(value: number) {
    return Math.abs(value);
  }
  chartHeight(value: number, values: { amount: number }[]) {
    const max = Math.max(...values.map((item) => item.amount), 1);
    return value ? Math.max(8, (value / max) * 100) : 3;
  }
  sourceWidth(value: number, total: number) {
    return total ? Math.max(4, (value / total) * 100) : 0;
  }
  openDocument(invoiceId: string, documentId: string) {
    // Popup + blob falha no WebView Android e resulta em about:blank.
    this.router.navigate(['/document-viewer', invoiceId, documentId]);
  }
  documentViewerUrl(invoiceId: string, documentId: string) {
    return `/document-viewer/${invoiceId}/${documentId}`;
  }
}
