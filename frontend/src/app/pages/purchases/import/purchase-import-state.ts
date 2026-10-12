import { DestroyRef, Injectable, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { finalize } from 'rxjs';

import { ApiService } from '../../../core/api.service';
import { Product } from '../../../core/models';
import { ImportPlanError, buildImportPlan } from '../../../shared/purchase-import-math';
import {
  ImportCheck,
  ImportDuplicate,
  EXPENSE_CATEGORIES,
  ImportDraft,
  closingDifference,
  emptyImportDraft,
  emptyImportLine,
  emptyImportProductDraft,
  fieldOriginText,
  hasItemsToCheck,
  importBlockers,
  importNotes,
  itemOriginText,
  itemsTotal,
  needsRate,
  paidDifference,
  subtotalDifference,
  today,
} from './purchase-import-model';

/** Fornecedor escolhido no cadastro rápido, sem custo de leitura. */
interface SupplierOption {
  id: string;
  name: string;
  contact: string | null;
  default_delivery_days: number | null;
  default_payment_terms: string | null;
}

/**
 * Estado e regras da revisão de importação de documento (P0/P14).
 *
 * Ficou fora da página de compras para a revisão ter leitura própria: aqui vive o rascunho
 * do documento, os campos lidos, as linhas, o rateio mostrado e os bloqueios de confirmação.
 */
@Injectable()
export class PurchaseImportState {
  private readonly api = inject(ApiService);
  private readonly destroyRef = inject(DestroyRef);
  readonly products = signal<Product[]>([]);
  readonly expenseCategories = EXPENSE_CATEGORIES;
  readonly importProductSearch = signal<Record<number, string>>({});
  readonly importProductResults = signal<Record<number, Product[]>>({});
  readonly importSearchRevision = signal<Record<number, number>>({});
  readonly importProductModal = signal(false);
  readonly importProductLine = signal<number | null>(null);
  readonly savingImportProduct = signal(false);
  readonly importProductError = signal('');
  readonly importProductDraft = signal(emptyImportProductDraft());
  readonly suppliers = signal<SupplierOption[]>([]);

  loadCatalog() {
    this.api.products().subscribe({
      next: (products) => this.products.set(products),
      error: () => this.products.set([]),
    });
    this.api.suppliers().subscribe({
      next: (suppliers) => this.suppliers.set(suppliers),
      error: () => this.suppliers.set([]),
    });
  }

  supplierByName(name: string | null | undefined) {
    const key = (name || '').trim().toLowerCase();
    return key
      ? (this.suppliers().find((supplier) => supplier.name.toLowerCase() === key) ?? null)
      : null;
  }

  readonly importMoneyValidity = signal<Record<string, boolean>>({});
  readonly importId = signal<string | null>(null);
  readonly importReview = signal<any | null>(null);
  readonly importProfiles = signal<
    Array<{ profile_id: string; name: string; kind: string; version: number }>
  >([]);
  readonly importDraft = signal(emptyImportDraft());
  readonly importDuplicate = signal<ImportDuplicate | null>(null);
  /**
   * P5: diferença entre o total do pedido e o valor pago, quando o documento não trouxe rótulo
   * de taxa. Fica aqui — nunca é aplicada sozinha: a pessoa confere e decide usar.
   */
  readonly suggestedExtras = signal<number | null>(null);
  readonly importCheck = signal<ImportCheck | null>(null);
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
  /** Lê o arquivo escolhido e abre a revisão (chamado pelo seletor de documento da página). */
  startAnalysis(event: Event) {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    this.loadCatalog();
    this.importFile.set(file);
    this.importError.set('');
    this.importLoading.set(true);
    this.api
      .analyzePurchaseDocument(file)
      .pipe(finalize(() => this.importLoading.set(false)))
      .subscribe({
        next: (review) => this.applyImportReview(review),
        error: (err) => {
          const message =
            err?.error?.detail ||
            'Não foi possível analisar o documento. A compra manual continua disponível.';
          this.importError.set(message);
        },
      });
  }
  private applyImportReview(review: any) {
    this.importMoneyValidity.set({});
    this.suggestedExtras.set(
      review.fields?.extras?.source === 'sugestao' ? Number(review.fields.extras.value ?? 0) : null,
    );
    this.importId.set(crypto.randomUUID());
    this.importProductSearch.set({});
    this.importProductResults.set({});
    this.importSearchRevision.set({});
    this.importReview.set(review);
    this.importDraft.set({
      supplier: String(review.fields?.supplier?.value || ''),
      orderNumber: String(review.fields?.order_number?.value || ''),
      documentDate: String(review.fields?.date?.value || ''),
      total: review.fields?.total?.value == null ? null : Number(review.fields.total.value),
      shipping:
        review.fields?.shipping?.value == null ? null : Number(review.fields.shipping.value),
      discount:
        review.fields?.discount?.value == null ? null : Number(review.fields.discount.value),
      tax: review.fields?.tax?.value == null ? null : Number(review.fields.tax.value),
      // P5: valor sugerido (diferença entre total e valor pago) NÃO entra sozinho no rascunho —
      // fica na sugestão para a pessoa aplicar depois de conferir.
      extras:
        review.fields?.extras?.source === 'sugestao' || review.fields?.extras?.value == null
          ? null
          : Number(review.fields.extras.value),
      currency: review.currency ? String(review.currency) : null,
      exchangeRate: review.exchange_rate == null ? null : Number(review.exchange_rate),
      paidAmount: review.paid?.amount == null ? null : Number(review.paid.amount),
      items: (review.items || []).map((item: any) => {
        const sku = String(item.sku || '').trim();
        // Vínculo automático só com correspondência exata de SKU ou código de barras (P14).
        const match = sku
          ? this.products().find(
              (product) =>
                product.sku.toLowerCase() === sku.toLowerCase() ||
                (!!product.barcode && product.barcode === sku),
            )
          : undefined;
        return {
          description: String(item.description || ''),
          sku,
          product_id: match ? match.id : null,
          stock_controlled: true,
          quantity: Number(item.quantity ?? 0),
          unit_cost: Number(item.unit_cost ?? 0),
          line_total: Number(
            item.line_total ?? Number(item.quantity ?? 0) * Number(item.unit_cost ?? 0),
          ),
          discount_amount: Number(item.discount_amount ?? 0),
          confidence: Number(item.confidence ?? 0),
          source: String(item.source || ''),
          quantityDerived: !!item.quantity_derived,
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
    this.api
      .purchaseImportDuplicates({ order_number: number, origin })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => this.importDuplicate.set(result.match),
        error: () => this.importDuplicate.set(null),
      });
  }
  changeImportProfile(profileId: string) {
    const file = this.importFile();
    if (!file) return;
    this.importLoading.set(true);
    this.api
      .analyzePurchaseDocument(file, profileId || undefined)
      .pipe(finalize(() => this.importLoading.set(false)))
      .subscribe({
        next: (review) => this.applyImportReview(review),
        error: (err) =>
          this.importError.set(err?.error?.detail || 'Não foi possível processar com este perfil.'),
      });
  }
  updateImportField(field: 'supplier' | 'orderNumber' | 'documentDate', value: string) {
    this.importDraft.update((draft) => ({ ...draft, [field]: value }));
  }
  setImportRate(value: number | null) {
    this.importDraft.update((draft) => ({ ...draft, exchangeRate: value }));
  }
  setImportRateFromInput(value: string) {
    this.setImportRate(value === '' ? null : Number(value));
  }
  fieldOrigin(field: { source?: string; confidence?: number } | undefined): string {
    return fieldOriginText(field);
  }
  itemOrigin(item: {
    source?: string;
    confidence?: number;
    quantity_derived?: boolean;
    quantityDerived?: boolean;
  }): string {
    return itemOriginText(item);
  }
  setImportPaid(value: number | null) {
    this.importDraft.update((draft) => ({ ...draft, paidAmount: value }));
  }
  /** P5: aplica a diferença sugerida (total do pedido × valor pago) como taxa extra. */
  applySuggestedExtras() {
    const suggested = this.suggestedExtras();
    if (suggested === null) return;
    this.importDraft.update((draft) => ({ ...draft, extras: suggested }));
    this.suggestedExtras.set(null);
  }
  importItemsTotal() {
    return itemsTotal(this.importDraft().items);
  }
  importClosingDifference() {
    return closingDifference(this.importDraft());
  }
  importHasItemsToCheck() {
    return hasItemsToCheck(this.importCheck(), this.importDraft());
  }
  importSubtotalDifference() {
    return subtotalDifference(this.importDraft(), this.importCheck()?.subtotal ?? null);
  }
  /** Motivos visíveis que impedem a confirmação — ninguém fica preso sem saber por quê. */
  importBlockers(): string[] {
    return importBlockers({
      draft: this.importDraft(),
      duplicate: this.importDuplicate(),
      needsRate: this.importNeedsRate(),
      moneyInvalid: Object.values(this.importMoneyValidity()).some(Boolean),
      kind: this.importType(),
      category: this.importCategory(),
    });
  }
  importPaidDifference() {
    return paidDifference(this.importDraft());
  }
  importNeedsRate() {
    return needsRate(this.importDraft().currency);
  }
  updateImportNumber(
    field: 'total' | 'shipping' | 'discount' | 'tax' | 'extras',
    value: number | null,
  ) {
    this.importDraft.update((draft) => ({ ...draft, [field]: value }));
  }
  updateImportItem(
    index: number,
    field: 'description' | 'sku' | 'quantity' | 'unit_cost' | 'discount_amount',
    value: string | number | null,
  ) {
    this.importDraft.update((draft) => ({
      ...draft,
      items: draft.items.map((item, i) => {
        if (i !== index) return item;
        const updated = {
          ...item,
          [field]: field === 'description' || field === 'sku' ? value : Number(value ?? 0),
        };
        if (field === 'quantity' || field === 'unit_cost' || field === 'discount_amount')
          updated.line_total = Math.max(
            0,
            Number(updated.quantity) * Number(updated.unit_cost) - Number(updated.discount_amount),
          );
        return updated;
      }),
    }));
  }
  setImportMoneyValidity(key: string, invalid: boolean) {
    this.importMoneyValidity.update((values) => ({ ...values, [key]: invalid }));
  }
  importNotes(
    review: any,
    draft: {
      orderNumber: string;
      documentDate: string;
      total: number | null;
      shipping: number | null;
      discount: number | null;
      tax: number | null;
    },
  ): string {
    return importNotes(review.profile.name, draft);
  }
  importPlanLine(index: number) {
    return this.importPlan().plan?.lines[index] ?? null;
  }
  canConfirmImport() {
    // P0: além dos bloqueios da revisão (P14), o fechamento do documento precisa fechar — a
    // compra já nasce com a cotação do papel aceita e o pedido registrado.
    return this.importPlan().error === '' && this.importBlockers().length === 0;
  }
  setImportType(value: 'parts' | 'expense') {
    this.importType.set(value);
    if (value === 'expense' && !this.importCategory())
      this.importCategory.set(this.expenseCategories[0]);
  }
  setImportPaidNow(value: boolean) {
    this.importPaidNow.set(value);
    if (value && !this.importPaidDate()) this.importPaidDate.set(today());
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
  addImportLine() {
    this.importDraft.update((draft) => ({
      ...draft,
      items: [...draft.items, emptyImportLine()],
    }));
  }
  removeImportLine(index: number) {
    this.importDraft.update((draft) => ({
      ...draft,
      items: draft.items.filter((_, i) => i !== index),
    }));
    this.importMoneyValidity.update((values) =>
      Object.fromEntries(Object.entries(values).filter(([key]) => !key.startsWith('item-'))),
    );
  }
  closeImportReview() {
    if (this.creatingImport()) return;
    this.importReview.set(null);
    this.importFile.set(null);
    this.importId.set(null);
    this.importError.set('');
    this.importProductModal.set(false);
  }
}
