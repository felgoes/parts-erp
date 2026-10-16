import { CurrencyPipe } from '@angular/common';
import { Component, inject, input, output, signal } from '@angular/core';
import {
  FormArray,
  FormBuilder,
  FormsModule,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { finalize } from 'rxjs';

import { ApiService } from '../../core/api.service';
import { PaymentConditionType, Product, Purchase, PurchaseListItem } from '../../core/models';
import { canManagePurchases } from '../../core/user-access';
import { AuthService } from '../../core/auth.service';
import { MoneyInputDirective } from '../../shared/money-input.directive';
import { EXPENSE_CATEGORIES } from './import/purchase-import-model';

export interface SupplierOption {
  id: string;
  name: string;
  contact: string | null;
  default_delivery_days: number | null;
  default_payment_terms: string | null;
}

/**
 * Cadastro manual da compra (peças ou despesa), com anexos na mesma operação.
 *
 * O catálogo e os fornecedores vêm da página por `input`: ela já carrega os dois para as outras
 * telas de compra, e aqui basta filtrar. A compra criada volta pelo `output`.
 */
@Component({
  selector: 'app-purchase-new',
  imports: [CurrencyPipe, FormsModule, MoneyInputDirective, ReactiveFormsModule],
  templateUrl: './purchase-new.html',
  styleUrl: './purchase-new.scss',
})
export class PurchaseNew {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly fb = inject(FormBuilder);

  readonly products = input<Product[]>([]);
  readonly suppliers = input<SupplierOption[]>([]);
  readonly created = output<Purchase>();
  /** Fornecedor cadastrado aqui: a página mantém a lista dela atualizada. */
  readonly supplierCreated = output<SupplierOption & { contact: null }>();

  readonly expenseCategories = EXPENSE_CATEGORIES;
  readonly saving = signal(false);
  readonly error = signal('');
  readonly selectedFiles = signal<File[]>([]);

  setAttachments(files: FileList | null) {
    this.selectedFiles.set(files ? Array.from(files).slice(0, 10) : []);
  }

  canManagePurchases() {
    return canManagePurchases(this.auth.user()?.role);
  }

  readonly showNew = signal(false);
  readonly form = this.fb.group({
    purchase_type: ['parts'],
    supplier_name: [''],
    supplier_order_number: [''],
    document_date: [''],
    expense_category: [''],
    expense_description: [''],
    expense_amount: [0, [Validators.min(0)]],
    needed_by: [''],
    notes: [''],
    payment_type: ['cash' as PaymentConditionType],
    installment_count: [1, [Validators.min(1), Validators.max(36)]],
    first_due_days: [0, [Validators.min(0)]],
    interval_days: [30, [Validators.min(1)]],
    items: this.fb.array([this.newLine()]),
  });
  readonly lines = this.form.controls.items as FormArray;
  // Filtro, busca e paginação acontecem no servidor: a tela guarda só o estado da consulta.
  private newLine() {
    return this.fb.group({
      product_id: [''],
      sku: [''],
      description: ['', Validators.required],
      unit: ['un', Validators.required],
      quantity: [1, [Validators.required, Validators.min(0.001)]],
      unit_cost: [0, [Validators.required, Validators.min(0)]],
    });
  }
  /** Abre o formulário limpo para cadastrar a compra manual. */
  open() {
    this.error.set('');
    this.selectedFiles.set([]);
    this.form.reset({
      purchase_type: 'parts',
      supplier_name: '',
      expense_category: '',
      expense_description: '',
      expense_amount: 0,
      needed_by: '',
      notes: '',
      payment_type: 'cash',
      installment_count: 1,
      first_due_days: 0,
      interval_days: 30,
    });
    while (this.lines.length) this.lines.removeAt(0);
    this.addLine();
    this.showNew.set(true);
  }

  /** Abre o formulário com os dados de uma compra existente, para repetir o pedido. */
  openCopy(purchase: PurchaseListItem) {
    this.error.set('');
    this.selectedFiles.set([]);
    this.form.reset({
      purchase_type: purchase.purchase_type,
      supplier_name: purchase.supplier_name ?? '',
      expense_category: purchase.expense_category ?? '',
      expense_description: purchase.expense_description ?? '',
      expense_amount: purchase.expense_amount ?? 0,
      needed_by: '',
      notes: purchase.notes
        ? `Cópia de ${purchase.number}\n${purchase.notes}`
        : `Cópia de ${purchase.number}`,
    });
    while (this.lines.length) this.lines.removeAt(0);
    if (purchase.purchase_type === 'parts') {
      for (const item of purchase.items) {
        const line = this.newLine();
        line.patchValue({
          product_id: item.product_id ?? '',
          sku: item.sku,
          description: item.description,
          quantity: item.quantity,
        });
        this.lines.push(line);
      }
    } else {
      this.addLine();
    }
    this.showNew.set(true);
  }
  addLine() {
    this.lines.push(this.newLine());
  }
  removeLine(index: number) {
    this.lines.removeAt(index);
  }
  selectProduct(index: number, id: string) {
    const line = this.lines.at(index);
    const product = this.products().find((entry) => entry.id === id);
    if (product) line.patchValue({ product_id: id, sku: product.sku, description: product.name });
    else line.patchValue({ product_id: '', sku: '', description: '' });
  }
  create() {
    const isExpense = this.form.controls.purchase_type.value === 'expense';
    if (
      this.saving() ||
      (!isExpense && this.form.invalid) ||
      (isExpense &&
        (!this.form.controls.expense_category.value ||
          Number(this.form.controls.expense_amount.value) < 0 ||
          this.lines.controls.some((line) => line.value.description && line.invalid)))
    )
      return;
    this.saving.set(true);
    this.error.set('');
    const value = this.form.getRawValue();
    this.api
      .createPurchase({
        purchase_type: value.purchase_type,
        payment_type: value.payment_type,
        installment_count: value.installment_count,
        first_due_days: value.first_due_days,
        interval_days: value.interval_days,
        supplier_name: value.supplier_name || null,
        supplier_id: this.supplierByName(value.supplier_name)?.id ?? null,
        supplier_order_number: value.supplier_order_number || null,
        document_date: value.document_date || null,
        expense_category: value.expense_category || null,
        expense_amount: value.expense_amount || null,
        expense_description: value.expense_description?.trim() || null,
        needed_by: value.needed_by || null,
        notes: value.notes || null,
        items: value.items
          .filter((item) => String(item.description || '').trim())
          .map((item) => ({ ...item, product_id: item.product_id || null })),
      })
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe({
        next: (purchase) => {
          this.showNew.set(false);
          const files = this.selectedFiles();
          if (files.length) {
            this.api
              .uploadPurchaseAttachments(purchase.id, files)
              .subscribe({ next: (updated) => this.created.emit(updated) });
          }
          this.created.emit(purchase);
        },
        error: (err) => this.error.set(err.error?.detail || 'Não foi possível salvar a compra.'),
      });
  }
  availableProducts(stockType: 'product' | 'warehouse') {
    return this.products().filter((product) => product.stock_type === stockType);
  }
  supplierByName(name: string | null | undefined) {
    const key = (name || '').trim().toLowerCase();
    return key
      ? (this.suppliers().find((supplier) => supplier.name.toLowerCase() === key) ?? null)
      : null;
  }
  applySupplierDefaults() {
    const supplier = this.supplierByName(this.form.controls.supplier_name.value);
    if (!supplier) return;
    if (supplier.default_delivery_days && !this.form.controls.needed_by.value) {
      const date = new Date();
      date.setDate(date.getDate() + supplier.default_delivery_days);
      this.form.controls.needed_by.setValue(date.toISOString().slice(0, 10));
    }
  }
  registerSupplier(name: string) {
    const trimmed = (name || '').trim();
    if (trimmed.length < 2 || this.saving()) return;
    this.saving.set(true);
    this.error.set('');
    this.api
      .createSupplier({ name: trimmed })
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe({
        next: (supplier) => {
          this.supplierCreated.emit({ ...supplier, contact: null });
          this.form.controls.supplier_name.setValue(supplier.name);
          this.applySupplierDefaults();
        },
        error: (err) =>
          this.error.set(err.error?.detail || 'Não foi possível cadastrar o fornecedor.'),
      });
  }
}
