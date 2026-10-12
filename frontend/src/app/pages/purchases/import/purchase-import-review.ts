import { DecimalPipe } from '@angular/common';
import { Component, inject, output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { finalize } from 'rxjs';

import { ApiService } from '../../../core/api.service';
import { Purchase } from '../../../core/models';
import { MoneyInputDirective } from '../../../shared/money-input.directive';
import { PurchaseImportCheck } from './purchase-import-check';
import { PurchaseImportItems } from './purchase-import-items';
import { PurchaseImportState } from './purchase-import-state';

/**
 * Revisão da importação: a casca do modal, os campos do documento e a confirmação.
 *
 * O estado vive em `PurchaseImportState` e as seções maiores (grade de itens e fechamento) são
 * componentes próprios. Os apelidos abaixo existem para o template continuar falando a mesma
 * língua de quando tudo isso era a página de compras.
 */
@Component({
  selector: 'app-purchase-import-review',
  imports: [
    DecimalPipe,
    FormsModule,
    MoneyInputDirective,
    PurchaseImportItems,
    PurchaseImportCheck,
  ],
  templateUrl: './purchase-import-review.html',
})
export class PurchaseImportReview {
  private readonly api = inject(ApiService);
  private readonly flow = inject(PurchaseImportState);
  /** Compra criada a partir do documento: a página cuida da lista, do aviso e do detalhe. */
  readonly created = output<{ purchase: Purchase; document: { filename: string; size: number } }>();

  readonly importReview = this.flow.importReview;
  readonly importDraft = this.flow.importDraft;
  readonly importProfiles = this.flow.importProfiles;
  readonly importLoading = this.flow.importLoading;
  readonly creatingImport = this.flow.creatingImport;
  readonly importError = this.flow.importError;
  readonly importType = this.flow.importType;
  readonly importCategory = this.flow.importCategory;
  readonly importPaidNow = this.flow.importPaidNow;
  readonly importPaidDate = this.flow.importPaidDate;
  readonly importPaidMethod = this.flow.importPaidMethod;

  closeImportReview() {
    this.flow.closeImportReview();
  }
  changeImportProfile(profileId: string) {
    this.flow.changeImportProfile(profileId);
  }
  updateImportField(field: 'supplier' | 'orderNumber' | 'documentDate', value: string) {
    this.flow.updateImportField(field, value);
  }
  updateImportNumber(
    field: 'total' | 'shipping' | 'discount' | 'tax' | 'extras',
    value: number | null,
  ) {
    this.flow.updateImportNumber(field, value);
  }
  setImportMoneyValidity(key: string, invalid: boolean) {
    this.flow.setImportMoneyValidity(key, invalid);
  }
  fieldOrigin(field: { source?: string; confidence?: number } | undefined) {
    return this.flow.fieldOrigin(field);
  }
  addImportLine() {
    this.flow.addImportLine();
  }

  /**
   * Fecha a revisão criando a compra. Só roda quando não há bloqueio: o mesmo documento entra
   * uma única vez (o servidor reconhece o `source_import_id`) e a página recebe a compra pronta.
   */
  createImportedPurchase() {
    const review = this.flow.importReview();
    const file = this.flow.importFile();
    const draft = this.flow.importDraft();
    const importId = this.flow.importId();
    if (
      !review ||
      !file ||
      !importId ||
      !this.flow.canConfirmImport() ||
      this.flow.creatingImport()
    )
      return;
    this.flow.creatingImport.set(true);
    this.flow.importError.set('');
    const isExpense = this.flow.importType() === 'expense';
    const payload = {
      purchase_type: this.flow.importType(),
      source_import_id: importId,
      supplier_name: draft.supplier.trim() || null,
      expense_category: isExpense ? this.flow.importCategory().trim() || null : null,
      expense_amount: isExpense ? draft.total : null,
      supplier_id: this.flow.supplierByName(draft.supplier)?.id ?? null,
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
      paid_now: this.flow.importPaidNow(),
      paid_date: this.flow.importPaidNow() ? this.flow.importPaidDate() || null : null,
      paid_method: this.flow.importPaidNow() ? this.flow.importPaidMethod().trim() || null : null,
      document_date: draft.documentDate || null,
      notes: this.flow.importNotes(review, draft),
      // P0: o documento é a cotação da compra — os valores do papel entram uma única vez e são
      // rateados por peça no mesmo algoritmo mostrado na revisão. Lançamento de despesa segue o
      // fluxo de despesa (P14) e não leva a cotação do documento.
      import_document: isExpense
        ? null
        : {
            filename: file.name,
            total: draft.total,
            freight_amount: draft.shipping ?? 0,
            tax_amount: draft.tax ?? 0,
            extras_amount: draft.extras ?? 0,
            discount_amount: draft.discount ?? 0,
          },
      items: (isExpense
        ? draft.items.filter((item) => item.stock_controlled && item.product_id)
        : draft.items
      ).map((item) => ({
        sku: item.sku.trim(),
        description: item.description.trim(),
        quantity: item.quantity,
        unit_cost: item.unit_cost,
        product_id: item.product_id,
        line_discount_amount: item.discount_amount,
        // O total impresso na linha manda no fechamento: o papel arredonda o unitário na
        // vitrine e cobra o total exato da linha.
        line_total_amount: item.line_total || null,
      })),
    };
    this.api
      .confirmImportedPurchase(file, payload)
      .pipe(finalize(() => this.flow.creatingImport.set(false)))
      .subscribe({
        next: (purchase) => {
          const document = { filename: file.name, size: file.size };
          this.flow.closeImportReview();
          this.created.emit({ purchase, document });
        },
        error: (err) => this.flow.importError.set(this.errorText(err)),
      });
  }

  private errorText(err: any): string {
    const detail = err?.error?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail))
      return (
        detail
          .map((entry: { msg?: string }) => entry?.msg || '')
          .filter(Boolean)
          .join(' · ') || 'Confira os campos da revisão.'
      );
    if (detail?.message) return String(detail.message);
    return 'Não foi possível criar a compra revisada.';
  }
}
