import { CurrencyPipe, DatePipe, DecimalPipe } from '@angular/common';
import { Component, inject, output } from '@angular/core';

import { AuthService } from '../../../core/auth.service';
import { Purchase, PurchaseListItem } from '../../../core/models';
import { canAdjustStock, canManagePurchases, canReadCosts } from '../../../core/user-access';
import { PurchaseDetailAside } from './purchase-detail-aside';
import { PurchaseDetailDraft } from './purchase-detail-draft';
import { PurchaseDetailEditing } from './purchase-detail-editing';
import { PurchaseDetailQuotes } from './purchase-detail-quotes';
import { PurchaseQuoteLogic } from './purchase-quote-logic';
import { PurchaseDetailReceive } from './purchase-detail-receive';
import { PurchaseDetailState } from './purchase-detail-state';

/**
 * Painel de detalhe da compra: a casca com o cabeçalho, as etapas e a grade de seções.
 *
 * O estado vive em `PurchaseDetailState` e cada seção densa (rascunho, recebimento, cotações,
 * resumo lateral) é um componente próprio. Os apelidos abaixo mantêm o template igual ao que era
 * quando tudo isso estava na página de compras.
 */
@Component({
  selector: 'app-purchase-detail',
  imports: [
    CurrencyPipe,
    DatePipe,
    DecimalPipe,
    PurchaseDetailAside,
    PurchaseDetailDraft,
    PurchaseDetailReceive,
    PurchaseDetailQuotes,
  ],
  templateUrl: './purchase-detail.html',
})
export class PurchaseDetail {
  private readonly flow = inject(PurchaseDetailState);
  private readonly quotes = inject(PurchaseQuoteLogic);
  private readonly editing = inject(PurchaseDetailEditing);
  private readonly auth = inject(AuthService);

  /** Copiar a compra e excluir são ações da página: aqui só saem como pedido. */
  readonly copy = output<Purchase>();
  readonly remove = output<Purchase>();

  readonly detail = this.flow.detail;
  readonly saving = this.flow.saving;
  readonly error = this.flow.error;
  readonly workflow = this.flow.workflow;
  readonly draftEditor = this.editing.draftEditor;

  canManagePurchases() {
    return canManagePurchases(this.auth.user()?.role);
  }
  canAdjustStock() {
    return canAdjustStock(this.auth.user()?.role);
  }
  canReadCosts() {
    return canReadCosts(this.auth.user()?.role);
  }
  purchaseStatusLabel(purchase: PurchaseListItem) {
    return this.flow.purchaseStatusLabel(purchase);
  }
  dateOnly(value: string | null | undefined) {
    return this.flow.dateOnly(value);
  }
  stepIndex(status: Purchase['status']) {
    return this.flow.stepIndex(status);
  }
  isOverdue(purchase: PurchaseListItem) {
    return this.flow.isOverdue(purchase);
  }
  formatBytes(bytes: number) {
    return this.flow.formatBytes(bytes);
  }
  uploadAttachments(purchase: Purchase, files: FileList | null) {
    this.flow.uploadAttachments(purchase, files);
  }
  downloadAttachment(purchase: Purchase, attachment: Purchase['attachments'][number]) {
    this.flow.downloadAttachment(purchase, attachment);
  }
  openDraftEditor() {
    this.editing.openDraftEditor();
  }
  closeDraftEditor() {
    this.editing.closeDraftEditor();
  }
  placeOrder() {
    this.quotes.placeOrder();
  }
  copyPurchase(purchase: Purchase) {
    this.copy.emit(purchase);
  }
}
