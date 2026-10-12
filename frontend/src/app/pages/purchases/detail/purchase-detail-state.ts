import { DestroyRef, Injectable, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subject, finalize } from 'rxjs';

import { ApiService } from '../../../core/api.service';
import { LiveUpdatesService } from '../../../core/live-updates.service';
import {
  Product,
  Purchase,
  PurchaseItem,
  PurchaseListItem,
  PurchasePayable,
  PurchaseQuote,
  PurchaseStatus,
} from '../../../core/models';
import { dateOnlyLabel, dateOnlyValue } from '../../../shared/date-only';

export interface SupplierOption {
  id: string;
  name: string;
  contact: string | null;
  default_delivery_days: number | null;
  default_payment_terms: string | null;
}

/**
 * Estado do painel de detalhe da compra: a compra aberta, o catálogo, os anexos e as contas de
 * leitura que a tela usa para mostrar etapa, progresso e valores.
 *
 * Os blocos maiores (cotações, recebimento, rascunho) ficam em serviços próprios que dependem
 * deste, para cada arquivo caber no teto de leitura.
 */
@Injectable()
export class PurchaseDetailState {
  private readonly api = inject(ApiService);
  private readonly live = inject(LiveUpdatesService);
  private readonly destroyRef = inject(DestroyRef);

  /** Avisa a página quando algo muda para ela recarregar a lista. */
  readonly changed = new Subject<void>();
  /** Avisa os servicos do detalhe que a compra aberta mudou, para cada um reiniciar o seu pedaco. */
  readonly detailChanged = new Subject<Purchase>();
  /** Etapas da compra, usadas no filtro da lista e no rotulo do detalhe. */
  readonly statuses: { value: string; label: string }[] = [
    { value: 'negotiating', label: 'Em negociacao' },
    { value: 'approved', label: 'Aprovada' },
    { value: 'ordered', label: 'Pedido enviado' },
    { value: 'partially_received', label: 'Recebimento parcial' },
    { value: 'received', label: 'Recebida' },
    { value: 'closed', label: 'Encerrada' },
    { value: 'cancelled', label: 'Cancelada' },
  ];
  readonly saving = signal(false);
  readonly error = signal('');

