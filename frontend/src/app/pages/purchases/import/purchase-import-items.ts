import { CurrencyPipe, DecimalPipe } from '@angular/common';
import { Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { AuthService } from '../../../core/auth.service';
import { Product } from '../../../core/models';
import { canManageCatalog, canReadCosts } from '../../../core/user-access';
import { MoneyInputDirective } from '../../../shared/money-input.directive';
import { PurchaseImportProducts } from './purchase-import-products';
import { PurchaseImportState } from './purchase-import-state';

/**
 * Grade de itens da revisão e o cadastro rápido de peça aberto a partir dela.
 *
 * Ficou separada da casca do modal porque é a parte mais densa da conferência (uma linha por
 * peça, com busca, vínculo e custo final).
 */
@Component({
  selector: 'app-purchase-import-items',
  imports: [CurrencyPipe, DecimalPipe, FormsModule, MoneyInputDirective],
  templateUrl: './purchase-import-items.html',
  styleUrl: './purchase-import-items.scss',
})
export class PurchaseImportItems {
  private readonly flow = inject(PurchaseImportState);
  private readonly productTools = inject(PurchaseImportProducts);
  private readonly auth = inject(AuthService);

  readonly importDraft = this.flow.importDraft;
  readonly importPlanLine = (index: number) => this.flow.importPlanLine(index);
  readonly importMoneyValidity = this.flow.importMoneyValidity;
  readonly importProductSearch = this.flow.importProductSearch;
  readonly importProductResults = this.flow.importProductResults;
  readonly importProductModal = this.flow.importProductModal;
  readonly importProductDraft = this.flow.importProductDraft;
  readonly importProductError = this.flow.importProductError;
  readonly savingImportProduct = this.flow.savingImportProduct;
  readonly products = this.flow.products;

  canManageCatalog() {
    return canManageCatalog(this.auth.user()?.role);
  }
  canReadCosts() {
    return canReadCosts(this.auth.user()?.role);
  }
  itemOrigin(item: {
    source?: string;
    confidence?: number;
    quantity_derived?: boolean;
    quantityDerived?: boolean;
  }) {
    return this.flow.itemOrigin(item);
  }
  updateImportItem(
    index: number,
    field: 'description' | 'sku' | 'quantity' | 'unit_cost' | 'discount_amount',
    value: string | number | null,
  ) {
    this.flow.updateImportItem(index, field, value);
  }
  setImportMoneyValidity(key: string, invalid: boolean) {
    this.flow.setImportMoneyValidity(key, invalid);
  }
  searchImportProducts(index: number, value: string) {
    this.productTools.searchImportProducts(index, value);
  }
  selectedImportProduct(id: string | null) {
    return this.productTools.selectedImportProduct(id);
  }
  selectImportedProduct(index: number, product: Product) {
    this.productTools.selectImportedProduct(index, product);
  }
  selectImportedProductById(index: number, productId: string) {
    this.productTools.selectImportedProductById(index, productId);
  }
  setImportStockControlled(index: number, value: boolean) {
    this.productTools.setImportStockControlled(index, value);
  }
  clearImportedProduct(index: number) {
    this.productTools.clearImportedProduct(index);
  }
  openImportProductCreate(index: number) {
    this.productTools.openImportProductCreate(index);
  }
  closeImportProductCreate() {
    this.productTools.closeImportProductCreate();
  }
  updateImportProduct(field: string, value: string | number | null) {
    this.productTools.updateImportProduct(field, value);
  }
  canSaveImportProduct() {
    return this.productTools.canSaveImportProduct();
  }
  saveImportProduct() {
    this.productTools.saveImportProduct();
  }
  removeImportLine(index: number) {
    this.flow.removeImportLine(index);
  }
}
