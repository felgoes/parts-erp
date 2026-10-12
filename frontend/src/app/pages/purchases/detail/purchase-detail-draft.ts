import { CurrencyPipe, DecimalPipe } from '@angular/common';
import { Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { Purchase, PurchaseItem } from '../../../core/models';
import { PurchaseDetailEditing } from './purchase-detail-editing';
import { PurchaseDetailState } from './purchase-detail-state';

/**
 * Rascunho da compra: fornecedor, previsão, número do pedido, data do documento e linhas de peça,
 * tudo editável enquanto o pedido não foi enviado.
 */
@Component({
  selector: 'app-purchase-detail-draft',
  imports: [CurrencyPipe, DecimalPipe, FormsModule],
  templateUrl: './purchase-detail-draft.html',
})
export class PurchaseDetailDraft {
  private readonly flow = inject(PurchaseDetailState);
  private readonly editing = inject(PurchaseDetailEditing);

  readonly detail = this.flow.detail;
  readonly suppliers = this.flow.suppliers;
  readonly saving = this.flow.saving;
  readonly draftHeader = this.editing.draftHeader;
  readonly lineDrafts = this.editing.lineDrafts;
  readonly newLineDraft = this.editing.newLineDraft;

  setDraftHeader(
    field: 'supplier_name' | 'needed_by' | 'document_date' | 'supplier_order_number' | 'notes',
    value: string,
  ) {
    this.editing.setDraftHeader(field, value);
  }
  saveDraftHeader(purchase: Purchase) {
    this.editing.saveDraftHeader(purchase);
  }
  setLineDraft(itemId: string, field: 'description' | 'sku' | 'unit' | 'quantity', value: string) {
    this.editing.setLineDraft(itemId, field, value);
  }
  saveLine(purchase: Purchase, item: PurchaseItem) {
    this.editing.saveLine(purchase, item);
  }
  removePurchaseLine(purchase: Purchase, item: PurchaseItem) {
    this.editing.removePurchaseLine(purchase, item);
  }
  setNewLineDraft(field: 'description' | 'sku' | 'unit' | 'quantity', value: string) {
    this.editing.setNewLineDraft(field, value);
  }
  addDraftLine(purchase: Purchase) {
    this.editing.addDraftLine(purchase);
  }
}