  readonly products = signal<Product[]>([]);
  readonly suppliers = signal<
    Array<{
      id: string;
      name: string;
      contact: string | null;
      default_delivery_days: number | null;
      default_payment_terms: string | null;
    }>
  >([]);
  readonly detail = signal<Purchase | null>(null);
  readonly selectedFiles = signal<File[]>([]);
  readonly workflow = [
    { value: 'negotiating', label: 'Negociação' },
    { value: 'approved', label: 'Aprovação' },
    { value: 'ordered', label: 'Pedido' },
    { value: 'received', label: 'Recebimento' },
  ];
  refreshProducts() {
    this.api
      .products('', false)
      .subscribe({ next: (items) => this.products.set(items), error: () => undefined });
  }
  loadSuppliers() {
    this.api
      .suppliers()
      .subscribe({ next: (items) => this.suppliers.set(items), error: () => undefined });
  }
  setAttachments(files: FileList | null) {
    this.selectedFiles.set(files ? Array.from(files).slice(0, 10) : []);
  }
  uploadAttachments(purchase: Purchase, files: FileList | null) {
    const selected = files ? Array.from(files).slice(0, 10) : [];
    if (!selected.length) return;
    this.saving.set(true);
    this.api
      .uploadPurchaseAttachments(purchase.id, selected)
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe({
        next: (updated) => this.setPurchase(updated),
        error: (err) =>
          this.error.set(err.error?.detail || 'Não foi possível anexar os documentos.'),
      });
  }
  downloadAttachment(purchase: Purchase, attachment: Purchase['attachments'][number]) {
    this.api.downloadPurchaseAttachment(purchase.id, attachment.id, attachment.filename);
  }
  formatBytes(bytes: number) {
    return bytes < 1024 * 1024
      ? `${Math.ceil(bytes / 1024)} KB`
      : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  }
  openDetails(purchase: PurchaseListItem) {
    // A lista não traz histórico, anexos nem títulos (projeção leve): o detalhe busca a
    // compra completa ao abrir, então a tela sempre mostra o estado atual.
    this.error.set('');
    this.api.purchase(purchase.id).subscribe({
      next: (full) => this.showDetail(full),
      error: () => this.error.set('Não foi possível abrir a compra. Tente novamente.'),
    });
  }
  showDetail(purchase: Purchase) {
    this.detail.set(purchase);
    this.detailChanged.next(purchase);
  }
  selectedQuote(purchase: PurchaseListItem) {
    return purchase.quotes.find((quote) => quote.id === purchase.selected_quote_id) ?? null;
  }
  // O detalhe mostra o rateio e a condição da cotação: ali a compra é o registro completo.
  selectedDetailQuote(purchase: Purchase): PurchaseQuote | null {
    return purchase.quotes.find((quote) => quote.id === purchase.selected_quote_id) ?? null;
  }
  statusLabel(status: PurchaseStatus) {
    return this.statuses.find((entry) => entry.value === status)?.label ?? status;
  }
  purchaseStatusLabel(purchase: PurchaseListItem) {
    return this.statusLabel(purchase.status);
  }
  purchaseStatusNote(purchase: Purchase) {
    if (purchase.status === 'cancelled')
      return purchase.cancel_reason ? `Cancelada · ${purchase.cancel_reason}` : 'Compra cancelada.';
    if (purchase.status === 'closed')
      return 'Saldo pendente encerrado; o material recebido foi mantido no estoque.';
    return '';
  }
  payableLabel(payable: PurchasePayable) {
    if (payable.status === 'paid')
      return `Pago${payable.payment_method ? ' · ' + payable.payment_method : ''}`;
    if (payable.status === 'cancelled') return 'Encerrado com o cancelamento';
    if (payable.status === 'partial')
      return `Baixa parcial · vence ${this.dateLabel(payable.due_date)}`;
    return `Vence ${this.dateLabel(payable.due_date)}`;
  }
  dateLabel(value: string) {
    return dateOnlyLabel(value);
  }
  dateOnly(value: string | null | undefined) {
    return dateOnlyLabel(value);
  }
  isActive(purchase: Purchase) {
    return purchase.status !== 'cancelled' && purchase.status !== 'closed';
  }
  hasReceived(purchase: Purchase) {
    return purchase.items.some(
      (item) => item.received_quantity - (item.returned_quantity ?? 0) > 0,
    );
  }
  stepIndex(status: PurchaseStatus) {
    if (status === 'cancelled') return -1;
    if (status === 'received' || status === 'closed') return 4;
    if (status === 'partially_received') return 3;
    return ['negotiating', 'approved', 'ordered'].indexOf(status);
  }
  // A API serializa Decimal como string: some sempre com Number para não concatenar.
  progress(item: PurchaseItem) {
    const quantity = Number(item.quantity ?? 0);
    return quantity ? Math.min(100, (Number(item.received_quantity ?? 0) / quantity) * 100) : 0;
  }
  totalUnits(purchase: Purchase) {
    return purchase.items.reduce((sum, item) => sum + Number(item.quantity ?? 0), 0);
  }
  receivedUnits(purchase: Purchase) {
    return purchase.items.reduce((sum, item) => sum + Number(item.received_quantity ?? 0), 0);
  }
  isOverdue(purchase: PurchaseListItem) {
    if (!purchase.needed_by || !['ordered', 'partially_received'].includes(purchase.status))
      return false;
    const today = new Date();
    const todayKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
    return dateOnlyValue(purchase.needed_by) < todayKey;
  }
  availableProducts(stockType: 'product' | 'warehouse') {
    return this.products().filter((product) => product.stock_type === stockType);
  }
  /** Fornecedor pelo nome digitado (o cadastro rápido e o rascunho usam o mesmo atalho). */
  supplierByName(name: string | null | undefined) {
    const key = (name || '').trim().toLowerCase();
    return key
      ? (this.suppliers().find((supplier) => supplier.name.toLowerCase() === key) ?? null)
      : null;
  }
  runAction(request: ReturnType<ApiService['placePurchaseOrder']>) {
    const purchase = this.detail();
    if (!purchase) return;
    this.saving.set(true);
    this.error.set('');
    request.pipe(finalize(() => this.saving.set(false))).subscribe({
      next: (updated) => {
        this.setPurchase(updated);
        if (updated.status === 'received')
          this.api.products('', false, 'product').subscribe((items) => this.products.set(items));
      },
      error: (err) =>
        this.error.set(err.error?.detail || 'Não foi possível atualizar esta compra.'),
    });
  }
  /** Compra atualizada por uma acao: o detalhe recarrega, os blocos se reiniciam e a lista volta. */
  applyUpdate(purchase: Purchase) {
    this.detail.set(purchase);
    this.detailChanged.next(purchase);
    this.changed.next();
  }
  setPurchase(purchase: Purchase) {
    this.applyUpdate(purchase);
  }
}
