import { CurrencyPipe } from '@angular/common';
import { Component, inject } from '@angular/core';
import { FormsModule, ReactiveFormsModule } from '@angular/forms';

import { Purchase, PurchaseItem, PurchaseQuote } from '../../../core/models';
import { MoneyInputDirective } from '../../../shared/money-input.directive';
import { PurchaseQuoteLogic } from './purchase-quote-logic';
import { PurchaseDetailState } from './purchase-detail-state';

/** Cotações de fornecedor: registro, rateio do total, custo final por peça e escolha da vencedora. */
@Component({
  selector: 'app-purchase-detail-quotes',
  imports: [CurrencyPipe, FormsModule, MoneyInputDirective, ReactiveFormsModule],
  templateUrl: './purchase-detail-quotes.html',
  styleUrl: './purchase-detail-quotes.scss',
})
export class PurchaseDetailQuotes {
  private readonly flow = inject(PurchaseDetailState);
  private readonly quotes = inject(PurchaseQuoteLogic);

  readonly detail = this.flow.detail;
  readonly quoteForm = this.quotes.quoteForm;
  readonly quoteRounding = this.quotes.quoteRounding;
  readonly saving = this.flow.saving;

  quoteUnitCost(item: PurchaseItem) {
    return this.quotes.quoteUnitCost(item);
  }
  quoteTotal(purchase: Purchase) {
    return this.quotes.quoteTotal(purchase);
  }
  quoteNet(purchase: Purchase) {
    return this.quotes.quoteNet(purchase);
  }
  setQuoteConditionType(value: string) {
    this.quotes.setQuoteConditionType(value);
  }
  setQuoteConditionNumber(
    field: 'installment_count' | 'first_due_days' | 'interval_days',
    value: string,
  ) {
    this.quotes.setQuoteConditionNumber(field, value);
  }
  applyQuoteConditionPreset(preset: 'cash' | '30' | '30/60' | '30/60/90') {
    this.quotes.applyQuoteConditionPreset(preset);
  }
  quoteConditionPreview() {
    return this.quotes.quoteConditionPreview();
  }
  quoteConditionLabel(quote: PurchaseQuote) {
    return this.quotes.quoteConditionLabel(quote);
  }
  quoteDirectionNote() {
    return this.quotes.quoteDirectionNote();
  }
  quoteMismatch(purchase: Purchase) {
    return this.quotes.quoteMismatch(purchase);
  }
  setQuoteTotal(value: number | null) {
    this.quotes.setQuoteTotal(value);
  }
  setQuoteUnitCost(item: PurchaseItem, value: number | null) {
    this.quotes.setQuoteUnitCost(item, value);
  }
  setQuoteCostValidity(itemId: string, invalid: boolean) {
    this.quotes.setQuoteCostValidity(itemId, invalid);
  }
  quoteCostHasErrors() {
    return this.quotes.quoteCostHasErrors();
  }
  quoteCostsComplete(purchase: Purchase) {
    return this.quotes.quoteCostsComplete(purchase);
  }
  addQuote() {
    this.quotes.addQuote();
  }
  selectQuote(id: string) {
    this.quotes.selectQuote(id);
  }
}
