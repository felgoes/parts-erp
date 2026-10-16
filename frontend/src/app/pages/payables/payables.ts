import { CurrencyPipe, DecimalPipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { DestroyRef } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Subject, debounceTime } from 'rxjs';
import { finalize } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { LiveUpdatesService } from '../../core/live-updates.service';
import {
  PayableDetail,
  PayableInstallment,
  PayableListItem,
  PayableListResponse,
  PayableReport,
  PaymentConditionType,
} from '../../core/models';
import { DateRange, quickDateRange } from '../../core/quick-date-ranges';
import { canManagePurchases } from '../../core/user-access';
import { dateOnlyLabel, dateOnlyValue } from '../../shared/date-only';
import { MoneyInputDirective } from '../../shared/money-input.directive';
import { PageHeader } from '../../shared/page-header';
import { PeriodFilter } from '../../shared/period-filter';

@Component({
  selector: 'app-payables',
  imports: [CurrencyPipe, DecimalPipe, FormsModule, MoneyInputDirective, PageHeader, PeriodFilter],
  templateUrl: './payables.html',
  styleUrl: './payables.scss',
})
export class PayablesPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly live = inject(LiveUpdatesService);
  private readonly destroyRef = inject(DestroyRef);

  readonly data = signal<PayableListResponse | null>(null);
  readonly report = signal<PayableReport | null>(null);
  readonly detail = signal<PayableDetail | null>(null);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly error = signal('');
  readonly message = signal('');
  readonly search = signal('');
  readonly supplierFilter = signal('');
  readonly statusFilter = signal('all');
  readonly overdueOnly = signal(false);
  private readonly initialRange = quickDateRange('last30');
  readonly startDate = signal(this.initialRange.startDate);
  readonly endDate = signal(this.initialRange.endDate);
  readonly paymentDraft = signal<{
    amount: number;
    paid_at: string;
    method: string;
    notes: string;
    installmentId: string | null;
  }>({ amount: 0, paid_at: this.today(), method: '', notes: '', installmentId: null });
  readonly conditionDraft = signal<{
    payment_type: PaymentConditionType;
    installment_count: number;
    first_due_days: number;
    interval_days: number;
  }>({ payment_type: 'cash', installment_count: 1, first_due_days: 30, interval_days: 30 });
  private readonly filterChanges = new Subject<void>();

  constructor() {
    this.filterChanges.pipe(debounceTime(350), takeUntilDestroyed()).subscribe(() => this.load());
  }

  setSearch(value: string) {
    this.search.set(value);
    this.filterChanges.next();
  }
  setSupplier(value: string) {
    this.supplierFilter.set(value);
    this.filterChanges.next();
  }
  setStatus(value: string) {
    this.statusFilter.set(value);
    this.load();
  }
  setOverdueOnly(value: boolean) {
    this.overdueOnly.set(value);
    this.load();
  }

  canManage() {
    return canManagePurchases(this.auth.user()?.role);
  }
  dateOnly(value: string | null | undefined) {
    return dateOnlyLabel(value);
  }
  payableStatusLabel(status: string) {
    return (
      { open: 'Em aberto', partial: 'Baixa parcial', paid: 'Pago', cancelled: 'Encerrado' }[
        status
      ] ?? status
    );
  }
  /** O que é o título: na despesa vale o título do gasto, com a categoria ao lado. */
  payableContext(item: PayableListItem) {
    if (item.purchase_type !== 'expense') return 'Compra de peças';
    return [item.expense_description, item.expense_category || 'Despesa']
      .filter(Boolean)
      .join(' · ');
  }
  private today() {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  }

  ngOnInit() {
    this.load();
    this.loadReport();
    this.live.changes$
      .pipe(debounceTime(300), takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        this.load();
        this.loadReport();
      });
  }

  private filters(extra: Record<string, string | number | boolean> = {}) {
    return {
      status: this.statusFilter() === 'all' ? '' : this.statusFilter(),
      supplier: this.supplierFilter().trim(),
      search: this.search().trim(),
      overdue_only: this.overdueOnly(),
      ...extra,
    };
  }

  load() {
    this.loading.set(true);
    this.error.set('');
    this.api
      .payables(this.filters())
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: (listing) => this.data.set(listing),
        error: (err) =>
          this.error.set(err.error?.detail || 'Não foi possível carregar as contas a pagar.'),
      });
  }

  loadReport() {
    this.api.payableReport({ paid_from: this.startDate(), paid_to: this.endDate() }).subscribe({
      next: (summary) => this.report.set(summary),
      error: () => undefined,
    });
  }

  applyPeriod(range: DateRange) {
    this.startDate.set(range.startDate);
    this.endDate.set(range.endDate);
    this.load();
    this.loadReport();
  }

  exportCsv() {
    this.api.downloadPayablesCsv(this.filters());
  }

  openDetail(item: PayableListItem) {
    this.error.set('');
    this.message.set('');
    this.api.payable(item.id).subscribe({
      next: (payable) => {
        this.paymentDraft.set({
          amount: Number(payable.balance),
          paid_at: this.today(),
          method: '',
          notes: '',
          installmentId: null,
        });
        this.conditionDraft.set({
          payment_type: (payable.payment_type ?? 'cash') as PaymentConditionType,
          installment_count: payable.installment_count ?? payable.installments.length ?? 1,
          first_due_days: payable.first_due_days ?? 30,
          interval_days: payable.interval_days ?? 30,
        });
        this.detail.set(payable);
      },
      error: (err) => this.error.set(err.error?.detail || 'Não foi possível abrir o título.'),
    });
  }

  closeDetail() {
    this.detail.set(null);
  }

  setPaymentAmount(value: number | null) {
    this.paymentDraft.update((draft) => ({ ...draft, amount: value ?? 0 }));
  }
  /** P12: pré-seleciona a parcela no formulário de baixa. */
  payInstallment(payable: PayableDetail, installment: PayableInstallment) {
    const open = Number(
      installment.balance ?? Number(installment.amount) - Number(installment.paid_amount ?? 0),
    );
    this.paymentDraft.set({
      amount: open,
      paid_at: this.today(),
      method: '',
      notes: `Parcela ${installment.number}`,
      installmentId: installment.id,
    });
  }

  setConditionType(value: string) {
    this.conditionDraft.update((draft) => ({
      ...draft,
      payment_type: value as PaymentConditionType,
    }));
  }
  setConditionNumber(
    field: 'installment_count' | 'first_due_days' | 'interval_days',
    value: string,
  ) {
    this.conditionDraft.update((draft) => ({ ...draft, [field]: Number(value) || 0 }));
  }

  /** P12: altera a condição do título; parcelas já pagas ficam como estão. */
  saveCondition(payable: PayableDetail) {
    if (this.saving()) return;
    const draft = this.conditionDraft();
    this.saving.set(true);
    this.error.set('');
    this.api
      .updatePayable(payable.id, draft)
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe({
        next: (updated) => {
          this.detail.set(updated);
          this.afterMutation('Condição de pagamento atualizada.');
        },
        error: (err) =>
          this.error.set(err.error?.detail || 'Não foi possível alterar a condição de pagamento.'),
      });
  }
  setPaymentField(field: 'paid_at' | 'method' | 'notes', value: string) {
    this.paymentDraft.update((draft) => ({ ...draft, [field]: value }));
  }

  submitPayment(payable: PayableDetail) {
    const draft = this.paymentDraft();
    if (this.saving() || draft.amount <= 0 || draft.amount > payable.balance) return;
    this.saving.set(true);
    this.error.set('');
    this.api
      .addPayablePayment(payable.id, {
        amount: draft.amount,
        paid_at: draft.paid_at || null,
        method: draft.method || null,
        notes: draft.notes || null,
        installment_id: draft.installmentId,
      })
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe({
        next: (updated) => {
          this.paymentDraft.set({
            amount: Number(updated.balance),
            paid_at: this.today(),
            method: '',
            notes: '',
            installmentId: null,
          });
          this.detail.set(updated);
          this.afterMutation('Pagamento registrado.');
        },
        error: (err) =>
          this.error.set(err.error?.detail || 'Não foi possível registrar o pagamento.'),
      });
  }

  toggleReconcile(payable: PayableDetail, payment: { id: string; reconciled: boolean }) {
    if (this.saving()) return;
    this.saving.set(true);
    this.api
      .reconcilePayablePayment(payable.id, payment.id, !payment.reconciled)
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe({
        next: (updated) => {
          this.detail.set(updated);
          this.afterMutation(
            payment.reconciled ? 'Conciliação desfeita.' : 'Pagamento conciliado.',
          );
        },
        error: (err) =>
          this.error.set(err.error?.detail || 'Não foi possível atualizar a conciliação.'),
      });
  }

  removePayment(payable: PayableDetail, payment: { id: string }) {
    if (this.saving()) return;
    if (!confirm('Remover este pagamento do título? O saldo volta a ficar em aberto.')) return;
    this.saving.set(true);
    this.api
      .removePayablePayment(payable.id, payment.id)
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe({
        next: (updated) => {
          this.detail.set(updated);
          this.paymentDraft.update((draft) => ({ ...draft, amount: Number(updated.balance) }));
          this.afterMutation('Pagamento removido.');
        },
        error: (err) =>
          this.error.set(err.error?.detail || 'Não foi possível remover o pagamento.'),
      });
  }

  updateDueDate(payable: PayableDetail, value: string) {
    if (!value || dateOnlyValue(value) === dateOnlyValue(payable.due_date)) return;
    this.saving.set(true);
    this.api
      .updatePayable(payable.id, { due_date: value })
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe({
        next: (updated) => {
          this.detail.set(updated);
          this.afterMutation('Vencimento atualizado.');
        },
        error: (err) =>
          this.error.set(err.error?.detail || 'Não foi possível alterar o vencimento.'),
      });
  }

  private afterMutation(text: string) {
    this.message.set(text);
    this.load();
    this.loadReport();
  }
}
