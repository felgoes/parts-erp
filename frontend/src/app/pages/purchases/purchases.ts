import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subject, debounceTime, finalize } from 'rxjs';
import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, DestroyRef, OnInit, computed, inject, signal, viewChild } from '@angular/core';
import {
  FormsModule,
  ReactiveFormsModule,
} from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { ApiService } from '../../core/api.service';
import { LiveUpdatesService } from '../../core/live-updates.service';
import { AuthService } from '../../core/auth.service';
import {
  Product,
  Purchase,
  PurchaseListItem,
  PurchaseQuote,
} from '../../core/models';
import {
  canAdjustStock,
  canManageCatalog,
  canManagePurchases,
  canReadCosts,
} from '../../core/user-access';
import { DateRange, QuickDatePreset, matchingDatePreset, quickDateRange } from '../../core/quick-date-ranges';
import { PageHeader } from '../../shared/page-header';
import { PeriodFilter } from '../../shared/period-filter';
import { dateOnlyLabel, dateOnlyValue } from '../../shared/date-only';
import { RecordOrigin, readRecordOrigin, recordOrigin, restoreRecordPosition } from '../../shared/record-origin';
import { PURCHASE_GROUPS, purchaseGroup } from './purchase-status-groups';
import { PurchaseDelete } from './purchase-delete';
import { PurchaseNew, SupplierOption } from './purchase-new';
import { PurchaseDetail } from './detail/purchase-detail';
import { PurchaseDetailEditing } from './detail/purchase-detail-editing';
import { PurchaseDetailState } from './detail/purchase-detail-state';
import { PurchaseQuoteLogic } from './detail/purchase-quote-logic';
import { PurchaseImportProducts } from './import/purchase-import-products';
import { PurchaseImportReview } from './import/purchase-import-review';
import { PurchaseImportState } from './import/purchase-import-state';

