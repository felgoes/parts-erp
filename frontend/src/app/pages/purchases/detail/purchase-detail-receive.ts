import { CurrencyPipe, DecimalPipe } from '@angular/common';
import { Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { PurchaseItem } from '../../../core/models';
import { MoneyInputDirective } from '../../../shared/money-input.directive';
import { PurchaseDetailEditing } from './purchase-detail-editing';
import { PurchaseDetailState } from './purchase-detail-state';

/** Itens e recebimento: quantidade que chegou, produto de destino e registro de cada entrada. */
@Component({
  selector: 'app-purchase-detail-receive',
  imports: [CurrencyPipe, DecimalPipe, FormsModule, MoneyInputDirective],
  templateUrl: './purchase-detail-receive.html',
})
export class PurchaseDetailReceive {
  private readonly flow = inject(PurchaseDetailState);
  private readonly editing = inject(PurchaseDetailEditing);

  readonly detail = this.flow.detail;
  readonly progress = this.flow.progress;
  readonly receiveValues = this.editing.receiveValues;
  readonly saving = this.flow.saving;

  availableProducts(stockType: 'product' | 'warehouse') {
    return this.flow.availableProducts(stockType);
  }
  receiveQty(item: PurchaseItem) {
    return this.editing.receiveQty(item);
  }
  receiveObservation(item: PurchaseItem) {
    return this.editing.receiveObservation(item);
  }
  setReceiveObservation(item: PurchaseItem, value: string) {
    this.editing.setReceiveObservation(item, value);
  }
  setReceiveQty(item: PurchaseItem, value: string) {
    this.editing.setReceiveQty(item, value);
  }
  receiveProduct(item: PurchaseItem) {
    return this.editing.receiveProduct(item);
  }
  setReceiveProduct(item: PurchaseItem, value: string) {
    this.editing.setReceiveProduct(item, value);
  }
  createNewProduct(item: PurchaseItem) {
    return this.editing.createNewProduct(item);
  }
  setCreateNewProduct(item: PurchaseItem, value: boolean) {
    this.editing.setCreateNewProduct(item, value);
  }
  receive(item: PurchaseItem) {
    this.editing.receive(item);
  }
}
