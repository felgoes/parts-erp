import { CurrencyPipe } from '@angular/common';
import { Component, inject, input, output, signal } from '@angular/core';
import { finalize } from 'rxjs';

import { ApiService } from '../../core/api.service';
import { Purchase } from '../../core/models';

/**
 * Confirmação da exclusão de uma compra.
 *
 * Recebe a compra já carregada por inteiro (o aviso lista o que será apagado, inclusive o título
 * a pagar) e devolve para a página só o identificador excluído: quem atualiza a lista é a página.
 */
@Component({
  selector: 'app-purchase-delete',
  imports: [CurrencyPipe],
  templateUrl: './purchase-delete.html',
  styleUrl: './purchase-delete.scss',
})
export class PurchaseDelete {
  private readonly api = inject(ApiService);

  readonly purchase = input<Purchase | null>(null);
  readonly deleted = output<string>();
  readonly closed = output<void>();

  readonly reason = signal('');
  readonly saving = signal(false);
  readonly error = signal('');

  purchaseTotal(purchase: Purchase) {
    return purchase.purchase_type === 'expense'
      ? (purchase.expense_amount ?? 0)
      : (purchase.total_amount ?? 0);
  }

  cancelDelete() {
    this.closed.emit();
  }

  deleteBlockedByPayment(purchase: Purchase) {
    return (purchase.payables ?? []).some(
      (payable) => payable.status !== 'cancelled' && (payable.paid_amount ?? 0) > 0,
    );
  }

  deletionEffects(purchase: Purchase) {
    const effects: string[] = [`${purchase.items.length} item(ns) do pedido`];
    if (purchase.quotes.length)
      effects.push(`${purchase.quotes.length} cotação(ões) registrada(s)`);
    if (purchase.attachments.length)
      effects.push(`${purchase.attachments.length} anexo(s), inclusive o arquivo armazenado`);
    const received = purchase.items.filter(
      (item) => item.received_quantity - (item.returned_quantity ?? 0) > 0,
    );
    if (received.length) {
      const quantity = received.reduce(
        (sum, item) => sum + item.received_quantity - (item.returned_quantity ?? 0),
        0,
      );
      effects.push(
        `estorno de ${quantity} unidade(s) recebida(s) no estoque, com movimentação rastreável`,
      );
    }
    const payable = (purchase.payables ?? []).find((entry) => entry.status !== 'cancelled');
    if (payable)
      effects.push(
        `título a pagar de ${Number(payable.amount).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}`,
      );
    if (purchase.events.length)
      effects.push(`${purchase.events.length} evento(s) do histórico do pedido`);
    return effects;
  }

  confirmDelete(purchase: Purchase) {
    if (this.saving() || this.deleteBlockedByPayment(purchase)) return;
    this.saving.set(true);
    this.error.set('');
    const reason = this.reason().trim();
    this.api
      .deletePurchase(purchase.id, reason || undefined)
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe({
        next: () => this.deleted.emit(purchase.id),
        error: (err) => this.error.set(err.error?.detail || 'Não foi possível excluir a compra.'),
      });
  }
}
