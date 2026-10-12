import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { debounceTime } from 'rxjs';
import { CurrencyPipe, DatePipe, DecimalPipe } from '@angular/common';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { FormArray, FormBuilder, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { finalize } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { LiveUpdatesService } from '../../core/live-updates.service';
import { AuthService } from '../../core/auth.service';
import { PaymentConditionType, Product, Purchase, PurchaseItem, PurchaseListItem, PurchasePayable, PurchaseQuote, PurchaseStatus } from '../../core/models';
import { canAdjustStock, canManageCatalog, canManagePurchases, canReadCosts } from '../../core/user-access';
import { DateRange, quickDateRange } from '../../core/quick-date-ranges';
import { PageHeader } from '../../shared/page-header';
import { PeriodFilter } from '../../shared/period-filter';
import { MoneyInputDirective } from '../../shared/money-input.directive';
import { dateOnlyLabel, dateOnlyValue } from '../../shared/date-only';
import { ImportPlanError, buildImportPlan } from '../../shared/purchase-import-math';

@Component({
  selector: 'app-purchases',
  imports: [CurrencyPipe, DatePipe, DecimalPipe, FormsModule, MoneyInputDirective, ReactiveFormsModule, PageHeader, PeriodFilter],
  templateUrl: './purchases.html',
  styleUrl: './purchases.scss',
  host: { '(document:click)': 'closeRowMenu()', '(window:scroll)': 'closeRowMenu()' },
})
export class PurchasesPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly live = inject(LiveUpdatesService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly auth = inject(AuthService);
  private readonly fb = inject(FormBuilder);
  readonly purchases = signal<PurchaseListItem[]>([]);
  canManagePurchases() { return canManagePurchases(this.auth.user()?.role); }
  canManageCatalog() { return canManageCatalog(this.auth.user()?.role); }
  canAdjustStock() { return canAdjustStock(this.auth.user()?.role); }
  canReadCosts() { return canReadCosts(this.auth.user()?.role); }
  readonly products = signal<Product[]>([]);
  readonly suppliers = signal<Array<{ id: string; name: string; contact: string | null; default_delivery_days: number | null; default_payment_terms: string | null }>>([]);
  readonly detail = signal<Purchase | null>(null);
  readonly page = signal(1);
  readonly pageSize = 25;
  readonly selectedIds = signal<Record<string, boolean>>({});
  readonly draftEditor = signal(false);
  readonly draftHeader = signal({ supplier_name: '', supplier_order_number: '', document_date: '', needed_by: '', notes: '' });
  readonly lineDrafts = signal<Record<string, { description: string; sku: string; unit: string; quantity: number }>>({});
  readonly newLineDraft = signal({ description: '', sku: '', unit: 'un', quantity: 1 });
  readonly rowMenuId = signal<string | null>(null);
  readonly rowMenuPosition = signal<{ top: number; left: number } | null>(null);
  readonly showNew = signal(false);
  readonly saving = signal(false);
  readonly error = signal('');
  readonly message = signal('');
  readonly search = signal('');
  readonly statusFilter = signal('all');
  readonly receiveValues = signal<Record<string, { quantity: number; productId: string; create: boolean }>>({});
  readonly receiptIds = signal<Record<string, string>>({});
  readonly receiveObservations = signal<Record<string, string>>({});
  readonly quoteCosts = signal<Record<string, number>>({});
  readonly quoteCostValidity = signal<Record<string, boolean>>({});
  readonly quoteTotalValue = signal<number | null>(null);
  readonly quoteRounding = signal(0);
  readonly lifecycleForm = signal<{ mode: 'cancel' | 'close'; reason: string; resolution: 'keep_received' | 'return_received' } | null>(null);
  readonly deleteTarget = signal<Purchase | null>(null);
  readonly deleteReason = signal('');
  readonly importMoneyValidity = signal<Record<string, boolean>>({});
  readonly importProductSearch = signal<Record<number, string>>({});
  readonly importProductResults = signal<Record<number, Product[]>>({});
  private readonly importSearchRevision = signal<Record<number, number>>({});
  readonly importProductModal = signal(false);
  readonly importProductLine = signal<number | null>(null);
  readonly savingImportProduct = signal(false);
  readonly importProductError = signal('');
  readonly importProductDraft = signal({ sku: '', stock_type: 'product' as 'product' | 'warehouse', name: '', description: '', sale_price: 0, cost_price: 0, minimum_stock: 0, brand: '', manufacturer: '', manufacturer_part_number: '', barcode: '', category: '', item_condition: 'new' as 'new' | 'used' | 'refurbished', warranty_days: null as number | null, origin_country: '', weight_g: null as number | null, package_length_cm: null as number | null, package_width_cm: null as number | null, package_height_cm: null as number | null });
  private readonly importId = signal<string | null>(null);
  readonly selectedFiles = signal<File[]>([]);
  readonly importReview = signal<any | null>(null);
  readonly importProfiles = signal<Array<{ profile_id: string; name: string; kind: string; version: number }>>([]);
  readonly importDraft = signal<{ supplier: string; orderNumber: string; documentDate: string; total: number | null; shipping: number | null; discount: number | null; tax: number | null; currency: string | null; exchangeRate: number | null; paidAmount: number | null; items: Array<{ description: string; sku: string; quantity: number; unit_cost: number; confidence: number; product_id: string | null; stock_controlled: boolean; line_total: number; discount_amount: number; source: string; quantityDerived: boolean }> }>({ supplier: '', orderNumber: '', documentDate: '', total: null, shipping: null, discount: null, tax: null, currency: null, exchangeRate: null, paidAmount: null, items: [] });
  readonly importDuplicate = signal<{ purchase_id: string; purchase_number: string; purchase_status: string; cancelled: boolean } | null>(null);
  readonly importCheck = signal<{ items_total: number | null; subtotal?: number | null; closing_difference: number | null; subtotal_difference: number | null; balanced: boolean } | null>(null);
  readonly importType = signal<'parts' | 'expense'>('parts');
  readonly importCategory = signal('');
  readonly importPaidNow = signal(false);
  readonly importPaidDate = signal('');
  readonly importPaidMethod = signal('');
  readonly importFile = signal<File | null>(null);
  readonly importLoading = signal(false);
  readonly creatingImport = signal(false);
  readonly importError = signal('');
  // P0: mesmo rateio que o backend grava — a revisão mostra o custo final por peça e o fechamento.
  readonly importPlan = computed(() => {
    const draft = this.importDraft();
    try {
      return { plan: buildImportPlan(draft.items, draft), error: '' };
    } catch (error) {
      return {
        // A revisão continua mostrando o rateio quando só o fechamento do documento falha.
        plan: error instanceof ImportPlanError ? error.plan : null,
        error:
          error instanceof ImportPlanError
            ? error.message
            : 'Não foi possível fechar os valores do documento. Revise os campos.',
      };
    }
  });
  readonly expenseCategories = ['Aluguel', 'Energia e água', 'Internet e telefonia', 'Contabilidade', 'Marketing', 'Frete e transporte', 'Material de escritório', 'Materiais de consumo e embalagem', 'Impostos e taxas', 'Serviços', 'Outros'];
  private readonly initialRange = quickDateRange('last30');
  readonly startDate = signal(this.initialRange.startDate);
  readonly endDate = signal(this.initialRange.endDate);
  readonly statuses: { value: string; label: string }[] = [
    { value: 'negotiating', label: 'Em negociação' }, { value: 'approved', label: 'Aprovada' },
    { value: 'ordered', label: 'Pedido enviado' }, { value: 'partially_received', label: 'Recebimento parcial' },
    { value: 'received', label: 'Recebida' }, { value: 'closed', label: 'Encerrada' },
    { value: 'cancelled', label: 'Cancelada' },
  ];
  readonly workflow = [{ value: 'negotiating', label: 'Negociação' }, { value: 'approved', label: 'Aprovação' }, { value: 'ordered', label: 'Pedido' }, { value: 'received', label: 'Recebimento' }];
  readonly form = this.fb.group({
    purchase_type: ['parts'], supplier_name: [''], supplier_order_number: [''], document_date: [''], expense_category: [''], expense_amount: [0, [Validators.min(0)]], needed_by: [''], notes: [''], payment_type: ['cash' as PaymentConditionType], installment_count: [1, [Validators.min(1), Validators.max(36)]], first_due_days: [0, [Validators.min(0)]], interval_days: [30, [Validators.min(1)]], items: this.fb.array([this.newLine()]),
  });
  readonly quoteForm = this.fb.nonNullable.group({ supplier_name: ['', Validators.required], supplier_contact: [''], freight_amount: [0, [Validators.required, Validators.min(0)]], tax_amount: [0, [Validators.required, Validators.min(0)]], discount_amount: [0, [Validators.required, Validators.min(0)]], allocation_method: ['proportional' as 'proportional' | 'quantity'], delivery_days: [null as number | null], payment_type: ['cash' as PaymentConditionType], installment_count: [1, [Validators.min(1), Validators.max(36)]], first_due_days: [30, [Validators.min(0)]], interval_days: [30, [Validators.min(1)]], payment_terms: [''], notes: [''] });
  readonly lines = this.form.controls.items as FormArray;
  readonly periodPurchases = computed(() => {
    const startDate = this.startDate();
    const endDate = this.endDate();
    return this.purchases().filter((purchase) => {
      const date = this.purchaseLocalDate(purchase);
      return (!startDate || date >= startDate) && (!endDate || date <= endDate);
    });
  });
  readonly filtered = computed(() => {
    const term = this.search().trim().toLocaleLowerCase('pt-BR');
    return this.periodPurchases().filter((purchase) => {
      const matchStatus = this.statusFilter() === 'all' || purchase.status === this.statusFilter();
      const haystack = [purchase.number, ...purchase.items.flatMap((item) => [item.sku, item.description]), ...purchase.quotes.map((quote) => quote.supplier_name)].join(' ').toLocaleLowerCase('pt-BR');
      return matchStatus && (!term || haystack.includes(term));
    });
  });
  readonly summary = computed(() => [
    { status: 'negotiating', label: 'Em negociação', count: this.periodPurchases().filter((p) => p.status === 'negotiating').length, note: 'Aguardando propostas' },
    { status: 'ordered', label: 'Aguardando recebimento', count: this.periodPurchases().filter((p) => ['ordered', 'partially_received'].includes(p.status)).length, note: 'Peças e materiais pendentes' },
    { status: 'received', label: 'Concluídas', count: this.periodPurchases().filter((p) => p.status === 'received').length, note: 'Compras recebidas ou despesas lançadas' },
  ]);

  private purchaseLocalDate(purchase: PurchaseListItem) {
    const date = new Date(purchase.created_at);
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
  }

  ngOnInit() { this.load(); this.refreshProducts(); this.loadSuppliers(); this.api.purchaseImportProfiles().subscribe({ next: (result) => this.importProfiles.set(result.profiles), error: () => undefined }); this.live.changes$.pipe(debounceTime(250), takeUntilDestroyed(this.destroyRef)).subscribe(() => { this.load(); this.refreshProducts(); this.loadSuppliers(); }); this.quoteForm.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => { const purchase = this.detail(); const typed = this.quoteTotalValue(); if (purchase && typed !== null) this.distributeQuoteTotal(purchase, typed); }); }
  private refreshProducts() { this.api.products('', false).subscribe({ next: (items) => this.products.set(items), error: () => undefined }); }
  private loadSuppliers() { this.api.suppliers().subscribe({ next: (items) => this.suppliers.set(items), error: () => undefined }); }
  onImportDocument(event: Event) {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0]; input.value = '';
    if (!file) return;
    this.importFile.set(file); this.importError.set(''); this.importLoading.set(true);
    this.api.analyzePurchaseDocument(file).pipe(finalize(() => this.importLoading.set(false))).subscribe({
      next: (review) => this.applyImportReview(review),
      error: (err) => { const message = err?.error?.detail || 'Não foi possível analisar o documento. A compra manual continua disponível.'; this.importError.set(message); this.error.set(message); },
    });
  }
  private applyImportReview(review: any) {
    this.importMoneyValidity.set({});
    this.importId.set(crypto.randomUUID());
    this.importProductSearch.set({}); this.importProductResults.set({}); this.importSearchRevision.set({});
    this.importReview.set(review);
    this.importDraft.set({
      supplier: String(review.fields?.supplier?.value || ''),
      orderNumber: String(review.fields?.order_number?.value || ''),
      documentDate: String(review.fields?.date?.value || ''),
      total: review.fields?.total?.value == null ? null : Number(review.fields.total.value),
      shipping: review.fields?.shipping?.value == null ? null : Number(review.fields.shipping.value),
      discount: review.fields?.discount?.value == null ? null : Number(review.fields.discount.value),
      tax: review.fields?.tax?.value == null ? null : Number(review.fields.tax.value),
      currency: review.currency ? String(review.currency) : null,
      exchangeRate: review.exchange_rate == null ? null : Number(review.exchange_rate),
      paidAmount: review.paid?.amount == null ? null : Number(review.paid.amount),
      items: (review.items || []).map((item: any) => {
        const sku = String(item.sku || '').trim();
        // Vínculo automático só com correspondência exata de SKU ou código de barras (P14).
        const match = sku
          ? this.products().find((product) => product.sku.toLowerCase() === sku.toLowerCase() || (!!product.barcode && product.barcode === sku))
          : undefined;
        return {
          description: String(item.description || ''), sku, product_id: match ? match.id : null, stock_controlled: true,
          quantity: Number(item.quantity ?? 0), unit_cost: Number(item.unit_cost ?? 0), line_total: Number(item.line_total ?? Number(item.quantity ?? 0) * Number(item.unit_cost ?? 0)), discount_amount: Number(item.discount_amount ?? 0),
          confidence: Number(item.confidence ?? 0), source: String(item.source || ''), quantityDerived: !!item.quantity_derived,
        };
      }),
    });
    this.importError.set('');
    this.importCheck.set(review.check || null);
    this.checkImportDuplicate();
  }
  private checkImportDuplicate() {
    const review = this.importReview();
    const number = String(review?.fields?.order_number?.value || '').trim();
    const origin = String(review?.profile?.profile_id || '').trim();
    this.importDuplicate.set(null);
    if (!number || !origin) return;
    this.api.purchaseImportDuplicates({ order_number: number, origin }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (result) => this.importDuplicate.set(result.match),
      error: () => this.importDuplicate.set(null),
    });
  }
  changeImportProfile(profileId: string) {
    const file = this.importFile(); if (!file) return;
    this.importLoading.set(true);
    this.api.analyzePurchaseDocument(file, profileId || undefined).pipe(finalize(() => this.importLoading.set(false))).subscribe({
      next: (review) => this.applyImportReview(review),
      error: (err) => this.importError.set(err?.error?.detail || 'Não foi possível processar com este perfil.'),
    });
  }
  updateImportField(field: 'supplier' | 'orderNumber' | 'documentDate', value: string) { this.importDraft.update((draft) => ({ ...draft, [field]: value })); }
  setImportRate(value: number | null) { this.importDraft.update((draft) => ({ ...draft, exchangeRate: value })); }
  setImportRateFromInput(value: string) { this.setImportRate(value === '' ? null : Number(value)); }
  fieldOrigin(field: { source?: string; confidence?: number } | undefined): string {
    if (!field) return 'não identificado';
    const source = String(field.source || '');
    if (source === 'xml') return 'XML da NF-e';
    if (source === 'ocr') return `OCR · qualidade ${Math.round((Number(field.confidence) || 0) * 100)}%`;
    if (source === 'pdf_text') return 'texto do documento';
    if (source === 'columns') return 'grade do documento';
    return 'documento';
  }
  itemOrigin(item: { source?: string; confidence?: number; quantity_derived?: boolean; quantityDerived?: boolean }): string {
    const base = this.fieldOrigin(item);
    const derived = item.quantity_derived ?? item.quantityDerived;
    return derived ? `${base} · quantidade derivada` : base;
  }
  setImportPaid(value: number | null) { this.importDraft.update((draft) => ({ ...draft, paidAmount: value })); }
  importItemsTotal() { return this.importDraft().items.reduce((sum, item) => sum + Number(item.line_total || 0), 0); }
  importClosingDifference() {
    const draft = this.importDraft();
    if (draft.total === null || !draft.items.length) return 0;
    return Number((this.importItemsTotal() + Number(draft.shipping || 0) + Number(draft.tax || 0) - Number(draft.discount || 0) - Number(draft.total)).toFixed(2));
  }
  importHasItemsToCheck() { return !!this.importCheck()?.items_total || this.importDraft().items.length > 0; }
  importSubtotalDifference() {
    const draft = this.importDraft();
    const subtotal = this.importCheck()?.subtotal ?? null;
    if (subtotal === null || !draft.items.length) return null;
    return Number((this.importItemsTotal() - Number(subtotal)).toFixed(2));
  }
  /** Motivos visíveis que impedem a confirmação — ninguém fica preso sem saber por quê. */
  importBlockers(): string[] {
    const blockers: string[] = [];
    const draft = this.importDraft();
    const duplicate = this.importDuplicate();
    if (duplicate && !duplicate.cancelled) {
      blockers.push(`Este documento já foi importado na compra ${duplicate.purchase_number}.`);
    }
    if (this.importNeedsRate() && !(Number(draft.exchangeRate) > 0)) {
      blockers.push('Informe a cotação usada na conversão para reais.');
    }
    if (Object.values(this.importMoneyValidity()).some(Boolean)) {
      blockers.push('Há um campo de valor com formato inválido — corrija o valor destacado.');
    }
    if (this.importType() === 'expense') {
      if (this.importCategory().trim().length < 2) blockers.push('Escolha a categoria da despesa.');
      if (!(Number(draft.total) > 0)) blockers.push('Informe o valor total da despesa.');
      return blockers;
    }
    if (!draft.items.length) {
      blockers.push('Inclua pelo menos um item — ou marque uma linha candidata do documento.');
    }
    draft.items.forEach((item, index) => {
      const label = `linha ${index + 1}`;
      if (item.description.trim().length < 2) blockers.push(`Descreva a ${label}.`);
      if (!(Number(item.quantity) > 0)) blockers.push(`Informe a quantidade da ${label}.`);
      if (item.stock_controlled && !item.product_id) {
        blockers.push(`Vincule um produto do catálogo na ${label} (ou desmarque "Controlado no estoque").`);
      }
      // P0, regra 6: a compra nasce com o pedido registrado, então cada linha precisa de SKU
      // ou produto vinculado — a mesma exigência do envio manual do pedido.
      if (!item.sku.trim() && !item.product_id) {
        blockers.push(`Informe o SKU ou vincule um produto na ${label}: a compra já nasce como pedido registrado.`);
      }
      if (Number(item.discount_amount) > Number(item.quantity) * Number(item.unit_cost)) {
        blockers.push(`O desconto da ${label} é maior que o valor da linha.`);
      }
    });
    return [...new Set(blockers)];
  }
  importPaidDifference() {
    const draft = this.importDraft();
    if (draft.paidAmount === null || draft.total === null) return 0;
    return Number((Number(draft.paidAmount) - Number(draft.total)).toFixed(2));
  }
  importNeedsRate() {
    const currency = this.importDraft().currency;
    return !!currency && currency.toUpperCase() !== 'BRL';
  }
  updateImportNumber(field: 'total' | 'shipping' | 'discount' | 'tax', value: number | null) { this.importDraft.update((draft) => ({ ...draft, [field]: value })); }
  updateImportItem(index: number, field: 'description' | 'sku' | 'quantity' | 'unit_cost' | 'discount_amount', value: string | number | null) {
    this.importDraft.update((draft) => ({ ...draft, items: draft.items.map((item, i) => { if (i !== index) return item; const updated = { ...item, [field]: field === 'description' || field === 'sku' ? value : Number(value ?? 0) }; if (field === 'quantity' || field === 'unit_cost' || field === 'discount_amount') updated.line_total = Math.max(0, Number(updated.quantity) * Number(updated.unit_cost) - Number(updated.discount_amount)); return updated; }) }));
  }
  setImportMoneyValidity(key: string, invalid: boolean) { this.importMoneyValidity.update((values) => ({ ...values, [key]: invalid })); }
  searchImportProducts(index: number, value: string) { this.importProductSearch.update((rows) => ({ ...rows, [index]: value })); const revision = (this.importSearchRevision()[index] || 0) + 1; this.importSearchRevision.update((rows) => ({ ...rows, [index]: revision })); if (!value.trim()) { this.importProductResults.update((rows) => ({ ...rows, [index]: [] })); return; } this.api.products(value.trim(), false).subscribe({ next: (products) => { if (this.importSearchRevision()[index] === revision) this.importProductResults.update((rows) => ({ ...rows, [index]: products.filter((product) => product.stock_type === 'product' || product.stock_type === 'warehouse') })); }, error: () => { if (this.importSearchRevision()[index] === revision) this.importProductResults.update((rows) => ({ ...rows, [index]: [] })); } }); }
  selectedImportProduct(id: string | null) { return id ? this.products().find((product) => product.id === id) || Object.values(this.importProductResults()).flat().find((product) => product.id === id) || null : null; }
  selectImportedProduct(index: number, product: Product) { this.importDraft.update((draft) => ({ ...draft, items: draft.items.map((item, i) => i === index ? { ...item, product_id: product.id, stock_controlled: true, sku: item.sku || product.sku } : item) })); this.products.update((items) => items.some((entry) => entry.id === product.id) ? items : [...items, product]); this.importProductSearch.update((rows) => ({ ...rows, [index]: '' })); this.importProductResults.update((rows) => ({ ...rows, [index]: [] })); }
  selectImportedProductById(index: number, productId: string) {
    if (!productId) { this.clearImportedProduct(index); return; }
    const product = this.products().find((entry) => entry.id === productId)
      ?? Object.values(this.importProductResults()).flat().find((entry) => entry.id === productId);
    if (product) this.selectImportedProduct(index, product);
  }
  setImportStockControlled(index: number, value: boolean) { this.importDraft.update((draft) => ({ ...draft, items: draft.items.map((item, i) => i === index ? { ...item, stock_controlled: value, product_id: value ? item.product_id : null } : item) })); }
  clearImportedProduct(index: number) { this.importDraft.update((draft) => ({ ...draft, items: draft.items.map((item, i) => i === index ? { ...item, product_id: null } : item) })); }
  openImportProductCreate(index: number) { const item = this.importDraft().items[index]; this.importProductLine.set(index); this.importProductError.set(''); this.importProductDraft.set({ sku: item.sku, stock_type: 'product', name: item.description, description: item.description, sale_price: 0, cost_price: 0, minimum_stock: 0, brand: '', manufacturer: '', manufacturer_part_number: '', barcode: '', category: '', item_condition: 'new', warranty_days: null, origin_country: '', weight_g: null, package_length_cm: null, package_width_cm: null, package_height_cm: null }); this.importProductModal.set(true); }
  closeImportProductCreate() { if (!this.savingImportProduct()) this.importProductModal.set(false); }
  updateImportProduct(field: string, value: string | number | null) { this.importProductDraft.update((draft) => { const numeric = ['sale_price', 'cost_price', 'minimum_stock', 'warranty_days', 'weight_g', 'package_length_cm', 'package_width_cm', 'package_height_cm'].includes(field); return { ...draft, [field]: numeric ? value === '' || value == null ? null : Number(value) : value } as typeof draft; }); }
  canSaveImportProduct() { const value = this.importProductDraft(); return value.sku.trim().length > 0 && value.sku.trim().length <= 80 && value.name.trim().length >= 2 && value.name.trim().length <= 200; }
  saveImportProduct() { if (!this.canSaveImportProduct() || this.savingImportProduct()) return; const index = this.importProductLine(), draft = this.importProductDraft(); if (index == null) return; this.savingImportProduct.set(true); this.importProductError.set(''); this.api.createProduct({ ...draft, sku: draft.sku.trim(), name: draft.name.trim(), current_stock: 0, sale_price: draft.sale_price ?? 0, cost_price: draft.cost_price ?? 0, minimum_stock: draft.minimum_stock ?? 0, attributes: {}, fitments: [] }).pipe(finalize(() => this.savingImportProduct.set(false))).subscribe({ next: (product) => { this.selectImportedProduct(index, product); this.importProductModal.set(false); }, error: (err) => this.importProductError.set(err?.error?.detail || 'Não foi possível cadastrar o produto. Confira SKU e campos obrigatórios.') }); }
  private importNotes(review: any, draft: { orderNumber: string; documentDate: string; total: number | null; shipping: number | null; discount: number | null; tax: number | null }): string {
    const metadata = [
      `Perfil: ${review.profile.name}`,
      draft.orderNumber ? `Pedido: ${draft.orderNumber}` : '',
      draft.documentDate ? `Data no documento: ${draft.documentDate}` : '',
      draft.shipping != null ? `Frete no documento: ${draft.shipping}` : '',
      draft.discount != null ? `Desconto no documento: ${draft.discount}` : '',
      draft.tax != null ? `Impostos no documento: ${draft.tax}` : '',
      `Total no documento: ${draft.total ?? 'não identificado'}`,
      'Documento revisado pelo usuário.',
    ].filter(Boolean);
    return `Importação de documento. ${metadata.join(' · ')}`.slice(0, 4000);
  }
  importPlanLine(index: number) { return this.importPlan().plan?.lines[index] ?? null; }
  canConfirmImport() {
    // P0: além dos bloqueios da revisão (P14), o fechamento do documento precisa fechar — a
    // compra já nasce com a cotação do papel aceita e o pedido registrado.
    return this.importPlan().error === '' && this.importBlockers().length === 0;
  }
  setImportType(value: 'parts' | 'expense') {
    this.importType.set(value);
    if (value === 'expense' && !this.importCategory()) this.importCategory.set(this.expenseCategories[0]);
  }
  setImportPaidNow(value: boolean) {
    this.importPaidNow.set(value);
    if (value && !this.importPaidDate()) this.importPaidDate.set(this.today());
  }
  private today() {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  }
  useImportCandidate(candidate: { text: string; quantity?: number; unit_cost?: number }) {
    const quantity = Number(candidate.quantity ?? 1) || 1;
    const unitCost = Number(candidate.unit_cost ?? 0);
    this.importDraft.update((draft) => ({
      ...draft,
      items: [
        ...draft.items,
        {
          description: candidate.text,
          sku: '',
          quantity,
          unit_cost: unitCost,
          line_total: Number((quantity * unitCost).toFixed(2)),
          discount_amount: 0,
          confidence: 0,
          product_id: null,
          stock_controlled: true,
          source: 'candidato',
          quantityDerived: candidate.quantity === undefined,
        },
      ],
    }));
  }
  addImportLine() { this.importDraft.update((draft) => ({ ...draft, items: [...draft.items, { description: '', sku: '', quantity: 1, unit_cost: 0, confidence: 0, product_id: null, stock_controlled: true, line_total: 0, discount_amount: 0, source: '', quantityDerived: false }] })); }
  removeImportLine(index: number) { this.importDraft.update((draft) => ({ ...draft, items: draft.items.filter((_, i) => i !== index) })); this.importMoneyValidity.update((values) => Object.fromEntries(Object.entries(values).filter(([key]) => !key.startsWith('item-')))); }
  closeImportReview() { if (this.creatingImport()) return; this.importReview.set(null); this.importFile.set(null); this.importId.set(null); this.importError.set(''); this.importProductModal.set(false); }
  createImportedPurchase() {
    const review = this.importReview(), file = this.importFile(), draft = this.importDraft(), importId = this.importId();
    if (!review || !file || !importId || !this.canConfirmImport() || this.creatingImport()) return;
    this.creatingImport.set(true); this.importError.set('');
    const isExpense = this.importType() === 'expense';
    const payload = {
      purchase_type: this.importType(), source_import_id: importId, supplier_name: draft.supplier.trim() || null,
      expense_category: isExpense ? this.importCategory().trim() || null : null,
      expense_amount: isExpense ? draft.total : null,
      supplier_id: this.supplierByName(draft.supplier)?.id ?? null,
      supplier_order_number: draft.orderNumber.trim() || null,
      purchase_origin: review.profile?.profile_id || null,
      document_access_key: review.fields?.access_key?.value ?? null,
      document_number: review.fields?.document_number?.value ?? null,
      document_series: review.fields?.document_series?.value ?? null,
      issuer_cnpj: review.fields?.issuer_cnpj?.value ?? null,
      original_currency: draft.currency,
      original_total: draft.total,
      exchange_rate: draft.exchangeRate,
      paid_amount: draft.paidAmount,
      paid_now: this.importPaidNow(),
      paid_date: this.importPaidNow() ? this.importPaidDate() || null : null,
      paid_method: this.importPaidNow() ? this.importPaidMethod().trim() || null : null,
      document_date: draft.documentDate || null,
      notes: this.importNotes(review, draft),
      // P0: o documento é a cotação da compra — os valores do papel entram uma única vez e
      // são rateados por peça no mesmo algoritmo mostrado na revisão. Lançamento de despesa
      // segue o fluxo de despesa (P14) e não leva a cotação do documento.
      import_document: isExpense
        ? null
        : {
            filename: file.name,
            total: draft.total,
            freight_amount: draft.shipping ?? 0,
            tax_amount: draft.tax ?? 0,
            discount_amount: draft.discount ?? 0,
          },
      items: (isExpense ? draft.items.filter((item) => item.stock_controlled && item.product_id) : draft.items).map((item) => ({
        sku: item.sku.trim(), description: item.description.trim(), quantity: item.quantity,
        unit_cost: item.unit_cost, product_id: item.product_id,
        line_discount_amount: item.discount_amount,
      })),
    };
    this.api.confirmImportedPurchase(file, payload).pipe(finalize(() => this.creatingImport.set(false))).subscribe({
      next: (purchase) => {
        this.importReview.set(null); this.importFile.set(null);
        this.purchases.update((list) => [purchase, ...list]);
        const alreadyAttached = purchase.attachments.some((attachment) => attachment.filename === file.name && attachment.size_bytes === file.size);
        if (!alreadyAttached) this.error.set('O documento não voltou anexado; confira o anexo na compra.');
        this.openDetails(purchase);
      },
      error: (err) => this.importError.set(this.importErrorText(err)),
    });
  }
  private importErrorText(err: any): string {
    const detail = err?.error?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) return detail.map((entry) => entry?.msg || '').filter(Boolean).join(' · ') || 'Confira os campos da revisão.';
    if (detail?.message) return String(detail.message);
    return 'Não foi possível criar a compra revisada.';
  }

  private newLine() { return this.fb.group({ product_id: [''], sku: [''], description: ['', Validators.required], unit: ['un', Validators.required], quantity: [1, [Validators.required, Validators.min(0.001)]], unit_cost: [0, [Validators.required, Validators.min(0)]] }); }
  load() { this.api.purchases().subscribe({ next: (items) => this.purchases.set(items), error: () => this.error.set('Não foi possível carregar as compras. Tente novamente.') }); }
  applyPeriod(range: DateRange) { this.startDate.set(range.startDate); this.endDate.set(range.endDate); }
  toggleStatus(status: string) { this.statusFilter.set(this.statusFilter() === status ? 'all' : status); }
  openNew() { this.closeRowMenu(); this.error.set(''); this.selectedFiles.set([]); this.form.reset({ purchase_type: 'parts', supplier_name: '', expense_category: '', expense_amount: 0, needed_by: '', notes: '', payment_type: 'cash', installment_count: 1, first_due_days: 0, interval_days: 30 }); while (this.lines.length) this.lines.removeAt(0); this.addLine(); this.showNew.set(true); }
  toggleRowMenu(id: string, event: Event) {
    event.stopPropagation();
    if (this.rowMenuId() === id) { this.closeRowMenu(); return; }
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
  rowMenuPurchase() { return this.purchases().find((purchase) => purchase.id === this.rowMenuId()) ?? null; }
  closeRowMenu() { this.rowMenuId.set(null); this.rowMenuPosition.set(null); }
  copyPurchaseFromList(purchase: PurchaseListItem, event: Event) { event.stopPropagation(); this.copyPurchase(purchase); }
  copyPurchase(purchase: PurchaseListItem) {
    this.closeRowMenu();
    this.error.set('');
    this.selectedFiles.set([]);
    this.form.reset({
      purchase_type: purchase.purchase_type,
      supplier_name: purchase.supplier_name ?? '',
      expense_category: purchase.expense_category ?? '',
      expense_amount: purchase.expense_amount ?? 0,
      needed_by: '',
      notes: purchase.notes ? `Cópia de ${purchase.number}\n${purchase.notes}` : `Cópia de ${purchase.number}`,
    });
    while (this.lines.length) this.lines.removeAt(0);
    if (purchase.purchase_type === 'parts') {
      for (const item of purchase.items) {
        const line = this.newLine();
        line.patchValue({ product_id: item.product_id ?? '', sku: item.sku, description: item.description, quantity: item.quantity });
        this.lines.push(line);
      }
    } else {
      this.addLine();
    }
    this.detail.set(null);
    this.showNew.set(true);
  }
  addLine() { this.lines.push(this.newLine()); }
  removeLine(index: number) { this.lines.removeAt(index); }
  selectProduct(index: number, id: string) { const line = this.lines.at(index); const product = this.products().find((entry) => entry.id === id); if (product) line.patchValue({ product_id: id, sku: product.sku, description: product.name }); else line.patchValue({ product_id: '', sku: '', description: '' }); }
  create() {
    const isExpense = this.form.controls.purchase_type.value === 'expense';
    if (this.saving() || (!isExpense && this.form.invalid) || (isExpense && (!this.form.controls.expense_category.value || Number(this.form.controls.expense_amount.value) < 0 || this.lines.controls.some((line) => line.value.description && line.invalid)))) return;
    this.saving.set(true); this.error.set('');
    const value = this.form.getRawValue();
    this.api.createPurchase({ purchase_type: value.purchase_type, payment_type: value.payment_type, installment_count: value.installment_count, first_due_days: value.first_due_days, interval_days: value.interval_days, supplier_name: value.supplier_name || null, supplier_id: this.supplierByName(value.supplier_name)?.id ?? null, supplier_order_number: value.supplier_order_number || null, document_date: value.document_date || null, expense_category: value.expense_category || null, expense_amount: value.expense_amount || null, needed_by: value.needed_by || null, notes: value.notes || null, items: value.items.filter((item) => String(item.description || '').trim()).map((item) => ({ ...item, product_id: item.product_id || null })) }).pipe(finalize(() => this.saving.set(false))).subscribe({ next: (purchase) => { this.showNew.set(false); this.purchases.update((list) => [purchase, ...list]); const files = this.selectedFiles(); if (files.length) { this.api.uploadPurchaseAttachments(purchase.id, files).subscribe({ next: (updated) => this.setPurchase(updated) }); } this.openDetails(purchase); }, error: (err) => this.error.set(err.error?.detail || 'Não foi possível salvar a compra.') });
  }
  setAttachments(files: FileList | null) { this.selectedFiles.set(files ? Array.from(files).slice(0, 10) : []); }
  uploadAttachments(purchase: Purchase, files: FileList | null) { const selected = files ? Array.from(files).slice(0, 10) : []; if (!selected.length) return; this.saving.set(true); this.api.uploadPurchaseAttachments(purchase.id, selected).pipe(finalize(() => this.saving.set(false))).subscribe({ next: (updated) => this.setPurchase(updated), error: (err) => this.error.set(err.error?.detail || 'Não foi possível anexar os documentos.') }); }
  downloadAttachment(purchase: Purchase, attachment: Purchase['attachments'][number]) { this.api.downloadPurchaseAttachment(purchase.id, attachment.id, attachment.filename); }
  formatBytes(bytes: number) { return bytes < 1024 * 1024 ? `${Math.ceil(bytes / 1024)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`; }
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
  availableProducts(stockType: 'product' | 'warehouse') { return this.products().filter((product) => product.stock_type === stockType); }
  selectedQuote(purchase: PurchaseListItem) { return purchase.quotes.find((quote) => quote.id === purchase.selected_quote_id) ?? null; }
  statusLabel(status: PurchaseStatus) { return this.statuses.find((entry) => entry.value === status)?.label ?? status; }
  purchaseStatusLabel(purchase: PurchaseListItem) { return this.statusLabel(purchase.status); }
  purchaseStatusNote(purchase: Purchase) {
    if (purchase.status === 'cancelled') return purchase.cancel_reason ? `Cancelada · ${purchase.cancel_reason}` : 'Compra cancelada.';
    if (purchase.status === 'closed') return 'Saldo pendente encerrado; o material recebido foi mantido no estoque.';
    return '';
  }
  payableLabel(payable: PurchasePayable) {
    if (payable.status === 'paid') return `Pago${payable.payment_method ? ' · ' + payable.payment_method : ''}`;
    if (payable.status === 'cancelled') return 'Encerrado com o cancelamento';
    if (payable.status === 'partial') return `Baixa parcial · vence ${this.dateLabel(payable.due_date)}`;
    return `Vence ${this.dateLabel(payable.due_date)}`;
  }
  dateLabel(value: string) { return dateOnlyLabel(value); }
  dateOnly(value: string | null | undefined) { return dateOnlyLabel(value); }
  isActive(purchase: Purchase) { return purchase.status !== 'cancelled' && purchase.status !== 'closed'; }
  hasReceived(purchase: Purchase) { return purchase.items.some((item) => item.received_quantity - (item.returned_quantity ?? 0) > 0); }
  stepIndex(status: PurchaseStatus) { if (status === 'cancelled') return -1; if (status === 'received' || status === 'closed') return 4; if (status === 'partially_received') return 3; return ['negotiating', 'approved', 'ordered'].indexOf(status); }
  // A API serializa Decimal como string: some sempre com Number para não concatenar.
  progress(item: PurchaseItem) { const quantity = Number(item.quantity ?? 0); return quantity ? Math.min(100, Number(item.received_quantity ?? 0) / quantity * 100) : 0; }
  totalUnits(purchase: Purchase) { return purchase.items.reduce((sum, item) => sum + Number(item.quantity ?? 0), 0); }
  receivedUnits(purchase: Purchase) { return purchase.items.reduce((sum, item) => sum + Number(item.received_quantity ?? 0), 0); }
  receiveQty(item: PurchaseItem) { return this.receiveValues()[item.id]?.quantity ?? 0; }
  receiveObservation(item: PurchaseItem) { return this.receiveObservations()[item.id] ?? ''; }
  setReceiveObservation(item: PurchaseItem, value: string) { this.receiveObservations.update((values) => ({ ...values, [item.id]: value })); this.clearReceiptId(item); }
  setReceiveQty(item: PurchaseItem, value: string) { this.receiveValues.update((values) => ({ ...values, [item.id]: { ...values[item.id], quantity: Number(value) } })); this.clearReceiptId(item); }
  receiveProduct(item: PurchaseItem) { return this.receiveValues()[item.id]?.productId ?? ''; }
  setReceiveProduct(item: PurchaseItem, value: string) { this.receiveValues.update((values) => ({ ...values, [item.id]: { ...values[item.id], productId: value, create: false } })); this.clearReceiptId(item); }
  createNewProduct(item: PurchaseItem) { return this.receiveValues()[item.id]?.create ?? false; }
  setCreateNewProduct(item: PurchaseItem, value: boolean) { this.receiveValues.update((values) => ({ ...values, [item.id]: { ...values[item.id], create: value, productId: value ? '' : values[item.id]?.productId ?? '' } })); this.clearReceiptId(item); }
  quoteUnitCost(item: PurchaseItem) { return this.quoteCosts()[item.id] ?? 0; }
  quoteSubtotal(purchase: Purchase) { return purchase.items.reduce((sum, item) => sum + this.quoteUnitCost(item) * Number(item.quantity), 0); }
  /** O último campo editado manda: o total digitado prevalece; sem ele, o unitário alimenta o total. */
  quoteTotal(purchase: Purchase) { const typed = this.quoteTotalValue(); return typed === null ? this.quoteComputedTotal(purchase) : typed; }
  quoteComputedTotal(purchase: Purchase) { const value = this.quoteForm.getRawValue(); return this.round2(this.quoteSubtotal(purchase) + Number(value.freight_amount || 0) + Number(value.tax_amount || 0) - Number(value.discount_amount || 0)); }
  /** Líquido das peças: total − frete − impostos + desconto. Negativo é proposta impossível. */
  quoteNet(purchase: Purchase) { const value = this.quoteForm.getRawValue(); return this.round2(this.quoteTotal(purchase) - Number(value.freight_amount || 0) - Number(value.tax_amount || 0) + Number(value.discount_amount || 0)); }
  setQuoteConditionType(value: string) { this.quoteForm.controls.payment_type.setValue(value as PaymentConditionType); }
  setQuoteConditionNumber(field: 'installment_count' | 'first_due_days' | 'interval_days', value: string) { this.quoteForm.controls[field].setValue(Number(value) || 0); }
  applyQuoteConditionPreset(preset: 'cash' | '30' | '30/60' | '30/60/90') {
    if (preset === 'cash') { this.quoteForm.patchValue({ payment_type: 'cash', installment_count: 1, first_due_days: 0, interval_days: 30 }); return; }
    const days = preset.split('/').map((value) => Number(value));
    this.quoteForm.patchValue({ payment_type: days.length > 1 ? 'installments' : 'cash', installment_count: days.length, first_due_days: days[0], interval_days: days.length > 1 ? days[1] - days[0] : 30 });
  }
  /** Condição legível que será gravada no título a pagar. */
  quoteConditionPreview() {
    const value = this.quoteForm.getRawValue();
    if (value.payment_type === 'cash') { return value.first_due_days > 0 ? `à vista em ${value.first_due_days} dias` : 'à vista'; }
    const offsets = value.payment_type === 'entry'
      ? [value.first_due_days, ...Array.from({ length: value.installment_count }, (_, index) => value.first_due_days + (index + 1) * value.interval_days)]
      : Array.from({ length: value.installment_count }, (_, index) => value.first_due_days + index * value.interval_days);
    return (value.payment_type === 'entry' ? 'entrada + ' : '') + offsets.join('/');
  }

  /** Condição legível da proposta, igual à que será gravada no título a pagar (P12). */
  quoteConditionLabel(quote: PurchaseQuote) {
    if (!quote.payment_type || quote.payment_type === 'cash') { return quote.first_due_days ? `À vista em ${quote.first_due_days} dias` : 'À vista'; }
    const count = quote.installment_count ?? 1;
    const first = quote.first_due_days ?? 0;
    const interval = quote.interval_days ?? 30;
    const offsets = quote.payment_type === 'entry'
      ? [first, ...Array.from({ length: count }, (_, index) => first + (index + 1) * interval)]
      : Array.from({ length: count }, (_, index) => first + index * interval);
    return (quote.payment_type === 'entry' ? 'Entrada + ' : '') + offsets.join('/');
  }

  quoteDirectionNote() { return this.quoteTotalValue() === null ? 'o custo unitário de cada peça alimenta o total.' : 'o total digitado foi distribuído entre as peças pelo rateio escolhido.'; }
  quoteMismatch(purchase: Purchase) { return Math.abs(this.quoteComputedTotal(purchase) - this.quoteTotal(purchase)) > 0.01 * Math.max(1, purchase.items.length); }
  private round2(value: number) { return Math.round(value * 100) / 100; }
  setQuoteTotal(value: number | null) { const purchase = this.detail(); if (value === null) { this.quoteTotalValue.set(null); this.quoteRounding.set(0); return; } this.quoteTotalValue.set(value); if (purchase) this.distributeQuoteTotal(purchase, value); }
  /** Distribui o líquido da proposta pelos itens e fecha a sobra de centavos no maior item. */
  private distributeQuoteTotal(purchase: Purchase, total: number) {
    if (!purchase.items.length) return;
    const value = this.quoteForm.getRawValue();
    const netCents = Math.round((total - Number(value.freight_amount || 0) - Number(value.tax_amount || 0) + Number(value.discount_amount || 0)) * 100);
    const byQuantity = value.allocation_method === 'quantity';
    // A API serializa Decimal como texto: a quantidade chega como string e precisa ser número.
    let weights = purchase.items.map((item) => (byQuantity ? Number(item.quantity) : this.quoteUnitCost(item) * Number(item.quantity)));
    if (!byQuantity && weights.every((weight) => weight <= 0)) weights = purchase.items.map((item) => Number(item.quantity));
    const weightSum = weights.reduce((sum, weight) => sum + weight, 0);
    const shares = weights.map((weight) => (weightSum > 0 ? Math.round((netCents * weight) / weightSum) : 0));
    if (weightSum <= 0) shares[0] = netCents;
    const largest = weights.reduce((best, weight, index) => (weight > weights[best] ? index : best), 0);
    const residual = netCents - shares.reduce((sum, share) => sum + share, 0);
    shares[largest] += residual;
    const costs: Record<string, number> = {};
    purchase.items.forEach((item, index) => { costs[item.id] = this.round2(shares[index] / 100 / Number(item.quantity)); });
    this.quoteCosts.set(costs);
    // A sobra que aparece para o usuário é a diferença real entre o líquido digitado e a
    // soma dos unitários com duas casas, que nem sempre fecha em quantidades quebradas.
    const roundedSubtotal = purchase.items.reduce((sum, item) => sum + costs[item.id] * Number(item.quantity), 0);
    this.quoteRounding.set(this.round2(netCents / 100 - roundedSubtotal));
  }
  setQuoteUnitCost(item: PurchaseItem, value: number | null) { if (value === null) return; this.quoteTotalValue.set(null); this.quoteRounding.set(0); this.quoteCosts.update((costs) => ({ ...costs, [item.id]: value })); }
  setQuoteCostValidity(itemId: string, invalid: boolean) { this.quoteCostValidity.update((values) => ({ ...values, [itemId]: invalid })); }
  quoteCostHasErrors() { return Object.values(this.quoteCostValidity()).some(Boolean); }
  quoteCostsComplete(purchase: Purchase) { return purchase.items.every((item) => Number.isFinite(this.quoteUnitCost(item)) && this.quoteUnitCost(item) >= 0); }
  addQuote() { const purchase = this.detail(); if (!purchase || this.quoteForm.invalid || this.quoteCostHasErrors() || !this.quoteCostsComplete(purchase) || this.quoteTotal(purchase) < 0 || this.saving()) return; this.saving.set(true); this.error.set(''); const value = this.quoteForm.getRawValue(); this.api.addPurchaseQuote(purchase.id, { ...value, total: this.quoteTotal(purchase), item_costs: this.quoteCosts() }).pipe(finalize(() => this.saving.set(false))).subscribe({ next: (updated) => { this.setPurchase(updated); this.quoteForm.reset({ supplier_name: '', supplier_contact: '', freight_amount: 0, tax_amount: 0, discount_amount: 0, allocation_method: 'proportional', delivery_days: null, payment_type: 'cash', installment_count: 1, first_due_days: 30, interval_days: 30, payment_terms: '', notes: '' }); this.quoteCosts.set(Object.fromEntries(purchase.items.map((item) => [item.id, 0]))); this.quoteTotalValue.set(null); this.quoteRounding.set(0); }, error: (err) => this.error.set(err.error?.detail || 'Não foi possível registrar a cotação.') }); }
  selectQuote(id: string) { const purchase = this.detail(); if (!purchase || this.saving()) return; if (!confirm('Aprovar esta cotação? A compra seguirá para envio do pedido ao fornecedor.')) return; this.runAction(this.api.selectPurchaseQuote(purchase.id, id)); }
  placeOrder() { const purchase = this.detail(); if (purchase) this.runAction(this.api.placePurchaseOrder(purchase.id)); }
  receive(item: PurchaseItem) {
    const purchase = this.detail();
    if (!purchase || this.saving()) return;
    const choice = this.receiveValues()[item.id];
    if (!choice || choice.quantity <= 0) return;
    const receiptId = this.receiptIds()[item.id] ?? crypto.randomUUID();
    this.receiptIds.update((ids) => ({ ...ids, [item.id]: receiptId }));
    this.saving.set(true); this.error.set('');
    this.api.receivePurchase(purchase.id, { items: [{ item_id: item.id, receipt_id: receiptId, quantity: choice.quantity, product_id: choice.productId || null, create_product: choice.create, observation: this.receiveObservation(item) || null }] }).pipe(finalize(() => this.saving.set(false))).subscribe({
      next: (updated) => { this.setPurchase(updated); this.clearReceiptId(item); this.api.products('', false).subscribe((items) => this.products.set(items)); },
      error: (err) => this.error.set(err.error?.detail || 'Não foi possível registrar o recebimento.')
    });
  }
  private clearReceiptId(item: PurchaseItem) { this.receiptIds.update((ids) => { const updated = { ...ids }; delete updated[item.id]; return updated; }); }
  openLifecycleForm(mode: 'cancel' | 'close') {
    const purchase = this.detail();
    if (!purchase) return;
    this.error.set('');
    this.lifecycleForm.set({ mode, reason: '', resolution: this.hasReceived(purchase) ? 'keep_received' : 'return_received' });
  }
  setLifecycleReason(value: string) { this.lifecycleForm.update((form) => form ? { ...form, reason: value } : form); }
  setLifecycleResolution(value: 'keep_received' | 'return_received') { this.lifecycleForm.update((form) => form ? { ...form, resolution: value } : form); }
  submitLifecycle(purchase: Purchase) {
    const form = this.lifecycleForm();
    if (!form || this.saving() || form.reason.trim().length < 3) return;
    const request = form.mode === 'cancel'
      ? this.api.cancelPurchaseWithReason(purchase.id, { reason: form.reason.trim(), resolution: form.resolution })
      : this.api.closePurchaseBalance(purchase.id, { reason: form.reason.trim() });
    this.saving.set(true); this.error.set('');
    request.pipe(finalize(() => this.saving.set(false))).subscribe({
      next: (updated) => { this.lifecycleForm.set(null); this.setPurchase(updated); },
      error: (err) => this.error.set(err.error?.detail || 'Não foi possível concluir a ação.'),
    });
  }
  receiveAll(purchase: Purchase) {
    if (this.saving()) return;
    if (!confirm(`Receber todos os itens pendentes de ${purchase.number}? Itens sem produto vinculado serão cadastrados no catálogo.`)) return;
    this.saving.set(true); this.error.set('');
    this.api.receivePurchaseInFull(purchase.id, { create_products: true }).pipe(finalize(() => this.saving.set(false))).subscribe({
      next: (updated) => { this.setPurchase(updated); this.api.products('', false).subscribe((items) => this.products.set(items)); },
      error: (err) => this.error.set(err.error?.detail || 'Não foi possível registrar o recebimento.'),
    });
  }
  settlePayable(purchase: Purchase, payable: PurchasePayable) {
    if (this.saving()) return;
    const amount = payable.amount.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
    if (!confirm(`Registrar o pagamento de ${amount} do título de ${purchase.number}?`)) return;
    this.saving.set(true); this.error.set('');
    this.api.settlePurchasePayable(purchase.id, payable.id).pipe(finalize(() => this.saving.set(false))).subscribe({
      next: () => {
        this.api.purchases().subscribe((items) => this.purchases.set(items));
        this.api.purchase(purchase.id).subscribe((full) => this.detail.set(full));
      },
      error: (err) => this.error.set(err.error?.detail || 'Não foi possível registrar o pagamento.'),
    });
  }
  requestDelete(purchase: PurchaseListItem, event?: Event) {
    event?.stopPropagation();
    this.closeRowMenu();
    this.error.set('');
    this.deleteReason.set('');
    // O aviso de exclusão lista o que será apagado (inclui título a pagar), então busca a
    // compra completa antes de abrir a confirmação.
    this.api.purchase(purchase.id).subscribe({
      next: (full) => this.deleteTarget.set(full),
      error: () => this.error.set('Não foi possível abrir a compra. Tente novamente.'),
    });
  }
  cancelDelete() { this.deleteTarget.set(null); }
  deleteBlockedByPayment(purchase: Purchase) {
    return (purchase.payables ?? []).some((payable) => payable.status !== 'cancelled' && (payable.paid_amount ?? 0) > 0);
  }
  deletionEffects(purchase: Purchase) {
    const effects: string[] = [`${purchase.items.length} item(ns) do pedido`];
    if (purchase.quotes.length) effects.push(`${purchase.quotes.length} cotação(ões) registrada(s)`);
    if (purchase.attachments.length) effects.push(`${purchase.attachments.length} anexo(s), inclusive o arquivo armazenado`);
    const received = purchase.items.filter((item) => item.received_quantity - (item.returned_quantity ?? 0) > 0);
    if (received.length) {
      const quantity = received.reduce((sum, item) => sum + item.received_quantity - (item.returned_quantity ?? 0), 0);
      effects.push(`estorno de ${quantity} unidade(s) recebida(s) no estoque, com movimentação rastreável`);
    }
    const payable = (purchase.payables ?? []).find((entry) => entry.status !== 'cancelled');
    if (payable) effects.push(`título a pagar de ${Number(payable.amount).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}`);
    if (purchase.events.length) effects.push(`${purchase.events.length} evento(s) do histórico do pedido`);
    return effects;
  }
  confirmDelete(purchase: Purchase) {
    if (this.saving() || this.deleteBlockedByPayment(purchase)) return;
    this.saving.set(true); this.error.set('');
    const reason = this.deleteReason().trim();
    this.api.deletePurchase(purchase.id, reason || undefined).pipe(finalize(() => this.saving.set(false))).subscribe({
      next: () => {
        this.deleteTarget.set(null);
        if (this.detail()?.id === purchase.id) this.detail.set(null);
        this.purchases.update((items) => items.filter((item) => item.id !== purchase.id));
        this.message.set(`${purchase.number} foi excluída com os registros ligados.`);
      },
      error: (err) => this.error.set(err.error?.detail || 'Não foi possível excluir a compra.'),
    });
  }
  supplierByName(name: string | null | undefined) {
    const key = (name || '').trim().toLowerCase();
    return key ? this.suppliers().find((supplier) => supplier.name.toLowerCase() === key) ?? null : null;
  }
  applySupplierDefaults() {
    const supplier = this.supplierByName(this.form.controls.supplier_name.value);
    if (!supplier) return;
    if (supplier.default_delivery_days && !this.form.controls.needed_by.value) {
      const date = new Date();
      date.setDate(date.getDate() + supplier.default_delivery_days);
      this.form.controls.needed_by.setValue(date.toISOString().slice(0, 10));
    }
    if (supplier.default_payment_terms && !this.quoteForm.controls.payment_terms.value) {
      this.quoteForm.controls.payment_terms.setValue(supplier.default_payment_terms);
    }
  }
  registerSupplier(name: string) {
    const trimmed = (name || '').trim();
    if (trimmed.length < 2 || this.saving()) return;
    this.saving.set(true); this.error.set('');
    this.api.createSupplier({ name: trimmed }).pipe(finalize(() => this.saving.set(false))).subscribe({
      next: (supplier) => { this.suppliers.update((items) => items.some((entry) => entry.id === supplier.id) ? items : [...items, { ...supplier, contact: null }]); this.applySupplierDefaults(); },
      error: (err) => this.error.set(err.error?.detail || 'Não foi possível cadastrar o fornecedor.'),
    });
  }
  isOverdue(purchase: PurchaseListItem) {
    if (!purchase.needed_by || !['ordered', 'partially_received'].includes(purchase.status)) return false;
    const today = new Date();
    const todayKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
    return dateOnlyValue(purchase.needed_by) < todayKey;
  }
  purchaseTotal(purchase: PurchaseListItem) {
    if (purchase.purchase_type === 'expense') return purchase.expense_amount ?? 0;
    return purchase.total_amount ?? purchase.items.reduce((sum, item) => sum + item.quantity * (item.unit_cost ?? 0), 0);
  }
  totalPages() { return Math.max(1, Math.ceil(this.filtered().length / this.pageSize)); }
  pagedPurchases() { const page = Math.min(this.page(), this.totalPages()); const start = (page - 1) * this.pageSize; return this.filtered().slice(start, start + this.pageSize); }
  goToPage(delta: number) { this.page.set(Math.min(this.totalPages(), Math.max(1, this.page() + delta))); }
  isSelectable(purchase: PurchaseListItem) { return purchase.status === 'negotiating' && !purchase.selected_quote_id && purchase.items.every((item) => !item.received_quantity); }
  isSelected(id: string) { return !!this.selectedIds()[id]; }
  toggleSelection(id: string) { this.selectedIds.update((map) => ({ ...map, [id]: !map[id] })); }
  selectedPurchases() { return this.purchases().filter((purchase) => this.selectedIds()[purchase.id] && this.isSelectable(purchase)); }
  clearSelection() { this.selectedIds.set({}); }
  deleteSelectedDrafts() {
    const targets = this.selectedPurchases();
    if (!targets.length || this.saving()) return;
    if (!confirm(`Excluir ${targets.length} rascunho(s) selecionado(s)? Cada exclusão fica registrada no histórico de auditoria.`)) return;
    this.saving.set(true); this.error.set('');
    const failures: string[] = [];
    let pending = targets.length;
    for (const target of targets) {
      this.api.deletePurchase(target.id).pipe(finalize(() => { pending -= 1; if (!pending) { this.saving.set(false); this.clearSelection(); this.error.set(failures.join(' · ')); } })).subscribe({
        next: () => this.purchases.update((items) => items.filter((item) => item.id !== target.id)),
        error: (err) => failures.push(`${target.number}: ${err.error?.detail || 'falha ao excluir'}`),
      });
    }
  }
  openDraftEditor() { this.draftEditor.set(true); }
  closeDraftEditor() { this.draftEditor.set(false); }
  setDraftHeader(field: 'supplier_name' | 'supplier_order_number' | 'document_date' | 'needed_by' | 'notes', value: string) { this.draftHeader.update((header) => ({ ...header, [field]: value })); }
  saveDraftHeader(purchase: Purchase) {
    if (this.saving()) return;
    const header = this.draftHeader();
    this.saving.set(true); this.error.set('');
    this.api.updatePurchase(purchase.id, {
      supplier_name: header.supplier_name || null,
      supplier_id: this.supplierByName(header.supplier_name)?.id ?? null,
      supplier_order_number: header.supplier_order_number || null,
      document_date: header.document_date || null,
      needed_by: header.needed_by || null,
      notes: header.notes || null,
    }).pipe(finalize(() => this.saving.set(false))).subscribe({
      next: (updated) => this.applyUpdate(updated),
      error: (err) => this.error.set(err.error?.detail || 'Não foi possível salvar os dados do pedido.'),
    });
  }
  setLineDraft(itemId: string, field: 'description' | 'sku' | 'unit' | 'quantity', value: string) {
    this.lineDrafts.update((drafts) => ({ ...drafts, [itemId]: { ...(drafts[itemId] ?? { description: '', sku: '', unit: 'un', quantity: 0 }), [field]: field === 'quantity' ? Number(value) : value } }));
  }
  saveLine(purchase: Purchase, item: PurchaseItem) {
    const draft = this.lineDrafts()[item.id];
    if (!draft || this.saving()) return;
    this.saving.set(true); this.error.set('');
    this.api.updatePurchaseItem(purchase.id, item.id, { description: draft.description, sku: draft.sku, unit: draft.unit, quantity: draft.quantity }).pipe(finalize(() => this.saving.set(false))).subscribe({
      next: (updated) => this.applyUpdate(updated),
      error: (err) => this.error.set(err.error?.detail || 'Não foi possível salvar a peça.'),
    });
  }
  removePurchaseLine(purchase: Purchase, item: PurchaseItem) {
    if (this.saving()) return;
    if (!confirm(`Remover ${item.description} desta negociação?`)) return;
    this.saving.set(true); this.error.set('');
    this.api.removePurchaseItem(purchase.id, item.id).pipe(finalize(() => this.saving.set(false))).subscribe({
      next: (updated) => this.applyUpdate(updated),
      error: (err) => this.error.set(err.error?.detail || 'Não foi possível remover a peça.'),
    });
  }
  setNewLineDraft(field: 'description' | 'sku' | 'unit' | 'quantity', value: string) {
    this.newLineDraft.update((draft) => ({ ...draft, [field]: field === 'quantity' ? Number(value) : value }));
  }
  addDraftLine(purchase: Purchase) {
    const draft = this.newLineDraft();
    if (!draft.description.trim() || draft.quantity <= 0 || this.saving()) return;
    this.saving.set(true); this.error.set('');
    this.api.addPurchaseItem(purchase.id, { description: draft.description.trim(), sku: draft.sku.trim(), unit: draft.unit.trim() || 'un', quantity: draft.quantity, unit_cost: 0 }).pipe(finalize(() => this.saving.set(false))).subscribe({
      next: (updated) => { this.newLineDraft.set({ description: '', sku: '', unit: 'un', quantity: 1 }); this.applyUpdate(updated); },
      error: (err) => this.error.set(err.error?.detail || 'Não foi possível incluir a peça.'),
    });
  }
  private runAction(request: ReturnType<ApiService['placePurchaseOrder']>) { const purchase = this.detail(); if (!purchase) return; this.saving.set(true); this.error.set(''); request.pipe(finalize(() => this.saving.set(false))).subscribe({ next: (updated) => { this.setPurchase(updated); if (updated.status === 'received') this.api.products('', false, 'product').subscribe((items) => this.products.set(items)); }, error: (err) => this.error.set(err.error?.detail || 'Não foi possível atualizar esta compra.') }); }
  private primeDrafts(purchase: Purchase) {
    this.lineDrafts.set(Object.fromEntries(purchase.items.map((item) => [item.id, { description: item.description, sku: item.sku, unit: item.unit, quantity: item.quantity }])));
    this.draftHeader.set({ supplier_name: purchase.supplier_name || '', supplier_order_number: purchase.supplier_order_number || '', document_date: purchase.document_date ? purchase.document_date.slice(0, 10) : '', needed_by: purchase.needed_by ? purchase.needed_by.slice(0, 10) : '', notes: purchase.notes || '' });
  }
  private applyUpdate(purchase: Purchase) { this.primeDrafts(purchase); this.detail.set(purchase); this.purchases.update((items) => items.map((item) => item.id === purchase.id ? purchase : item)); }
  private setPurchase(purchase: Purchase) { this.applyUpdate(purchase); this.draftEditor.set(false); }
}
