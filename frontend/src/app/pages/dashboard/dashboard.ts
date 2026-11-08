import { CurrencyPipe, DecimalPipe } from '@angular/common';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { debounceTime } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { DashboardApi } from '../../core/api/dashboard-api';
import { UsersApi } from '../../core/api/users-api';
import { LiveUpdatesService } from '../../core/live-updates.service';
import { AuthService } from '../../core/auth.service';
import { DashboardFinancialMetrics, DashboardSummary, Invoice } from '../../core/models';
import { canAccessPage } from '../../core/user-access';
import { saleStageForInvoice, saleStageLabel } from '../../core/sale-stage';
import { QuickDatePreset, matchingDatePreset } from '../../core/quick-date-ranges';
import { RecordOrigin, recordOrigin, restoreRecordPosition } from '../../shared/record-origin';
import { PeriodFilter } from '../../shared/period-filter';
import { OverviewCount } from './overview-count';
import { SalesTrend } from './sales-trend';

@Component({
  selector: 'app-dashboard',
  imports: [
    CurrencyPipe,
    DecimalPipe,
    RouterLink,
    PeriodFilter,
    OverviewCount,
    SalesTrend,
  ],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.scss',
})
export class DashboardPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dashboardApi = inject(DashboardApi);
  private readonly usersApi = inject(UsersApi);
  private readonly live = inject(LiveUpdatesService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly auth = inject(AuthService);
  canOpen(path: string): boolean {
    return canAccessPage(this.auth.user()?.role, path);
  }
  private readonly router = inject(Router);
  readonly data = signal<DashboardSummary | null>(null);
  readonly loadError = signal(false);
  readonly salesOffset = signal(0);
  readonly salesLoading = signal(false);
  readonly salesError = signal(false);
  readonly pageSize = 10;
  readonly confirmedSaleUnits = ['venda confirmada', 'vendas confirmadas'] as const;
  private salesRevision = 0;
  readonly financial = signal<DashboardFinancialMetrics | null>(null);
  readonly financialSummaryHidden = computed(() => !!this.auth.user()?.financial_summary_hidden);
  startDate = this.monthStart();
  endDate = this.today();
  initialPreset: QuickDatePreset = 'thisMonth';
  readonly saleStageForInvoice = saleStageForInvoice;
  readonly saleStageLabel = saleStageLabel;
  private pendingReturn = window.history.state?.recordReturn as RecordOrigin | undefined;
  ngOnInit() {
    const view = this.pendingReturn?.view as { startDate?: string; endDate?: string; salesOffset?: number } | undefined;
    if (view?.startDate && view.endDate) {
      this.startDate = view.startDate;
      this.endDate = view.endDate;
      this.salesOffset.set(Math.max(0, view.salesOffset ?? 0));
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
    const offset = this.salesOffset();
    const revision = this.salesRevision;
    this.api.dashboard(startDate, endDate, offset).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (summary) => {
        if (startDate !== this.startDate || endDate !== this.endDate) return;
        this.loadError.set(false);
        if (revision !== this.salesRevision || offset !== this.salesOffset()) {
          const current = this.data();
          if (current) this.data.set({
            ...summary,
            recent_invoices: current.recent_invoices,
            recent_sales_next_offset: current.recent_sales_next_offset,
          });
          return;
        }
        if (offset > 0 && !summary.recent_invoices.length) {
          this.salesOffset.set(Math.max(0, offset - this.pageSize));
          this.load();
          return;
        }
        this.data.set(summary);
        restoreRecordPosition(this.pendingReturn);
        this.pendingReturn = undefined;
      },
      error: () => {
        if (startDate === this.startDate && endDate === this.endDate) this.loadError.set(true);
      },
    });
  }
  loadSalesPage(offset: number): void {
    if (this.salesLoading() || offset < 0 || offset === this.salesOffset()) return;
    const revision = ++this.salesRevision;
    this.salesLoading.set(true);
    this.salesError.set(false);
    this.dashboardApi.dashboardRecentSales(this.startDate, this.endDate, offset)
      .pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: (page) => {
          if (revision !== this.salesRevision) return;
          this.salesOffset.set(offset);
          this.data.update((summary) => summary && ({
            ...summary, recent_invoices: page.items, recent_sales_next_offset: page.next_offset,
          }));
          this.salesLoading.set(false);
        },
        error: () => {
          if (revision !== this.salesRevision) return;
          this.salesError.set(true);
          this.salesLoading.set(false);
        },
      });
  }
  applyDateFilter(range: { startDate: string; endDate: string }) {
    if (range.startDate === this.startDate && range.endDate === this.endDate) return;
    ++this.salesRevision;
    this.salesOffset.set(0);
    this.salesLoading.set(false);
    this.salesError.set(false);
    this.data.set(null);
    this.loadError.set(false);
    this.startDate = range.startDate;
    this.endDate = range.endDate;
    this.load();
  }
  validRange() {
    return !!this.startDate && !!this.endDate && this.startDate <= this.endDate;
  }
  private today() {
    return new Date().toLocaleDateString('sv-SE', { timeZone: 'America/Sao_Paulo' });
  }
  private monthStart() {
    return `${this.today().slice(0, 7)}-01`;
  }
  openRecent(event: MouseEvent, invoice: Invoice): void {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    void this.router.navigate(['/invoices', invoice.id], {
      state: recordOrigin(this.router.url, 'Visão geral', invoice.id, {
        startDate: this.startDate,
        endDate: this.endDate,
        salesOffset: this.salesOffset(),
      }),
    });
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
}
