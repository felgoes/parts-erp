import { CurrencyPipe } from '@angular/common';
import { Component, inject, output } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { MoneyInputDirective } from '../../../shared/money-input.directive';
import { PurchaseImportState } from './purchase-import-state';

/**
 * Fechamento do documento e decisões da revisão: tipo do lançamento, valor pago, conferência
 * do rateio, motivos que impedem a confirmação e as ações do modal.
 */
@Component({
  selector: 'app-purchase-import-check',
  imports: [CurrencyPipe, FormsModule, MoneyInputDirective],
  templateUrl: './purchase-import-check.html',
  styleUrl: './purchase-import-check.scss',
})
export class PurchaseImportCheck {
  private readonly flow = inject(PurchaseImportState);
  /** A confirmação é do componente da revisão, que monta e envia o documento já lido. */
  readonly confirm = output<void>();

  readonly importPlan = this.flow.importPlan;
  readonly importReview = this.flow.importReview;
  readonly importDraft = this.flow.importDraft;
  readonly importDuplicate = this.flow.importDuplicate;
  readonly importError = this.flow.importError;
  readonly importType = this.flow.importType;
  readonly importCategory = this.flow.importCategory;
  readonly importPaidNow = this.flow.importPaidNow;
  readonly importPaidDate = this.flow.importPaidDate;
  readonly importPaidMethod = this.flow.importPaidMethod;
  readonly expenseCategories = this.flow.expenseCategories;
  readonly creatingImport = this.flow.creatingImport;

  importBlockers() {
    return this.flow.importBlockers();
  }
  importClosingDifference() {
    return this.flow.importClosingDifference();
  }
  importSubtotalDifference() {
    return this.flow.importSubtotalDifference();
  }
  importHasItemsToCheck() {
    return this.flow.importHasItemsToCheck();
  }
  importPaidDifference() {
    return this.flow.importPaidDifference();
  }
  importNeedsRate() {
    return this.flow.importNeedsRate();
  }
  canConfirmImport() {
    return this.flow.canConfirmImport();
  }
  setImportType(value: 'parts' | 'expense') {
    this.flow.setImportType(value);
  }
  setImportPaidNow(value: boolean) {
    this.flow.setImportPaidNow(value);
  }
  setImportPaid(value: number | null) {
    this.flow.setImportPaid(value);
  }
  setImportRateFromInput(value: string) {
    this.flow.setImportRateFromInput(value);
  }
  useImportCandidate(candidate: { text: string; quantity?: number; unit_cost?: number }) {
    this.flow.useImportCandidate(candidate);
  }
  closeImportReview() {
    this.flow.closeImportReview();
  }
  createImportedPurchase() {
    this.confirm.emit();
  }
}
