import { Injectable, inject, signal } from '@angular/core';
import { finalize } from 'rxjs';

import { ApiService } from '../../../core/api.service';
import { Product } from '../../../core/models';
import { PurchaseImportState } from './purchase-import-state';
import { ImportProductDraft, emptyImportProductDraft } from './purchase-import-model';

/**
 * Busca, vínculo e cadastro de peça dentro da revisão de importação.
 *
 * Depende do estado da revisão para gravar o vínculo na linha e para oferecer o catálogo.
 */
@Injectable()
export class PurchaseImportProducts {
  private readonly api = inject(ApiService);
  private readonly flow = inject(PurchaseImportState);

  searchImportProducts(index: number, value: string) {
    this.flow.importProductSearch.update((rows) => ({ ...rows, [index]: value }));
    const revision = (this.flow.importSearchRevision()[index] || 0) + 1;
    this.flow.importSearchRevision.update((rows) => ({ ...rows, [index]: revision }));
    if (!value.trim()) {
      this.flow.importProductResults.update((rows) => ({ ...rows, [index]: [] }));
      return;
    }
    this.api.products(value.trim(), false).subscribe({
      next: (products) => {
        if (this.flow.importSearchRevision()[index] === revision)
          this.flow.importProductResults.update((rows) => ({
            ...rows,
            [index]: products.filter(
              (product) => product.stock_type === 'product' || product.stock_type === 'warehouse',
            ),
          }));
      },
      error: () => {
        if (this.flow.importSearchRevision()[index] === revision)
          this.flow.importProductResults.update((rows) => ({ ...rows, [index]: [] }));
      },
    });
  }
  selectedImportProduct(id: string | null) {
    return id
      ? this.flow.products().find((product) => product.id === id) ||
          Object.values(this.flow.importProductResults())
            .flat()
            .find((product) => product.id === id) ||
          null
      : null;
  }
  selectImportedProduct(index: number, product: Product) {
    this.flow.importDraft.update((draft) => ({
      ...draft,
      items: draft.items.map((item, i) =>
        i === index
          ? {
              ...item,
              product_id: product.id,
              stock_controlled: true,
              sku: item.sku || product.sku,
            }
          : item,
      ),
    }));
    this.flow.products.update((items) =>
      items.some((entry) => entry.id === product.id) ? items : [...items, product],
    );
    this.flow.importProductSearch.update((rows) => ({ ...rows, [index]: '' }));
    this.flow.importProductResults.update((rows) => ({ ...rows, [index]: [] }));
  }
  selectImportedProductById(index: number, productId: string) {
    if (!productId) {
      this.clearImportedProduct(index);
      return;
    }
    const product =
      this.flow.products().find((entry) => entry.id === productId) ??
      Object.values(this.flow.importProductResults())
        .flat()
        .find((entry) => entry.id === productId);
    if (product) this.selectImportedProduct(index, product);
  }
  setImportStockControlled(index: number, value: boolean) {
    this.flow.importDraft.update((draft) => ({
      ...draft,
      items: draft.items.map((item, i) =>
        i === index
          ? { ...item, stock_controlled: value, product_id: value ? item.product_id : null }
          : item,
      ),
    }));
  }
  clearImportedProduct(index: number) {
    this.flow.importDraft.update((draft) => ({
      ...draft,
      items: draft.items.map((item, i) => (i === index ? { ...item, product_id: null } : item)),
    }));
  }
  openImportProductCreate(index: number) {
    const item = this.flow.importDraft().items[index];
    this.flow.importProductLine.set(index);
    this.flow.importProductError.set('');
    this.flow.importProductDraft.set({
      sku: item.sku,
      stock_type: 'product',
      name: item.description,
      description: item.description,
      sale_price: 0,
      cost_price: 0,
      minimum_stock: 0,
      brand: '',
      manufacturer: '',
      manufacturer_part_number: '',
      barcode: '',
      category: '',
      item_condition: 'new',
      warranty_days: null,
      origin_country: '',
      weight_g: null,
      package_length_cm: null,
      package_width_cm: null,
      package_height_cm: null,
    });
    this.flow.importProductModal.set(true);
  }
  closeImportProductCreate() {
    if (!this.flow.savingImportProduct()) this.flow.importProductModal.set(false);
  }
  updateImportProduct(field: string, value: string | number | null) {
    this.flow.importProductDraft.update((draft) => {
      const numeric = [
        'sale_price',
        'cost_price',
        'minimum_stock',
        'warranty_days',
        'weight_g',
        'package_length_cm',
        'package_width_cm',
        'package_height_cm',
      ].includes(field);
      return {
        ...draft,
        [field]: numeric ? (value === '' || value == null ? null : Number(value)) : value,
      } as typeof draft;
    });
  }
  canSaveImportProduct() {
    const value = this.flow.importProductDraft();
    return (
      value.sku.trim().length > 0 &&
      value.sku.trim().length <= 80 &&
      value.name.trim().length >= 2 &&
      value.name.trim().length <= 200
    );
  }
  saveImportProduct() {
    if (!this.canSaveImportProduct() || this.flow.savingImportProduct()) return;
    const index = this.flow.importProductLine(),
      draft = this.flow.importProductDraft();
    if (index == null) return;
    this.flow.savingImportProduct.set(true);
    this.flow.importProductError.set('');
    this.api
      .createProduct({
        ...draft,
        sku: draft.sku.trim(),
        name: draft.name.trim(),
        current_stock: 0,
        sale_price: draft.sale_price ?? 0,
        cost_price: draft.cost_price ?? 0,
        minimum_stock: draft.minimum_stock ?? 0,
        attributes: {},
        fitments: [],
      })
      .pipe(finalize(() => this.flow.savingImportProduct.set(false)))
      .subscribe({
        next: (product) => {
          this.selectImportedProduct(index, product);
          this.flow.importProductModal.set(false);
        },
        error: (err) =>
          this.flow.importProductError.set(
            err?.error?.detail ||
              'Não foi possível cadastrar o produto. Confira SKU e campos obrigatórios.',
          ),
      });
  }
}
