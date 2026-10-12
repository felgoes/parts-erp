import { DestroyRef, Injectable, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, Validators } from '@angular/forms';
import { finalize } from 'rxjs';

import { ApiService } from '../../../core/api.service';
import { PaymentConditionType, Purchase, PurchaseItem, PurchaseQuote } from '../../../core/models';
import { PurchaseDetailState } from './purchase-detail-state';

/**
 * Cotação da compra: formulário, rateio do total por peça, prévia do custo final, condição de
 * pagamento e registro da cotação vencedora.
 */
@Injectable()
export class PurchaseQuoteLogic {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  readonly flow = inject(PurchaseDetailState);
  private readonly destroyRef: DestroyRef;

  constructor() {
    this.destroyRef = inject(DestroyRef);
    // Digitar o total da cotação redistribui o valor entre as peças na hora.
    this.quoteForm.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      const purchase = this.flow.detail();
      const typed = this.quoteTotalValue();
      if (purchase && typed !== null) this.distributeQuoteTotal(purchase, typed);
    });
    // Cada abertura de compra zera o rateio e a previa da cotacao.
    this.flow.detailChanged.subscribe((purchase) => {
      this.quoteCosts.set(Object.fromEntries(purchase.items.map((item) => [item.id, 0])));
      this.quoteCostValidity.set({});
      this.quoteTotalValue.set(null);
      this.quoteRounding.set(0);
    });
  }

  readonly quoteForm = this.fb.nonNullable.group({
    supplier_name: ['', Validators.required],
    supplier_contact: [''],
    freight_amount: [0, [Validators.required, Validators.min(0)]],
    tax_amount: [0, [Validators.required, Validators.min(0)]],
    extras_amount: [0, [Validators.required, Validators.min(0)]],
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
  readonly quoteCosts = signal<Record<string, number>>({});
  readonly quoteCostValidity = signal<Record<string, boolean>>({});
  readonly quoteTotalValue = signal<number | null>(null);
  readonly quoteRounding = signal(0);
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
        Number(value.tax_amount || 0) +
        Number(value.extras_amount || 0) -
        Number(value.discount_amount || 0),
    );
  }
  /** Líquido das peças: total − frete − impostos − taxas extras + desconto. */
  quoteNet(purchase: Purchase) {
    const value = this.quoteForm.getRawValue();
    return this.round2(
      this.quoteTotal(purchase) -
        Number(value.freight_amount || 0) -
        Number(value.tax_amount || 0) -
        Number(value.extras_amount || 0) +
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
    const purchase = this.flow.detail();
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
        Number(value.tax_amount || 0) -
        Number(value.extras_amount || 0) +
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
    const purchase = this.flow.detail();
    if (
      !purchase ||
      this.quoteForm.invalid ||
      this.quoteCostHasErrors() ||
      !this.quoteCostsComplete(purchase) ||
      this.quoteTotal(purchase) < 0 ||
      this.flow.saving()
    )
      return;
    this.flow.saving.set(true);
    this.flow.error.set('');
    const value = this.quoteForm.getRawValue();
    this.api
      .addPurchaseQuote(purchase.id, {
        ...value,
        total: this.quoteTotal(purchase),
        item_costs: this.quoteCosts(),
      })
      .pipe(finalize(() => this.flow.saving.set(false)))
      .subscribe({
        next: (updated) => {
          this.flow.setPurchase(updated);
          this.quoteForm.reset({
            supplier_name: '',
            supplier_contact: '',
            freight_amount: 0,
            tax_amount: 0,
            extras_amount: 0,
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
          this.flow.error.set(err.error?.detail || 'Não foi possível registrar a cotação.'),
      });
  }
  selectQuote(id: string) {
    const purchase = this.flow.detail();
    if (!purchase || this.flow.saving()) return;
    if (!confirm('Aprovar esta cotação? A compra seguirá para envio do pedido ao fornecedor.'))
      return;
    this.flow.runAction(this.api.selectPurchaseQuote(purchase.id, id));
  }
  placeOrder() {
    const purchase = this.flow.detail();
    if (purchase) this.flow.runAction(this.api.placePurchaseOrder(purchase.id));
  }
}
