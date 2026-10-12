import { CurrencyPipe, DatePipe, DecimalPipe } from '@angular/common';
import { Component, inject, output } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { AuthService } from '../../../core/auth.service';
import { Purchase, PurchaseListItem, PurchasePayable, PurchaseQuote } from '../../../core/models';
import { canManagePurchases } from '../../../core/user-access';
import { MoneyInputDirective } from '../../../shared/money-input.directive';
import { PurchaseDetailEditing } from './purchase-detail-editing';
import { PurchaseDetailState } from './purchase-detail-state';
import { PurchaseQuoteLogic } from './purchase-quote-logic';

/**
 * Resumo lateral da compra: valores, título a pagar com as parcelas, histórico e as ações de
 * encerramento (cancelar, encerrar saldo, receber tudo, baixar o título, excluir).
 */
@Component({
  selector: 'app-purchase-detail-aside',
  imports: [CurrencyPipe, DatePipe, DecimalPipe, FormsModule, MoneyInputDirective],
  templateUrl: './purchase-detail-aside.html',
})
export class PurchaseDetailAside {
  private readonly flow = inject(PurchaseDetailState);
  private readonly quotes = inject(PurchaseQuoteLogic);
  private readonly editing = inject(PurchaseDetailEditing);
  private readonly auth = inject(AuthService);

  readonly remove = output<Purchase>();

  readonly detail = this.flow.detail;
  readonly saving = this.flow.saving;
  readonly lifecycleForm = this.editing.lifecycleForm;

  canManagePurchases() {
    return canManagePurchases(this.auth.user()?.role);
  }
  selectedQuote(purchase: PurchaseListItem) {
    return this.flow.selectedQuote(purchase);
  }
  selectedDetailQuote(purchase: Purchase): PurchaseQuote | null {
    return this.flow.selectedDetailQuote(purchase);
  }
  purchaseStatusNote(purchase: Purchase) {
    return this.flow.purchaseStatusNote(purchase);
  }
  payableLabel(payable: PurchasePayable) {
    return this.flow.payableLabel(payable);
  }
  dateOnly(value: string | null | undefined) {
    return this.flow.dateOnly(value);
  }
  isActive(purchase: Purchase) {
    return this.flow.isActive(purchase);
  }
  hasReceived(purchase: Purchase) {
    return this.flow.hasReceived(purchase);
  }
  totalUnits(purchase: Purchase) {
    return this.flow.totalUnits(purchase);
  }
  receivedUnits(purchase: Purchase) {
    return this.flow.receivedUnits(purchase);
  }
  quoteConditionLabel(quote: PurchaseQuote) {
    return this.quotes.quoteConditionLabel(quote);
  }
  openLifecycleForm(mode: 'cancel' | 'close') {
    this.editing.openLifecycleForm(mode);
  }
  setLifecycleReason(value: string) {
    this.editing.setLifecycleReason(value);
  }
  setLifecycleResolution(value: 'keep_received' | 'return_received') {
    this.editing.setLifecycleResolution(value);
  }
  submitLifecycle(purchase: Purchase) {
    this.editing.submitLifecycle(purchase);
  }
  receiveAll(purchase: Purchase) {
    this.editing.receiveAll(purchase);
  }
  settlePayable(purchase: Purchase, payable: PurchasePayable) {
    this.editing.settlePayable(purchase, payable);
  }
  openDelete(purchase: Purchase) {
    this.remove.emit(purchase);
  }
}
