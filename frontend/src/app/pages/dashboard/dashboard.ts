import { CurrencyPipe, DecimalPipe } from '@angular/common';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { debounceTime } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { UsersApi } from '../../core/api/users-api';
import { LiveUpdatesService } from '../../core/live-updates.service';
import { AuthService } from '../../core/auth.service';
import { DashboardFinancialMetrics, DashboardSummary, Invoice } from '../../core/models';
import { canAccessPage } from '../../core/user-access';
import { saleStageForInvoice, saleStageLabel } from '../../core/sale-stage';
import { QuickDatePreset, matchingDatePreset } from '../../core/quick-date-ranges';
import { RecordOrigin, recordOrigin, restoreRecordPosition } from '../../shared/record-origin';
import { PeriodFilter } from '../../shared/period-filter';
import { SalesTrend } from './sales-trend';

@Component({
  selector: 'app-dashboard',
  imports: [
    CurrencyPipe,
    DecimalPipe,
    RouterLink,
    PeriodFilter,
    SalesTrend,
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
  canOpen(path: string): boolean {
    return canAccessPage(this.auth.user()?.role, path);
  }
  private readonly router = inject(Router);
  readonly data = signal<DashboardSummary | null>(null);
  readonly loadError = signal(false);
  readonly financial = signal<DashboardFinancialMetrics | null>(null);
  readonly financialSummaryHidden = computed(() => !!this.auth.user()?.financial_summary_hidden);
  startDate = this.monthStart();
  endDate = this.today();
  initialPreset: QuickDatePreset = 'thisMonth';
  readonly saleStageForInvoice = saleStageForInvoice;
  readonly saleStageLabel = saleStageLabel;
  private pendingReturn = window.history.state?.recordReturn as RecordOrigin | undefined;
  ngOnInit() {
    const view = this.pendingReturn?.view as { startDate?: string; endDate?: string } | undefined;
    if (view?.startDate && view.endDate) {
      this.startDate = view.startDate;
      this.endDate = view.endDate;
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
    this.api.dashboard(startDate, endDate).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (summary) => {
        if (startDate !== this.startDate || endDate !== this.endDate) return;
        this.loadError.set(false);
        this.data.set(summary);
        restoreRecordPosition(this.pendingReturn);
        this.pendingReturn = undefined;
      },
      error: () => {
        if (startDate === this.startDate && endDate === this.endDate) this.loadError.set(true);
      },
    });
  }
  applyDateFilter(range: { startDate: string; endDate: string }) {
    if (range.startDate === this.startDate && range.endDate === this.endDate) return;
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
