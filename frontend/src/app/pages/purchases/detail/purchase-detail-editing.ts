import { Injectable, inject, signal } from '@angular/core';
import { finalize } from 'rxjs';

import { ApiService } from '../../../core/api.service';
import { Purchase, PurchaseItem, PurchasePayable } from '../../../core/models';
import { PurchaseDetailState } from './purchase-detail-state';

/**
 * Edição da compra depois de criada: rascunho (fornecedor, previsão, peças), recebimento peça a
 * peça, encerramento/cancelamento e baixa do título a pagar.
 */
@Injectable()
export class PurchaseDetailEditing {
  private readonly api = inject(ApiService);
  readonly flow = inject(PurchaseDetailState);

  constructor() {
    // Cada abertura de compra reinicia o recebimento e o rascunho desta compra.
    this.flow.detailChanged.subscribe((purchase) => this.resetFor(purchase));
  }

  private resetFor(purchase: Purchase) {
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
    this.primeDrafts(purchase);
    this.draftEditor.set(false);
  }

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
  readonly receiveValues = signal<
    Record<string, { quantity: number; productId: string; create: boolean }>
  >({});
  readonly receiptIds = signal<Record<string, string>>({});
  readonly receiveObservations = signal<Record<string, string>>({});
  readonly lifecycleForm = signal<{
    mode: 'cancel' | 'close';
    reason: string;
    resolution: 'keep_received' | 'return_received';
  } | null>(null);
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
  receive(item: PurchaseItem) {
    const purchase = this.flow.detail();
    if (!purchase || this.flow.saving()) return;
    const choice = this.receiveValues()[item.id];
    if (!choice || choice.quantity <= 0) return;
    const receiptId = this.receiptIds()[item.id] ?? crypto.randomUUID();
    this.receiptIds.update((ids) => ({ ...ids, [item.id]: receiptId }));
    this.flow.saving.set(true);
    this.flow.error.set('');
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
      .pipe(finalize(() => this.flow.saving.set(false)))
      .subscribe({
        next: (updated) => {
          this.flow.setPurchase(updated);
          this.clearReceiptId(item);
          this.api.products('', false).subscribe((items) => this.flow.products.set(items));
        },
        error: (err) =>
          this.flow.error.set(err.error?.detail || 'Não foi possível registrar o recebimento.'),
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
    const purchase = this.flow.detail();
    if (!purchase) return;
    this.flow.error.set('');
    this.lifecycleForm.set({
      mode,
      reason: '',
      resolution: this.flow.hasReceived(purchase) ? 'keep_received' : 'return_received',
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
    if (!form || this.flow.saving() || form.reason.trim().length < 3) return;
    const request =
      form.mode === 'cancel'
        ? this.api.cancelPurchaseWithReason(purchase.id, {
            reason: form.reason.trim(),
            resolution: form.resolution,
          })
        : this.api.closePurchaseBalance(purchase.id, { reason: form.reason.trim() });
    this.flow.saving.set(true);
    this.flow.error.set('');
    request.pipe(finalize(() => this.flow.saving.set(false))).subscribe({
      next: (updated) => {
        this.lifecycleForm.set(null);
        this.flow.setPurchase(updated);
      },
      error: (err) => this.flow.error.set(err.error?.detail || 'Não foi possível concluir a ação.'),
    });
  }
  receiveAll(purchase: Purchase) {
    if (this.flow.saving()) return;
    if (
      !confirm(
        `Receber todos os itens pendentes de ${purchase.number}? Itens sem produto vinculado serão cadastrados no catálogo.`,
      )
    )
      return;
    this.flow.saving.set(true);
    this.flow.error.set('');
    this.api
      .receivePurchaseInFull(purchase.id, { create_products: true })
      .pipe(finalize(() => this.flow.saving.set(false)))
      .subscribe({
        next: (updated) => {
          this.flow.setPurchase(updated);
          this.api.products('', false).subscribe((items) => this.flow.products.set(items));
        },
        error: (err) =>
          this.flow.error.set(err.error?.detail || 'Não foi possível registrar o recebimento.'),
      });
  }
  settlePayable(purchase: Purchase, payable: PurchasePayable) {
    if (this.flow.saving()) return;
    const amount = payable.amount.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
    if (!confirm(`Registrar o pagamento de ${amount} do título de ${purchase.number}?`)) return;
    this.flow.saving.set(true);
    this.flow.error.set('');
    this.api
      .settlePurchasePayable(purchase.id, payable.id)
      .pipe(finalize(() => this.flow.saving.set(false)))
      .subscribe({
        next: () => {
          this.flow.changed.next();
          this.api.purchase(purchase.id).subscribe((full) => this.flow.detail.set(full));
        },
        error: (err) =>
          this.flow.error.set(err.error?.detail || 'Não foi possível registrar o pagamento.'),
      });
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
    if (this.flow.saving()) return;
    const header = this.draftHeader();
    this.flow.saving.set(true);
    this.flow.error.set('');
    this.api
      .updatePurchase(purchase.id, {
        supplier_name: header.supplier_name || null,
        supplier_id: this.flow.supplierByName(header.supplier_name)?.id ?? null,
        supplier_order_number: header.supplier_order_number || null,
        document_date: header.document_date || null,
        needed_by: header.needed_by || null,
        notes: header.notes || null,
      })
      .pipe(finalize(() => this.flow.saving.set(false)))
      .subscribe({
        next: (updated) => this.flow.applyUpdate(updated),
        error: (err) =>
          this.flow.error.set(err.error?.detail || 'Não foi possível salvar os dados do pedido.'),
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
    if (!draft || this.flow.saving()) return;
    this.flow.saving.set(true);
    this.flow.error.set('');
    this.api
      .updatePurchaseItem(purchase.id, item.id, {
        description: draft.description,
        sku: draft.sku,
        unit: draft.unit,
        quantity: draft.quantity,
      })
      .pipe(finalize(() => this.flow.saving.set(false)))
      .subscribe({
        next: (updated) => this.flow.applyUpdate(updated),
        error: (err) => this.flow.error.set(err.error?.detail || 'Não foi possível salvar a peça.'),
      });
  }
  removePurchaseLine(purchase: Purchase, item: PurchaseItem) {
    if (this.flow.saving()) return;
    if (!confirm(`Remover ${item.description} desta negociação?`)) return;
    this.flow.saving.set(true);
    this.flow.error.set('');
    this.api
      .removePurchaseItem(purchase.id, item.id)
      .pipe(finalize(() => this.flow.saving.set(false)))
      .subscribe({
        next: (updated) => this.flow.applyUpdate(updated),
        error: (err) =>
          this.flow.error.set(err.error?.detail || 'Não foi possível remover a peça.'),
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
    if (!draft.description.trim() || draft.quantity <= 0 || this.flow.saving()) return;
    this.flow.saving.set(true);
    this.flow.error.set('');
    this.api
      .addPurchaseItem(purchase.id, {
        description: draft.description.trim(),
        sku: draft.sku.trim(),
        unit: draft.unit.trim() || 'un',
        quantity: draft.quantity,
        unit_cost: 0,
      })
      .pipe(finalize(() => this.flow.saving.set(false)))
      .subscribe({
        next: (updated) => {
          this.newLineDraft.set({ description: '', sku: '', unit: 'un', quantity: 1 });
          this.flow.applyUpdate(updated);
        },
        error: (err) =>
          this.flow.error.set(err.error?.detail || 'Não foi possível incluir a peça.'),
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
}
