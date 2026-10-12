import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subject, debounceTime } from 'rxjs';
import { CurrencyPipe, DatePipe, DecimalPipe } from '@angular/common';
import { Component, DestroyRef, OnInit, computed, inject, signal, viewChild } from '@angular/core';
import {
  FormArray,
  FormBuilder,
  FormsModule,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { finalize } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { LiveUpdatesService } from '../../core/live-updates.service';
import { AuthService } from '../../core/auth.service';
import {
  PaymentConditionType,
  Product,
  Purchase,
  PurchaseItem,
  PurchaseListItem,
  PurchasePayable,
  PurchaseQuote,
  PurchaseStatus,
} from '../../core/models';
import {
  canAdjustStock,
  canManageCatalog,
  canManagePurchases,
  canReadCosts,
} from '../../core/user-access';
import { DateRange, quickDateRange } from '../../core/quick-date-ranges';
import { PageHeader } from '../../shared/page-header';
import { PeriodFilter } from '../../shared/period-filter';
import { MoneyInputDirective } from '../../shared/money-input.directive';
import { dateOnlyLabel, dateOnlyValue } from '../../shared/date-only';
import { PurchaseDelete } from './purchase-delete';
import { PurchaseNew, SupplierOption } from './purchase-new';
import { PurchaseImportProducts } from './import/purchase-import-products';
import { PurchaseImportReview } from './import/purchase-import-review';
import { PurchaseImportState } from './import/purchase-import-state';

@Component({
  selector: 'app-purchases',
  imports: [
    CurrencyPipe,
    DatePipe,
    DecimalPipe,
    FormsModule,
    MoneyInputDirective,
    ReactiveFormsModule,
    PageHeader,
    PeriodFilter,
    PurchaseImportReview,
    PurchaseDelete,
    PurchaseNew,
  ],
  templateUrl: './purchases.html',
  styleUrl: './purchases.scss',
  providers: [PurchaseImportState, PurchaseImportProducts],
  host: { '(document:click)': 'closeRowMenu()', '(window:scroll)': 'closeRowMenu()' },
})
export class PurchasesPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly live = inject(LiveUpdatesService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly auth = inject(AuthService);
  private readonly fb = inject(FormBuilder);
  private readonly importFlow = inject(PurchaseImportState);
  // A revisão vive em componentes próprios; a página só mostra o aviso e o estado do botão.
  readonly importError = this.importFlow.importError;
  readonly importLoading = this.importFlow.importLoading;
  readonly importReview = this.importFlow.importReview;
  readonly purchases = signal<PurchaseListItem[]>([]);
  private readonly newPurchase = viewChild(PurchaseNew);

  /** Abre o cadastro manual; o menu da linha sai de cena antes. */
  openNew() {
    this.closeRowMenu();
    this.newPurchase()?.open();
  }
  /** Compra criada no cadastro manual: entra na lista e abre o detalhe. */
  onCreated(purchase: Purchase) {
    this.purchases.update((list) => [purchase, ...list]);
    this.openDetails(purchase);
  }
  /** Fornecedor cadastrado dentro do cadastro de compra entra na lista da página. */
  onSupplierCreated(supplier: SupplierOption) {
    this.suppliers.update((items) =>
      items.some((entry) => entry.id === supplier.id) ? items : [...items, supplier],
    );
  }
  /** Produtos do catálogo disponíveis para vincular numa linha da compra. */
  availableProducts(stockType: 'product' | 'warehouse') {
    return this.products().filter((product) => product.stock_type === stockType);
  }
  /** Fornecedor pelo nome digitado (o cadastro rápido e o rascunho usam o mesmo atalho). */
  supplierByName(name: string | null | undefined) {
    const key = (name || '').trim().toLowerCase();
    return key
      ? (this.suppliers().find((supplier) => supplier.name.toLowerCase() === key) ?? null)
      : null;
  }

  onImportDocument(event: Event) {
    this.importFlow.startAnalysis(event);
  }
  /** Compra criada pela revisão do documento: entra na lista, avisa do anexo e abre o detalhe. */
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
  readonly products = signal<Product[]>([]);
  readonly suppliers = signal<
    Array<{
      id: string;
      name: string;
      contact: string | null;
      default_delivery_days: number | null;
      default_payment_terms: string | null;
    }>
  >([]);
  readonly detail = signal<Purchase | null>(null);
  readonly page = signal(1);
  readonly pageSize = 25;
  readonly selectedIds = signal<Record<string, boolean>>({});
  readonly draftEditor = signal(false);
  readonly draftHeader = signal({
    supplier_name: '',
    supplier_order_number: '',
    document_date: '',
    needed_by: '',
    notes: '',
  });
  readonly lineDrafts = signal<
    Record<string, { description: string; sku: string; unit: string; quantity: number }>
  >({});
  readonly newLineDraft = signal({ description: '', sku: '', unit: 'un', quantity: 1 });
  readonly rowMenuId = signal<string | null>(null);
  readonly rowMenuPosition = signal<{ top: number; left: number } | null>(null);
  readonly saving = signal(false);
  readonly error = signal('');
  readonly message = signal('');
  readonly search = signal('');
  private readonly searchChanges = new Subject<string>();
  readonly statusFilter = signal('all');
  readonly receiveValues = signal<
    Record<string, { quantity: number; productId: string; create: boolean }>
  >({});
  readonly receiptIds = signal<Record<string, string>>({});
  readonly receiveObservations = signal<Record<string, string>>({});
  readonly quoteCosts = signal<Record<string, number>>({});
  readonly quoteCostValidity = signal<Record<string, boolean>>({});
  readonly quoteTotalValue = signal<number | null>(null);
  readonly quoteRounding = signal(0);
  readonly lifecycleForm = signal<{
    mode: 'cancel' | 'close';
    reason: string;
    resolution: 'keep_received' | 'return_received';
  } | null>(null);
  readonly deleteTarget = signal<Purchase | null>(null);
  readonly selectedFiles = signal<File[]>([]);
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
  readonly statuses: { value: string; label: string }[] = [
    { value: 'negotiating', label: 'Em negociação' },
    { value: 'approved', label: 'Aprovada' },
    { value: 'ordered', label: 'Pedido enviado' },
    { value: 'partially_received', label: 'Recebimento parcial' },
    { value: 'received', label: 'Recebida' },
    { value: 'closed', label: 'Encerrada' },
    { value: 'cancelled', label: 'Cancelada' },
  ];
  readonly workflow = [
    { value: 'negotiating', label: 'Negociação' },
    { value: 'approved', label: 'Aprovação' },
    { value: 'ordered', label: 'Pedido' },
    { value: 'received', label: 'Recebimento' },
  ];
  readonly quoteForm = this.fb.nonNullable.group({
    supplier_name: ['', Validators.required],
    supplier_contact: [''],
    freight_amount: [0, [Validators.required, Validators.min(0)]],
    tax_amount: [0, [Validators.required, Validators.min(0)]],
    discount_amount: [0, [Validators.required, Validators.min(0)]],
    allocation_method: ['proportional' as 'proportional' | 'quantity'],
    delivery_days: [null as number | null],
    payment_type: ['cash' as PaymentConditionType],
    installment_count: [1, [Validators.min(1), Validators.max(36)]],
    first_due_days: [30, [Validators.min(0)]],
    interval_days: [30, [Validators.min(1)]],
    payment_terms: [''],
    notes: [''],
  });
  readonly total = signal(0);
  readonly summaryCounts = signal({ negotiating: 0, ordered: 0, received: 0 });
  readonly summary = computed(() => {
    const counts = this.summaryCounts();
    return [
      {
        status: 'negotiating',
        label: 'Em negociação',
        count: counts.negotiating,
        note: 'Aguardando propostas',
      },
      {
        status: 'ordered',
        label: 'Aguardando recebimento',
        count: counts.ordered,
        note: 'Peças e materiais pendentes',
      },
      {
        status: 'received',
        label: 'Concluídas',
        count: counts.received,
        note: 'Compras recebidas ou despesas lançadas',
      },
    ];
  });

  ngOnInit() {
    this.load();
    this.refreshProducts();
    this.loadSuppliers();
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
    this.quoteForm.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      const purchase = this.detail();
      const typed = this.quoteTotalValue();
      if (purchase && typed !== null) this.distributeQuoteTotal(purchase, typed);
    });
  }
  private refreshProducts() {
    this.api
      .products('', false)
      .subscribe({ next: (items) => this.products.set(items), error: () => undefined });
  }
  private loadSuppliers() {
    this.api
      .suppliers()
      .subscribe({ next: (items) => this.suppliers.set(items), error: () => undefined });
  }

  load() {
    this.api
      .purchases({
        limit: this.pageSize,
        offset: (this.page() - 1) * this.pageSize,
        search: this.search().trim() || undefined,
        status: this.statusFilter() === 'all' ? undefined : this.statusFilter(),
        startDate: this.startDate() || undefined,
        endDate: this.endDate() || undefined,
      })
      .subscribe({
        next: (page) => {
          this.purchases.set(page.items);
          this.total.set(page.total);
          this.summaryCounts.set(page.summary);
        },
        error: () => this.error.set('Não foi possível carregar as compras. Tente novamente.'),
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
    this.statusFilter.set(this.statusFilter() === status ? 'all' : status);
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
    this.detail.set(null);
    this.newPurchase()?.openCopy(purchase);
  }
  setAttachments(files: FileList | null) {
    this.selectedFiles.set(files ? Array.from(files).slice(0, 10) : []);
  }
  uploadAttachments(purchase: Purchase, files: FileList | null) {
    const selected = files ? Array.from(files).slice(0, 10) : [];
    if (!selected.length) return;
    this.saving.set(true);
    this.api
      .uploadPurchaseAttachments(purchase.id, selected)
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe({
        next: (updated) => this.setPurchase(updated),
        error: (err) =>
          this.error.set(err.error?.detail || 'Não foi possível anexar os documentos.'),
      });
  }
  downloadAttachment(purchase: Purchase, attachment: Purchase['attachments'][number]) {
    this.api.downloadPurchaseAttachment(purchase.id, attachment.id, attachment.filename);
  }
  formatBytes(bytes: number) {
    return bytes < 1024 * 1024
      ? `${Math.ceil(bytes / 1024)} KB`
      : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  }
  openDetails(purchase: PurchaseListItem) {
    // A lista não traz histórico, anexos nem títulos (projeção leve): o detalhe busca a
    // compra completa ao abrir, então a tela sempre mostra o estado atual.
    this.closeRowMenu();
    this.error.set('');
    this.api.purchase(purchase.id).subscribe({
      next: (full) => this.showDetail(full),
      error: () => this.error.set('Não foi possível abrir a compra. Tente novamente.'),
    });
  }
  private showDetail(purchase: Purchase) {
    this.receiveValues.set(
      Object.fromEntries(
        purchase.items.map((item) => [
          item.id,
          {
            quantity: Math.max(0, item.quantity - item.received_quantity),
            productId: item.product_id || '',
            create: purchase.purchase_type === 'parts' && !item.product_id,
          },
        ]),
      ),
    );
    this.quoteCosts.set(Object.fromEntries(purchase.items.map((item) => [item.id, 0])));
    this.quoteCostValidity.set({});
    this.quoteTotalValue.set(null);
    this.quoteRounding.set(0);
    this.primeDrafts(purchase);
    this.draftEditor.set(false);
    this.detail.set(purchase);
  }
  selectedQuote(purchase: PurchaseListItem) {
    return purchase.quotes.find((quote) => quote.id === purchase.selected_quote_id) ?? null;
  }
  // O detalhe mostra o rateio e a condição da cotação: ali a compra é o registro completo.
  selectedDetailQuote(purchase: Purchase): PurchaseQuote | null {
    return purchase.quotes.find((quote) => quote.id === purchase.selected_quote_id) ?? null;
  }
  statusLabel(status: PurchaseStatus) {
    return this.statuses.find((entry) => entry.value === status)?.label ?? status;
  }
  purchaseStatusLabel(purchase: PurchaseListItem) {
    return this.statusLabel(purchase.status);
  }
  purchaseStatusNote(purchase: Purchase) {
    if (purchase.status === 'cancelled')
      return purchase.cancel_reason ? `Cancelada · ${purchase.cancel_reason}` : 'Compra cancelada.';
    if (purchase.status === 'closed')
      return 'Saldo pendente encerrado; o material recebido foi mantido no estoque.';
    return '';
  }
  payableLabel(payable: PurchasePayable) {
    if (payable.status === 'paid')
      return `Pago${payable.payment_method ? ' · ' + payable.payment_method : ''}`;
    if (payable.status === 'cancelled') return 'Encerrado com o cancelamento';
    if (payable.status === 'partial')
      return `Baixa parcial · vence ${this.dateLabel(payable.due_date)}`;
    return `Vence ${this.dateLabel(payable.due_date)}`;
  }
  dateLabel(value: string) {
    return dateOnlyLabel(value);
  }
  dateOnly(value: string | null | undefined) {
    return dateOnlyLabel(value);
  }
  isActive(purchase: Purchase) {
    return purchase.status !== 'cancelled' && purchase.status !== 'closed';
  }
  hasReceived(purchase: Purchase) {
    return purchase.items.some(
      (item) => item.received_quantity - (item.returned_quantity ?? 0) > 0,
    );
  }
  stepIndex(status: PurchaseStatus) {
    if (status === 'cancelled') return -1;
    if (status === 'received' || status === 'closed') return 4;
    if (status === 'partially_received') return 3;
    return ['negotiating', 'approved', 'ordered'].indexOf(status);
  }
  // A API serializa Decimal como string: some sempre com Number para não concatenar.
  progress(item: PurchaseItem) {
    const quantity = Number(item.quantity ?? 0);
    return quantity ? Math.min(100, (Number(item.received_quantity ?? 0) / quantity) * 100) : 0;
  }
  totalUnits(purchase: Purchase) {
    return purchase.items.reduce((sum, item) => sum + Number(item.quantity ?? 0), 0);
  }
  receivedUnits(purchase: Purchase) {
    return purchase.items.reduce((sum, item) => sum + Number(item.received_quantity ?? 0), 0);
  }
  receiveQty(item: PurchaseItem) {
    return this.receiveValues()[item.id]?.quantity ?? 0;
  }
  receiveObservation(item: PurchaseItem) {
    return this.receiveObservations()[item.id] ?? '';
  }
  setReceiveObservation(item: PurchaseItem, value: string) {
    this.receiveObservations.update((values) => ({ ...values, [item.id]: value }));
    this.clearReceiptId(item);
  }
  setReceiveQty(item: PurchaseItem, value: string) {
    this.receiveValues.update((values) => ({
      ...values,
      [item.id]: { ...values[item.id], quantity: Number(value) },
    }));
    this.clearReceiptId(item);
  }
  receiveProduct(item: PurchaseItem) {
    return this.receiveValues()[item.id]?.productId ?? '';
  }
  setReceiveProduct(item: PurchaseItem, value: string) {
    this.receiveValues.update((values) => ({
      ...values,
      [item.id]: { ...values[item.id], productId: value, create: false },
    }));
    this.clearReceiptId(item);
  }
  createNewProduct(item: PurchaseItem) {
    return this.receiveValues()[item.id]?.create ?? false;
  }
  setCreateNewProduct(item: PurchaseItem, value: boolean) {
    this.receiveValues.update((values) => ({
      ...values,
      [item.id]: {
        ...values[item.id],
        create: value,
        productId: value ? '' : (values[item.id]?.productId ?? ''),
      },
    }));
    this.clearReceiptId(item);
  }
  quoteUnitCost(item: PurchaseItem) {
    return this.quoteCosts()[item.id] ?? 0;
  }
  quoteSubtotal(purchase: Purchase) {
    return purchase.items.reduce(
      (sum, item) => sum + this.quoteUnitCost(item) * Number(item.quantity),
      0,
    );
  }
  /** O último campo editado manda: o total digitado prevalece; sem ele, o unitário alimenta o total. */
  quoteTotal(purchase: Purchase) {
    const typed = this.quoteTotalValue();
    return typed === null ? this.quoteComputedTotal(purchase) : typed;
  }
  quoteComputedTotal(purchase: Purchase) {
    const value = this.quoteForm.getRawValue();
    return this.round2(
      this.quoteSubtotal(purchase) +
        Number(value.freight_amount || 0) +
        Number(value.tax_amount || 0) -
        Number(value.discount_amount || 0),
    );
  }
  /** Líquido das peças: total − frete − impostos + desconto. Negativo é proposta impossível. */
  quoteNet(purchase: Purchase) {
    const value = this.quoteForm.getRawValue();
    return this.round2(
      this.quoteTotal(purchase) -
        Number(value.freight_amount || 0) -
        Number(value.tax_amount || 0) +
        Number(value.discount_amount || 0),
    );
  }
  setQuoteConditionType(value: string) {
    this.quoteForm.controls.payment_type.setValue(value as PaymentConditionType);
  }
  setQuoteConditionNumber(
    field: 'installment_count' | 'first_due_days' | 'interval_days',
    value: string,
  ) {
    this.quoteForm.controls[field].setValue(Number(value) || 0);
  }
  applyQuoteConditionPreset(preset: 'cash' | '30' | '30/60' | '30/60/90') {
    if (preset === 'cash') {
      this.quoteForm.patchValue({
        payment_type: 'cash',
        installment_count: 1,
        first_due_days: 0,
        interval_days: 30,
      });
      return;
    }
    const days = preset.split('/').map((value) => Number(value));
    this.quoteForm.patchValue({
      payment_type: days.length > 1 ? 'installments' : 'cash',
      installment_count: days.length,
      first_due_days: days[0],
      interval_days: days.length > 1 ? days[1] - days[0] : 30,
    });
  }
  /** Condição legível que será gravada no título a pagar. */
  quoteConditionPreview() {
    const value = this.quoteForm.getRawValue();
    if (value.payment_type === 'cash') {
      return value.first_due_days > 0 ? `à vista em ${value.first_due_days} dias` : 'à vista';
    }
    const offsets =
      value.payment_type === 'entry'
        ? [
            value.first_due_days,
            ...Array.from(
              { length: value.installment_count },
              (_, index) => value.first_due_days + (index + 1) * value.interval_days,
            ),
          ]
        : Array.from(
            { length: value.installment_count },
            (_, index) => value.first_due_days + index * value.interval_days,
          );
    return (value.payment_type === 'entry' ? 'entrada + ' : '') + offsets.join('/');
  }

  /** Condição legível da proposta, igual à que será gravada no título a pagar (P12). */
  quoteConditionLabel(quote: PurchaseQuote) {
    if (!quote.payment_type || quote.payment_type === 'cash') {
      return quote.first_due_days ? `À vista em ${quote.first_due_days} dias` : 'À vista';
    }
    const count = quote.installment_count ?? 1;
    const first = quote.first_due_days ?? 0;
    const interval = quote.interval_days ?? 30;
    const offsets =
      quote.payment_type === 'entry'
        ? [first, ...Array.from({ length: count }, (_, index) => first + (index + 1) * interval)]
        : Array.from({ length: count }, (_, index) => first + index * interval);
    return (quote.payment_type === 'entry' ? 'Entrada + ' : '') + offsets.join('/');
  }

  quoteDirectionNote() {
    return this.quoteTotalValue() === null
      ? 'o custo unitário de cada peça alimenta o total.'
      : 'o total digitado foi distribuído entre as peças pelo rateio escolhido.';
  }
  quoteMismatch(purchase: Purchase) {
    return (
      Math.abs(this.quoteComputedTotal(purchase) - this.quoteTotal(purchase)) >
      0.01 * Math.max(1, purchase.items.length)
    );
  }
  private round2(value: number) {
    return Math.round(value * 100) / 100;
  }
  setQuoteTotal(value: number | null) {
    const purchase = this.detail();
    if (value === null) {
      this.quoteTotalValue.set(null);
      this.quoteRounding.set(0);
      return;
    }
    this.quoteTotalValue.set(value);
    if (purchase) this.distributeQuoteTotal(purchase, value);
  }
  /** Distribui o líquido da proposta pelos itens e fecha a sobra de centavos no maior item. */
  private distributeQuoteTotal(purchase: Purchase, total: number) {
    if (!purchase.items.length) return;
    const value = this.quoteForm.getRawValue();
    const netCents = Math.round(
      (total -
        Number(value.freight_amount || 0) -
        Number(value.tax_amount || 0) +
        Number(value.discount_amount || 0)) *
        100,
    );
    const byQuantity = value.allocation_method === 'quantity';
    // A API serializa Decimal como texto: a quantidade chega como string e precisa ser número.
    let weights = purchase.items.map((item) =>
      byQuantity ? Number(item.quantity) : this.quoteUnitCost(item) * Number(item.quantity),
    );
    if (!byQuantity && weights.every((weight) => weight <= 0))
      weights = purchase.items.map((item) => Number(item.quantity));
    const weightSum = weights.reduce((sum, weight) => sum + weight, 0);
    const shares = weights.map((weight) =>
      weightSum > 0 ? Math.round((netCents * weight) / weightSum) : 0,
    );
    if (weightSum <= 0) shares[0] = netCents;
    const largest = weights.reduce(
      (best, weight, index) => (weight > weights[best] ? index : best),
      0,
    );
    const residual = netCents - shares.reduce((sum, share) => sum + share, 0);
    shares[largest] += residual;
    const costs: Record<string, number> = {};
    purchase.items.forEach((item, index) => {
      costs[item.id] = this.round2(shares[index] / 100 / Number(item.quantity));
    });
    this.quoteCosts.set(costs);
    // A sobra que aparece para o usuário é a diferença real entre o líquido digitado e a
    // soma dos unitários com duas casas, que nem sempre fecha em quantidades quebradas.
    const roundedSubtotal = purchase.items.reduce(
      (sum, item) => sum + costs[item.id] * Number(item.quantity),
      0,
    );
    this.quoteRounding.set(this.round2(netCents / 100 - roundedSubtotal));
  }
  setQuoteUnitCost(item: PurchaseItem, value: number | null) {
    if (value === null) return;
    this.quoteTotalValue.set(null);
    this.quoteRounding.set(0);
    this.quoteCosts.update((costs) => ({ ...costs, [item.id]: value }));
  }
  setQuoteCostValidity(itemId: string, invalid: boolean) {
    this.quoteCostValidity.update((values) => ({ ...values, [itemId]: invalid }));
  }
  quoteCostHasErrors() {
    return Object.values(this.quoteCostValidity()).some(Boolean);
  }
  quoteCostsComplete(purchase: Purchase) {
    return purchase.items.every(
      (item) => Number.isFinite(this.quoteUnitCost(item)) && this.quoteUnitCost(item) >= 0,
    );
  }
  addQuote() {
    const purchase = this.detail();
    if (
      !purchase ||
      this.quoteForm.invalid ||
      this.quoteCostHasErrors() ||
      !this.quoteCostsComplete(purchase) ||
      this.quoteTotal(purchase) < 0 ||
      this.saving()
    )
      return;
    this.saving.set(true);
    this.error.set('');
    const value = this.quoteForm.getRawValue();
    this.api
      .addPurchaseQuote(purchase.id, {
        ...value,
        total: this.quoteTotal(purchase),
        item_costs: this.quoteCosts(),
      })
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe({
        next: (updated) => {
          this.setPurchase(updated);
          this.quoteForm.reset({
            supplier_name: '',
            supplier_contact: '',
            freight_amount: 0,
            tax_amount: 0,
            discount_amount: 0,
            allocation_method: 'proportional',
            delivery_days: null,
            payment_type: 'cash',
            installment_count: 1,
            first_due_days: 30,
            interval_days: 30,
            payment_terms: '',
            notes: '',
          });
          this.quoteCosts.set(Object.fromEntries(purchase.items.map((item) => [item.id, 0])));
          this.quoteTotalValue.set(null);
          this.quoteRounding.set(0);
        },
        error: (err) =>
          this.error.set(err.error?.detail || 'Não foi possível registrar a cotação.'),
      });
  }
  selectQuote(id: string) {
    const purchase = this.detail();
    if (!purchase || this.saving()) return;
    if (!confirm('Aprovar esta cotação? A compra seguirá para envio do pedido ao fornecedor.'))
      return;
    this.runAction(this.api.selectPurchaseQuote(purchase.id, id));
  }
  placeOrder() {
    const purchase = this.detail();
    if (purchase) this.runAction(this.api.placePurchaseOrder(purchase.id));
  }
  receive(item: PurchaseItem) {
    const purchase = this.detail();
    if (!purchase || this.saving()) return;
    const choice = this.receiveValues()[item.id];
    if (!choice || choice.quantity <= 0) return;
    const receiptId = this.receiptIds()[item.id] ?? crypto.randomUUID();
    this.receiptIds.update((ids) => ({ ...ids, [item.id]: receiptId }));
    this.saving.set(true);
    this.error.set('');
    this.api
      .receivePurchase(purchase.id, {
        items: [
          {
            item_id: item.id,
            receipt_id: receiptId,
            quantity: choice.quantity,
            product_id: choice.productId || null,
            create_product: choice.create,
            observation: this.receiveObservation(item) || null,
          },
        ],
      })
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe({
        next: (updated) => {
          this.setPurchase(updated);
          this.clearReceiptId(item);
          this.api.products('', false).subscribe((items) => this.products.set(items));
        },
        error: (err) =>
          this.error.set(err.error?.detail || 'Não foi possível registrar o recebimento.'),
      });
  }
  private clearReceiptId(item: PurchaseItem) {
    this.receiptIds.update((ids) => {
      const updated = { ...ids };
      delete updated[item.id];
      return updated;
    });
  }
  openLifecycleForm(mode: 'cancel' | 'close') {
    const purchase = this.detail();
    if (!purchase) return;
    this.error.set('');
    this.lifecycleForm.set({
      mode,
      reason: '',
      resolution: this.hasReceived(purchase) ? 'keep_received' : 'return_received',
    });
  }
  setLifecycleReason(value: string) {
    this.lifecycleForm.update((form) => (form ? { ...form, reason: value } : form));
  }
  setLifecycleResolution(value: 'keep_received' | 'return_received') {
    this.lifecycleForm.update((form) => (form ? { ...form, resolution: value } : form));
  }
  submitLifecycle(purchase: Purchase) {
    const form = this.lifecycleForm();
    if (!form || this.saving() || form.reason.trim().length < 3) return;
    const request =
      form.mode === 'cancel'
        ? this.api.cancelPurchaseWithReason(purchase.id, {
            reason: form.reason.trim(),
            resolution: form.resolution,
          })
        : this.api.closePurchaseBalance(purchase.id, { reason: form.reason.trim() });
    this.saving.set(true);
    this.error.set('');
    request.pipe(finalize(() => this.saving.set(false))).subscribe({
      next: (updated) => {
        this.lifecycleForm.set(null);
        this.setPurchase(updated);
      },
      error: (err) => this.error.set(err.error?.detail || 'Não foi possível concluir a ação.'),
    });
  }
  receiveAll(purchase: Purchase) {
    if (this.saving()) return;
    if (
      !confirm(
        `Receber todos os itens pendentes de ${purchase.number}? Itens sem produto vinculado serão cadastrados no catálogo.`,
      )
    )
      return;
    this.saving.set(true);
    this.error.set('');
    this.api
      .receivePurchaseInFull(purchase.id, { create_products: true })
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe({
        next: (updated) => {
          this.setPurchase(updated);
          this.api.products('', false).subscribe((items) => this.products.set(items));
        },
        error: (err) =>
          this.error.set(err.error?.detail || 'Não foi possível registrar o recebimento.'),
      });
  }
  settlePayable(purchase: Purchase, payable: PurchasePayable) {
    if (this.saving()) return;
    const amount = payable.amount.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
    if (!confirm(`Registrar o pagamento de ${amount} do título de ${purchase.number}?`)) return;
    this.saving.set(true);
    this.error.set('');
    this.api
      .settlePurchasePayable(purchase.id, payable.id)
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe({
        next: () => {
          this.load();
          this.api.purchase(purchase.id).subscribe((full) => this.detail.set(full));
        },
        error: (err) =>
          this.error.set(err.error?.detail || 'Não foi possível registrar o pagamento.'),
      });
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
  /** Compra excluída pelo componente de confirmação: sai da lista e fecha o detalhe. */
  onDeleted(id: string) {
    const removed = this.purchases().find((item) => item.id === id);
    if (this.detail()?.id === id) this.detail.set(null);
    this.deleteTarget.set(null);
    this.purchases.update((items) => items.filter((item) => item.id !== id));
    this.message.set(`${removed?.number ?? 'A compra'} foi excluída com os registros ligados.`);
  }
  isOverdue(purchase: PurchaseListItem) {
    if (!purchase.needed_by || !['ordered', 'partially_received'].includes(purchase.status))
      return false;
    const today = new Date();
    const todayKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
    return dateOnlyValue(purchase.needed_by) < todayKey;
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
  pagedPurchases() {
    return this.purchases();
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
  openDraftEditor() {
    this.draftEditor.set(true);
  }
  closeDraftEditor() {
    this.draftEditor.set(false);
  }
  setDraftHeader(
    field: 'supplier_name' | 'supplier_order_number' | 'document_date' | 'needed_by' | 'notes',
    value: string,
  ) {
    this.draftHeader.update((header) => ({ ...header, [field]: value }));
  }
  saveDraftHeader(purchase: Purchase) {
    if (this.saving()) return;
    const header = this.draftHeader();
    this.saving.set(true);
    this.error.set('');
    this.api
      .updatePurchase(purchase.id, {
        supplier_name: header.supplier_name || null,
        supplier_id: this.supplierByName(header.supplier_name)?.id ?? null,
        supplier_order_number: header.supplier_order_number || null,
        document_date: header.document_date || null,
        needed_by: header.needed_by || null,
        notes: header.notes || null,
      })
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe({
        next: (updated) => this.applyUpdate(updated),
        error: (err) =>
          this.error.set(err.error?.detail || 'Não foi possível salvar os dados do pedido.'),
      });
  }
  setLineDraft(itemId: string, field: 'description' | 'sku' | 'unit' | 'quantity', value: string) {
    this.lineDrafts.update((drafts) => ({
      ...drafts,
      [itemId]: {
        ...(drafts[itemId] ?? { description: '', sku: '', unit: 'un', quantity: 0 }),
        [field]: field === 'quantity' ? Number(value) : value,
      },
    }));
  }
  saveLine(purchase: Purchase, item: PurchaseItem) {
    const draft = this.lineDrafts()[item.id];
    if (!draft || this.saving()) return;
    this.saving.set(true);
    this.error.set('');
    this.api
      .updatePurchaseItem(purchase.id, item.id, {
        description: draft.description,
        sku: draft.sku,
        unit: draft.unit,
        quantity: draft.quantity,
      })
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe({
        next: (updated) => this.applyUpdate(updated),
        error: (err) => this.error.set(err.error?.detail || 'Não foi possível salvar a peça.'),
      });
  }
  removePurchaseLine(purchase: Purchase, item: PurchaseItem) {
    if (this.saving()) return;
    if (!confirm(`Remover ${item.description} desta negociação?`)) return;
    this.saving.set(true);
    this.error.set('');
    this.api
      .removePurchaseItem(purchase.id, item.id)
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe({
        next: (updated) => this.applyUpdate(updated),
        error: (err) => this.error.set(err.error?.detail || 'Não foi possível remover a peça.'),
      });
  }
  setNewLineDraft(field: 'description' | 'sku' | 'unit' | 'quantity', value: string) {
    this.newLineDraft.update((draft) => ({
      ...draft,
      [field]: field === 'quantity' ? Number(value) : value,
    }));
  }
  addDraftLine(purchase: Purchase) {
    const draft = this.newLineDraft();
    if (!draft.description.trim() || draft.quantity <= 0 || this.saving()) return;
    this.saving.set(true);
    this.error.set('');
    this.api
      .addPurchaseItem(purchase.id, {
        description: draft.description.trim(),
        sku: draft.sku.trim(),
        unit: draft.unit.trim() || 'un',
        quantity: draft.quantity,
        unit_cost: 0,
      })
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe({
        next: (updated) => {
          this.newLineDraft.set({ description: '', sku: '', unit: 'un', quantity: 1 });
          this.applyUpdate(updated);
        },
        error: (err) => this.error.set(err.error?.detail || 'Não foi possível incluir a peça.'),
      });
  }
  private runAction(request: ReturnType<ApiService['placePurchaseOrder']>) {
    const purchase = this.detail();
    if (!purchase) return;
    this.saving.set(true);
    this.error.set('');
    request.pipe(finalize(() => this.saving.set(false))).subscribe({
      next: (updated) => {
        this.setPurchase(updated);
        if (updated.status === 'received')
          this.api.products('', false, 'product').subscribe((items) => this.products.set(items));
      },
      error: (err) =>
        this.error.set(err.error?.detail || 'Não foi possível atualizar esta compra.'),
    });
  }
  private primeDrafts(purchase: Purchase) {
    this.lineDrafts.set(
      Object.fromEntries(
        purchase.items.map((item) => [
          item.id,
          {
            description: item.description,
            sku: item.sku,
            unit: item.unit,
            quantity: item.quantity,
          },
        ]),
      ),
    );
    this.draftHeader.set({
      supplier_name: purchase.supplier_name || '',
      supplier_order_number: purchase.supplier_order_number || '',
      document_date: purchase.document_date ? purchase.document_date.slice(0, 10) : '',
      needed_by: purchase.needed_by ? purchase.needed_by.slice(0, 10) : '',
      notes: purchase.notes || '',
    });
  }
  private applyUpdate(purchase: Purchase) {
    this.primeDrafts(purchase);
    this.detail.set(purchase);
    this.purchases.update((items) =>
      items.map((item) => (item.id === purchase.id ? purchase : item)),
    );
  }
  private setPurchase(purchase: Purchase) {
    this.applyUpdate(purchase);
    this.draftEditor.set(false);
  }
}
