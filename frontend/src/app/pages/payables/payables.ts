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
import { PayableDetail, PayableListItem, PayableListResponse, PayableReport } from '../../core/models';
import { DateRange, quickDateRange } from '../../core/quick-date-ranges';
import { canManagePurchases } from '../../core/user-access';
import { dateOnlyLabel, dateOnlyValue } from '../../shared/date-only';
import { MoneyInputDirective } from '../../shared/money-input.directive';
import { PageHeader } from '../../shared/page-header';
import { PeriodFilter } from '../../shared/period-filter';

@Component({
  selector: 'app-payables',
  imports: [CurrencyPipe, DecimalPipe, FormsModule, MoneyInputDirective, PageHeader, PeriodFilter],
  template: `
    <app-page-header eyebrow="Financeiro" title="Contas a pagar" subtitle="Títulos gerados por compras e despesas, com baixa parcial, conciliação e relatórios.">
      <div class="payables-header-actions"><button class="secondary" type="button" (click)="exportCsv()">Exportar CSV</button><button class="secondary" type="button" [disabled]="loading()" (click)="load()">Atualizar</button></div>
    </app-page-header>

    @if (error()) { <p class="payables-error" role="alert">{{ error() }}</p> }
    @if (message()) { <p class="payables-message" role="status">{{ message() }}</p> }

    @if (data(); as listing) {
      <section class="payables-highlights" aria-label="Resumo das contas a pagar">
        <article class="payables-highlight"><span>Em aberto</span><strong>{{ listing.summary.open_balance | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</strong><small>{{ listing.summary.open_count }} título(s) · {{ listing.summary.partial_count }} em baixa parcial</small></article>
        <article class="payables-highlight overdue-highlight"><span>Vencido</span><strong>{{ listing.summary.overdue_balance | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</strong><small>{{ listing.summary.overdue_count }} título(s) com vencimento passado</small></article>
        <article class="payables-highlight"><span>Vence em {{ listing.next_days }} dias</span><strong>{{ listing.summary.due_next_days_balance | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</strong><small>Inclui os que vencem hoje</small></article>
        <article class="payables-highlight paid-highlight"><span>Pago no período</span><strong>{{ listing.summary.paid_in_period | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</strong><small>{{ listing.summary.paid_count }} título(s) quitado(s) · {{ listing.summary.unreconciled_payments }} pagamento(s) sem conciliação</small></article>
      </section>

      <section class="card payables-filters">
        <label class="payables-search"><span>⌕</span><input aria-label="Buscar títulos" placeholder="Buscar fornecedor, número da compra ou pedido…" [value]="search()" (input)="setSearch($any($event.target).value)" /></label>
        <label>Fornecedor<input type="text" placeholder="Parte do nome" [value]="supplierFilter()" (input)="setSupplier($any($event.target).value)" /></label>
        <label>Situação<select [value]="statusFilter()" (change)="setStatus($any($event.target).value)"><option value="all">Todas</option><option value="open">Em aberto</option><option value="partial">Baixa parcial</option><option value="paid">Pagos</option><option value="cancelled">Encerrados</option></select></label>
        <label class="check-field"><input type="checkbox" [checked]="overdueOnly()" (change)="setOverdueOnly($any($event.target).checked)" /> Somente vencidos</label>
        <span class="muted">{{ listing.items.length }} título(s)</span>
      </section>

      <section class="card payables-aging" aria-label="Aging dos títulos">
        <div class="section-title"><div><p class="eyebrow">Aging</p><h2>Distribuição por atraso</h2><p>Saldo em aberto por faixa de vencimento, considerando os filtros aplicados.</p></div></div>
        <div class="aging-grid">
          @for (bucket of listing.aging; track bucket.label) {
            <div class="aging-cell" [class.aging-overdue]="bucket.label !== 'A vencer'"><span>{{ bucket.label }}</span><strong>{{ bucket.balance | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</strong><small>{{ bucket.count }} título(s)</small></div>
          }
        </div>
      </section>

      <section class="card payables-table-card">
        <div class="table-wrap"><table>
          <thead><tr><th>VENCIMENTO</th><th>FORNECEDOR</th><th>ORIGEM</th><th>VALOR</th><th>PAGO</th><th>SALDO</th><th>SITUAÇÃO</th><th></th></tr></thead>
          <tbody>
            @for (item of listing.items; track item.id) {
              <tr class="payable-row" [class.overdue-row]="item.days_overdue > 0">
                <td><strong>{{ dateOnly(item.due_date) }}</strong>@if (item.days_overdue > 0) { <small class="overdue-chip">{{ item.days_overdue }} dia(s) em atraso</small> }</td>
                <td>{{ item.supplier_name || 'Sem fornecedor' }}<small>{{ item.purchase_type === 'expense' ? (item.expense_category || 'Despesa') : 'Compra de peças' }}</small></td>
                <td><code>{{ item.purchase_number }}</code><small>{{ item.payment_count }} pagamento(s)@if (item.reconciled_payment_count < item.payment_count) { · {{ item.payment_count - item.reconciled_payment_count }} sem conciliação }</small></td>
                <td>{{ item.amount | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</td>
                <td>{{ item.paid_amount | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</td>
                <td><strong>{{ item.balance | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</strong></td>
                <td><span class="payable-badge" [attr.data-status]="item.status">{{ payableStatusLabel(item.status) }}</span></td>
                <td class="row-action"><button type="button" class="secondary small" (click)="openDetail(item)">{{ canManage() && item.status !== 'cancelled' ? 'Baixar / histórico' : 'Histórico' }}</button></td>
              </tr>
            } @empty { <tr><td colspan="8"><div class="payables-empty"><strong>Nenhum título com esses filtros</strong><span>Compras recebidas e despesas lançadas geram títulos automaticamente.</span></div></td></tr> }
          </tbody>
        </table></div>
      </section>

      <section class="card payables-report">
        <div class="section-title"><div><p class="eyebrow">Relatórios</p><h2>Pagamentos e passivo por fornecedor</h2><p>Período aplicado aos pagamentos registrados: {{ report()?.period_label || 'últimos 30 dias' }}.</p></div></div>
        <app-period-filter heading="Período dos pagamentos" description="Considera a data de cada baixa registrada." ariaLabel="Filtrar pagamentos por período" initialPreset="last30" [initialStartDate]="startDate()" [initialEndDate]="endDate()" (rangeChange)="applyPeriod($event)" />
        @if (report(); as summary) {
          <div class="report-grid">
            <div class="report-block">
              <h3>Saldo por fornecedor</h3>
              <div class="table-wrap"><table><thead><tr><th>FORNECEDOR</th><th>TÍTULOS</th><th>EM ABERTO</th><th>VENCIDO</th><th>PAGO NO PERÍODO</th></tr></thead><tbody>
                @for (row of summary.by_supplier; track row.supplier_name) { <tr><td>{{ row.supplier_name }}</td><td>{{ row.titles }}</td><td>{{ row.open_balance | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</td><td>{{ row.overdue_balance | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</td><td>{{ row.paid_in_period | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</td></tr> }
                @empty { <tr><td colspan="5" class="muted">Sem títulos no período.</td></tr> }
              </tbody></table></div>
            </div>
            <div class="report-block">
              <h3>Pagamentos por mês</h3>
              <ul class="month-list">
                @for (month of summary.by_month; track month.month) { <li><span>{{ month.month }}</span><strong>{{ month.paid | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</strong><small>{{ month.titles }} pagamento(s)</small></li> }
                @empty { <li class="muted">Nenhum pagamento registrado.</li> }
              </ul>
            </div>
          </div>
        }
      </section>
    } @else if (!error()) {
      <section class="card payables-state" aria-live="polite"><span class="loading-mark"></span><strong>Carregando os títulos…</strong></section>
    }

    @if (detail(); as payable) {
      <div class="modal-backdrop" (click)="closeDetail()"><section class="modal wide payable-modal" role="dialog" aria-modal="true" [attr.aria-label]="'Título ' + payable.purchase_number" (click)="$event.stopPropagation()">
        <div class="modal-head"><div><p class="eyebrow">{{ payable.purchase_type === 'expense' ? 'Despesa' : 'Compra' }} · {{ payable.purchase_number }}</p><h2>{{ payable.supplier_name || 'Sem fornecedor' }}</h2><p class="modal-intro">Vencimento {{ dateOnly(payable.due_date) }} · valor {{ payable.amount | currency:'BRL':'symbol':'1.2-2':'pt-BR' }} · saldo {{ payable.balance | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</p></div><div class="detail-head-actions"><span class="payable-badge" [attr.data-status]="payable.status">{{ payableStatusLabel(payable.status) }}</span><button class="close" aria-label="Fechar" (click)="closeDetail()">×</button></div></div>

        @if (canManage() && payable.status !== 'cancelled' && payable.balance > 0) {
          <section class="payable-form">
            <div class="section-title"><div><p class="eyebrow">Baixa</p><h3>Registrar pagamento</h3><p>Pagamentos parciais são permitidos até quitar o saldo.</p></div></div>
            <div class="payable-form-grid">
              <label>Valor (R$)<input appMoneyInput [appMoneyInput]="paymentDraft().amount" min="0.01" (moneyInput)="setPaymentAmount($event)" /></label>
              <label>Data do pagamento<input type="date" [value]="paymentDraft().paid_at" (input)="setPaymentField('paid_at', $any($event.target).value)" /></label>
              <label>Forma<input type="text" placeholder="Pix, boleto, cartão…" [value]="paymentDraft().method" (input)="setPaymentField('method', $any($event.target).value)" /></label>
              <label>Observações<input type="text" placeholder="Opcional" [value]="paymentDraft().notes" (input)="setPaymentField('notes', $any($event.target).value)" /></label>
              <label>Vencimento do título<input type="date" [value]="dateOnly(payable.due_date)" (change)="updateDueDate(payable, $any($event.target).value)" /></label>
            </div>
            <div class="payable-form-actions"><span class="muted">Saldo atual: {{ payable.balance | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</span><button type="button" class="primary" [disabled]="saving() || paymentDraft().amount <= 0 || paymentDraft().amount > payable.balance" (click)="submitPayment(payable)">{{ saving() ? 'Salvando…' : 'Registrar pagamento' }}</button></div>
          </section>
        }

        <section class="payable-history">
          <div class="section-title"><div><p class="eyebrow">Histórico</p><h3>Pagamentos registrados</h3></div><span class="muted">{{ payable.payments.length }} registro(s)</span></div>
          @if (payable.payments.length) {
            <ul class="payment-list">
              @for (payment of payable.payments; track payment.id) {
                <li class="payment-row" [class.reconciled]="payment.reconciled">
                  <div><strong>{{ payment.amount | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</strong><small>{{ dateOnly(payment.paid_at) }}{{ payment.method ? ' · ' + payment.method : '' }}{{ payment.notes ? ' · ' + payment.notes : '' }}</small></div>
                  <span class="reconcile-state">{{ payment.reconciled ? 'Conciliado' : 'Sem conciliação' }}</span>
                  @if (canManage()) { <div class="payment-actions">
                    <button type="button" class="secondary small" [disabled]="saving()" (click)="toggleReconcile(payable, payment)">{{ payment.reconciled ? 'Desfazer conciliação' : 'Conciliar' }}</button>
                    @if (!payment.reconciled) { <button type="button" class="danger-outline" [disabled]="saving()" (click)="removePayment(payable, payment)">Remover</button> }
                  </div> }
                </li>
              }
            </ul>
          } @else { <p class="muted">Nenhum pagamento registrado para este título.</p> }
        </section>
      </section></div>
    }
  `,
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
  readonly paymentDraft = signal({ amount: 0, paid_at: this.today(), method: '', notes: '' });
  private readonly filterChanges = new Subject<void>();

  constructor() {
    this.filterChanges.pipe(debounceTime(350), takeUntilDestroyed()).subscribe(() => this.load());
  }

  setSearch(value: string) { this.search.set(value); this.filterChanges.next(); }
  setSupplier(value: string) { this.supplierFilter.set(value); this.filterChanges.next(); }
  setStatus(value: string) { this.statusFilter.set(value); this.load(); }
  setOverdueOnly(value: boolean) { this.overdueOnly.set(value); this.load(); }

  canManage() { return canManagePurchases(this.auth.user()?.role); }
  dateOnly(value: string | null | undefined) { return dateOnlyLabel(value); }
  payableStatusLabel(status: string) {
    return { open: 'Em aberto', partial: 'Baixa parcial', paid: 'Pago', cancelled: 'Encerrado' }[status] ?? status;
  }
  private today() {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  }

  ngOnInit() {
    this.load();
    this.loadReport();
    this.live.changes$.pipe(debounceTime(300), takeUntilDestroyed(this.destroyRef)).subscribe(() => { this.load(); this.loadReport(); });
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
    this.api.payables(this.filters()).pipe(finalize(() => this.loading.set(false))).subscribe({
      next: (listing) => this.data.set(listing),
      error: (err) => this.error.set(err.error?.detail || 'Não foi possível carregar as contas a pagar.'),
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
        this.paymentDraft.set({ amount: Number(payable.balance), paid_at: this.today(), method: '', notes: '' });
        this.detail.set(payable);
      },
      error: (err) => this.error.set(err.error?.detail || 'Não foi possível abrir o título.'),
    });
  }

  closeDetail() { this.detail.set(null); }

  setPaymentAmount(value: number | null) { this.paymentDraft.update((draft) => ({ ...draft, amount: value ?? 0 })); }
  setPaymentField(field: 'paid_at' | 'method' | 'notes', value: string) { this.paymentDraft.update((draft) => ({ ...draft, [field]: value })); }

  submitPayment(payable: PayableDetail) {
    const draft = this.paymentDraft();
    if (this.saving() || draft.amount <= 0 || draft.amount > payable.balance) return;
    this.saving.set(true);
    this.error.set('');
    this.api.addPayablePayment(payable.id, { amount: draft.amount, paid_at: draft.paid_at || null, method: draft.method || null, notes: draft.notes || null }).pipe(finalize(() => this.saving.set(false))).subscribe({
      next: (updated) => { this.paymentDraft.set({ amount: Number(updated.balance), paid_at: this.today(), method: '', notes: '' }); this.detail.set(updated); this.afterMutation('Pagamento registrado.'); },
      error: (err) => this.error.set(err.error?.detail || 'Não foi possível registrar o pagamento.'),
    });
  }

  toggleReconcile(payable: PayableDetail, payment: { id: string; reconciled: boolean }) {
    if (this.saving()) return;
    this.saving.set(true);
    this.api.reconcilePayablePayment(payable.id, payment.id, !payment.reconciled).pipe(finalize(() => this.saving.set(false))).subscribe({
      next: (updated) => { this.detail.set(updated); this.afterMutation(payment.reconciled ? 'Conciliação desfeita.' : 'Pagamento conciliado.'); },
      error: (err) => this.error.set(err.error?.detail || 'Não foi possível atualizar a conciliação.'),
    });
  }

  removePayment(payable: PayableDetail, payment: { id: string }) {
    if (this.saving()) return;
    if (!confirm('Remover este pagamento do título? O saldo volta a ficar em aberto.')) return;
    this.saving.set(true);
    this.api.removePayablePayment(payable.id, payment.id).pipe(finalize(() => this.saving.set(false))).subscribe({
      next: (updated) => { this.detail.set(updated); this.paymentDraft.update((draft) => ({ ...draft, amount: Number(updated.balance) })); this.afterMutation('Pagamento removido.'); },
      error: (err) => this.error.set(err.error?.detail || 'Não foi possível remover o pagamento.'),
    });
  }

  updateDueDate(payable: PayableDetail, value: string) {
    if (!value || dateOnlyValue(value) === dateOnlyValue(payable.due_date)) return;
    this.saving.set(true);
    this.api.updatePayable(payable.id, { due_date: value }).pipe(finalize(() => this.saving.set(false))).subscribe({
      next: (updated) => { this.detail.set(updated); this.afterMutation('Vencimento atualizado.'); },
      error: (err) => this.error.set(err.error?.detail || 'Não foi possível alterar o vencimento.'),
    });
  }

  private afterMutation(text: string) {
    this.message.set(text);
    this.load();
    this.loadReport();
  }
}