@Component({
  selector: 'app-purchases',
  imports: [
    CurrencyPipe,
    DatePipe,
    FormsModule,
    ReactiveFormsModule,
    PageHeader,
    PeriodFilter,
    PurchaseImportReview,
    PurchaseDelete,
    PurchaseNew,
    PurchaseDetail,
  ],
  templateUrl: './purchases.html',
  styleUrl: './purchases.scss',
  providers: [
    PurchaseImportState,
    PurchaseImportProducts,
    PurchaseDetailState,
    PurchaseQuoteLogic,
    PurchaseDetailEditing,
  ],
  host: { '(document:click)': 'closeRowMenu()', '(window:scroll)': 'closeRowMenu()' },
})
export class PurchasesPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  readonly recordId = this.route.snapshot.paramMap.get('id');
  readonly origin = readRecordOrigin({ '/purchases': 'Compras' }, '/purchases');
  private pendingReturn = window.history.state?.recordReturn as RecordOrigin | undefined;
  private readonly live = inject(LiveUpdatesService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly auth = inject(AuthService);
  private readonly importFlow = inject(PurchaseImportState);
  readonly detailState = inject(PurchaseDetailState);
  // A revisão vive em componentes próprios; a página só mostra o aviso e o estado do botão.
  readonly importError = this.importFlow.importError;
  readonly importLoading = this.importFlow.importLoading;
  readonly importReview = this.importFlow.importReview;
  readonly purchases = signal<PurchaseListItem[]>([]);
  private readonly newPurchase = viewChild(PurchaseNew);

  openNew() {
    this.closeRowMenu();
    this.newPurchase()?.open();
  }
  onCreated(purchase: Purchase) {
    this.purchases.update((list) => [purchase, ...list]);
    this.openDetails(purchase);
  }
  onSupplierCreated(supplier: SupplierOption) {
    this.suppliers.update((items) =>
      items.some((entry) => entry.id === supplier.id) ? items : [...items, supplier],
    );
  }

  onImportDocument(event: Event) {
    this.importFlow.startAnalysis(event);
  }
  onImported(result: { purchase: Purchase; document: { filename: string; size: number } }) {
    const { purchase, document } = result;
    this.purchases.update((list) => [purchase, ...list]);
    const attached = purchase.attachments.some(
      (attachment) =>
        attachment.filename === document.filename && attachment.size_bytes === document.size,
    );
    if (!attached) this.error.set('O documento não voltou anexado; confira o anexo na compra.');
    this.openDetails(purchase);
  }
  canManagePurchases() {
    return canManagePurchases(this.auth.user()?.role);
  }
  canManageCatalog() {
    return canManageCatalog(this.auth.user()?.role);
  }
  canAdjustStock() {
    return canAdjustStock(this.auth.user()?.role);
  }
  canReadCosts() {
    return canReadCosts(this.auth.user()?.role);
  }
  readonly page = signal(1);
  readonly pageSize = 25;
  readonly selectedIds = signal<Record<string, boolean>>({});
  readonly rowMenuId = signal<string | null>(null);
  readonly rowMenuPosition = signal<{ top: number; left: number } | null>(null);
  readonly saving = signal(false);
  readonly error = signal('');
  readonly message = signal('');
  readonly search = signal('');
  private readonly searchChanges = new Subject<string>();
  readonly statusFilter = signal('all');
  readonly deleteTarget = signal<Purchase | null>(null);
  readonly expenseCategories = [
    'Aluguel',
    'Energia e água',
    'Internet e telefonia',
    'Contabilidade',
    'Marketing',
    'Frete e transporte',
    'Material de escritório',
    'Materiais de consumo e embalagem',
    'Impostos e taxas',
    'Serviços',
    'Outros',
  ];
  private readonly initialRange = quickDateRange('last30');
  readonly startDate = signal(this.initialRange.startDate);
  readonly endDate = signal(this.initialRange.endDate);
  readonly statuses = PURCHASE_GROUPS;
  readonly groupValue = (purchase: PurchaseListItem) => purchaseGroup(purchase.status).value;
  initialPreset: QuickDatePreset = 'last30';
  readonly detail = this.detailState.detail;
  readonly products = this.detailState.products;

  selectedQuote(purchase: PurchaseListItem) {
    return this.detailState.selectedQuote(purchase);
  }
  purchaseStatusLabel(purchase: PurchaseListItem) {
    return purchaseGroup(purchase.status).label;
  }
  dateOnly(value: string | null | undefined) {
    return this.detailState.dateOnly(value);
  }
  isOverdue(purchase: PurchaseListItem) {
    return this.detailState.isOverdue(purchase);
  }
  readonly suppliers = this.detailState.suppliers;

  openDetails(purchase: PurchaseListItem, event?: MouseEvent) {
    if (event?.ctrlKey || event?.metaKey || event?.shiftKey || event?.altKey) return;
    event?.preventDefault();
    this.closeRowMenu();
    const state = this.recordId ? { recordOrigin: this.origin } : recordOrigin(this.router.url, 'Compras', purchase.id, {
      search: this.search(), status: this.statusFilter(), page: this.page(),
      startDate: this.startDate(), endDate: this.endDate(),
    });
    void this.router.navigate(['/purchases', purchase.id], { state });
  }

  back(event?: MouseEvent): void {
    if (event?.ctrlKey || event?.metaKey || event?.shiftKey || event?.altKey) return;
    event?.preventDefault();
    void this.router.navigateByUrl(this.origin.path, { state: { recordReturn: this.origin } });
  }
  refreshProducts() {
    this.detailState.refreshProducts();
  }
  loadSuppliers() {
    this.detailState.loadSuppliers();
  }
  readonly total = signal(0);
  readonly summaryCounts = signal<Record<string, number>>({});
  readonly summary = computed(() => PURCHASE_GROUPS.map((group) => ({
    ...group, count: this.summaryCounts()[group.value] ?? 0,
  })));

  ngOnInit() {
    this.refreshProducts();
    this.loadSuppliers();
    if (this.recordId) {
      this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((params) => {
        const id = params.get('id');
        if (id) this.detailState.openDetails(id);
      });
      return;
    }
    const view = this.pendingReturn?.view as { search: string; status: string; page: number; startDate: string; endDate: string } | undefined;
    if (view) {
      this.search.set(view.search);
      this.statusFilter.set(view.status);
      this.page.set(view.page);
      this.startDate.set(view.startDate);
      this.endDate.set(view.endDate);
      this.initialPreset = matchingDatePreset(view.startDate, view.endDate);
    }
    this.load();
    // Busca no servidor: espera o usuário parar de digitar e volta para a primeira página.
    this.searchChanges
      .pipe(debounceTime(300), takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        this.page.set(1);
        this.load();
      });
    this.live.changes$
      .pipe(debounceTime(250), takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        this.load();
        this.refreshProducts();
        this.loadSuppliers();
      });
  }

  private loadVersion = 0;
  load() {
    const version = ++this.loadVersion;
    this.api
      .purchases({
        limit: this.pageSize,
        offset: (this.page() - 1) * this.pageSize,
        search: this.search().trim() || undefined,
        statusGroup: this.statusFilter() === 'all' ? undefined : this.statusFilter(),
        startDate: this.startDate() || undefined,
        endDate: this.endDate() || undefined,
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (page) => {
          if (version !== this.loadVersion) return;
          this.purchases.set(page.items);
          this.total.set(page.total);
          this.summaryCounts.set(page.summary.groups ?? {});
          restoreRecordPosition(this.pendingReturn);
          this.pendingReturn = undefined;
        },
        error: () => {
          if (version === this.loadVersion) this.error.set('Não foi possível carregar as compras. Tente novamente.');
        },
      });
  }
  onSearch(value: string) {
    this.search.set(value);
    this.searchChanges.next(value);
  }
  applyPeriod(range: DateRange) {
    this.startDate.set(range.startDate);
    this.endDate.set(range.endDate);
    this.page.set(1);
    this.load();
  }
  toggleStatus(status: string) {
    this.setStatus(this.statusFilter() === status ? 'all' : status);
  }
  setStatus(status: string) {
    this.statusFilter.set(status);
    this.page.set(1);
    this.load();
  }
  toggleRowMenu(id: string, event: Event) {
    event.stopPropagation();
    if (this.rowMenuId() === id) {
      this.closeRowMenu();
      return;
    }
    const trigger = event.currentTarget as HTMLElement;
    const rect = trigger.getBoundingClientRect();
    const menuWidth = 130;
    const menuHeight = 48;
    let top = rect.bottom + 4;
    if (top + menuHeight > window.innerHeight - 8) top = Math.max(8, rect.top - menuHeight - 4);
    const left = Math.max(8, Math.min(rect.right - menuWidth, window.innerWidth - menuWidth - 8));
    this.rowMenuPosition.set({ top, left });
    this.rowMenuId.set(id);
  }
  rowMenuPurchase() {
    return this.purchases().find((purchase) => purchase.id === this.rowMenuId()) ?? null;
  }
  closeRowMenu() {
    this.rowMenuId.set(null);
    this.rowMenuPosition.set(null);
  }
  copyPurchaseFromList(purchase: PurchaseListItem, event: Event) {
    event.stopPropagation();
    this.copyPurchase(purchase);
  }
  copyPurchase(purchase: PurchaseListItem) {
    this.closeRowMenu();
    this.newPurchase()?.openCopy(purchase);
  }

  openDelete(purchase: PurchaseListItem, event?: Event) {
    event?.stopPropagation();
    this.closeRowMenu();
    this.deleteTarget.set(null);
    // O aviso de exclusão lista o que será apagado (inclui título a pagar), então busca a
    // compra completa antes de abrir a confirmação.
    this.api.purchase(purchase.id).subscribe({
      next: (full) => this.deleteTarget.set(full),
      error: () => this.error.set('Não foi possível abrir a compra. Tente novamente.'),
    });
  }
  onDeleted(id: string) {
    const removed = this.purchases().find((item) => item.id === id);
    if (this.detail()?.id === id) this.back();
    this.deleteTarget.set(null);
    this.purchases.update((items) => items.filter((item) => item.id !== id));
    this.message.set(`${removed?.number ?? 'A compra'} foi excluída com os registros ligados.`);
    if (!this.recordId) this.load();
  }
  purchaseTotal(purchase: PurchaseListItem) {
    if (purchase.purchase_type === 'expense') return purchase.expense_amount ?? 0;
    // A linha da lista não carrega custo por item: o total vem do servidor, e quem não lê
    // financeiro recebe vazio — que é exatamente o comportamento desejado.
    return purchase.total_amount ?? 0;
  }
  totalPages() {
    return Math.max(1, Math.ceil(this.total() / this.pageSize));
  }
  goToPage(delta: number) {
    this.page.set(Math.min(this.totalPages(), Math.max(1, this.page() + delta)));
    this.load();
  }
  isSelectable(purchase: PurchaseListItem) {
    return (
      purchase.status === 'negotiating' &&
      !purchase.selected_quote_id &&
      purchase.items.every((item) => !item.received_quantity)
    );
  }
  isSelected(id: string) {
    return !!this.selectedIds()[id];
  }
  toggleSelection(id: string) {
    this.selectedIds.update((map) => ({ ...map, [id]: !map[id] }));
  }
  selectedPurchases() {
    return this.purchases().filter(
      (purchase) => this.selectedIds()[purchase.id] && this.isSelectable(purchase),
    );
  }
  clearSelection() {
    this.selectedIds.set({});
  }
  deleteSelectedDrafts() {
    const targets = this.selectedPurchases();
    if (!targets.length || this.saving()) return;
    if (
      !confirm(
        `Excluir ${targets.length} rascunho(s) selecionado(s)? Cada exclusão fica registrada no histórico de auditoria.`,
      )
    )
      return;
    this.saving.set(true);
    this.error.set('');
    const failures: string[] = [];
    let pending = targets.length;
    for (const target of targets) {
      this.api
        .deletePurchase(target.id)
        .pipe(
          finalize(() => {
            pending -= 1;
            if (!pending) {
              this.saving.set(false);
              this.clearSelection();
              this.error.set(failures.join(' · '));
            }
          }),
        )
        .subscribe({
          next: () =>
            this.purchases.update((items) => items.filter((item) => item.id !== target.id)),
          error: (err) =>
            failures.push(`${target.number}: ${err.error?.detail || 'falha ao excluir'}`),
        });
    }
  }
}
