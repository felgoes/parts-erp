import { CurrencyPipe, DatePipe, DecimalPipe, LowerCasePipe } from '@angular/common';
import { Component, Input, OnChanges, SimpleChanges, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { AfterSaleCase, AfterSaleCaseItem, InvoiceAfterSale } from '../core/models';
import { statusLabel } from '../core/status-labels';

type InspectionDisposition = 'restock' | 'mixed' | 'damaged' | 'discarded';
interface ReturnItemForm {
  received: number;
  restock: number;
  disposition: InspectionDisposition;
  notes: string;
}

@Component({
  selector: 'app-after-sale-workflow',
  imports: [CurrencyPipe, DatePipe, DecimalPipe, FormsModule, LowerCasePipe],
  templateUrl: './after-sale-workflow.html',
  styleUrl: './after-sale-workflow.scss',
})
export class AfterSaleWorkflow implements OnChanges {
  @Input() afterSale: InvoiceAfterSale | null = null;
  readonly cases = signal<AfterSaleCase[]>([]);
  readonly values = signal<Record<string, ReturnItemForm>>({});
  readonly busy = signal('');
  readonly message = signal('');
  readonly messageIsError = signal(false);
  readonly statusLabel = statusLabel;
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);

  canProcess() {
    const role = this.auth.user()?.role;
    return role === 'admin' || role === 'manager' || role === 'stock';
  }

  canClose() {
    const role = this.auth.user()?.role;
    return role === 'admin' || role === 'manager';
  }

  ngOnChanges(_changes: SimpleChanges) {
    this.cases.set(this.afterSale?.cases ?? []);
    this.values.set({});
    this.message.set('');
  }

  formFor(item: AfterSaleCaseItem): ReturnItemForm {
    return this.values()[item.id] ?? {
      received: item.received_quantity,
      restock: item.restocked_quantity,
      disposition: item.disposition === 'pending' ? 'restock' : item.disposition as InspectionDisposition,
      notes: item.notes ?? '',
    };
  }

  setForm<K extends keyof ReturnItemForm>(itemId: string, key: K, value: ReturnItemForm[K]) {
    const item = this.cases().flatMap((record) => record.items).find((row) => row.id === itemId);
    const initial: ReturnItemForm = item ? this.formFor(item) : { received: 0, restock: 0, disposition: 'restock', notes: '' };
    this.values.update((all) => ({ ...all, [itemId]: { ...initial, [key]: value } }));
  }

  workflowLabel(status: string) {
    return ({
      requested: 'Devolução solicitada',
      partially_received: 'Recebimento parcial',
      inspection_pending: 'Aguardando inspeção',
      resolved: 'Pós-venda concluído',
      cancelled: 'Caso cancelado',
    } as Record<string, string>)[status] ?? statusLabel(status);
  }

  requesterLabel(value: string) {
    return ({ meli: 'Mercado Livre', buyer: 'Comprador', seller: 'Vendedor' } as Record<string, string>)[value.toLowerCase()] ?? value;
  }

  canCloseWithoutStock(record: AfterSaleCase) {
    return record.items.every((item) => item.received_quantity <= item.inspected_quantity);
  }

  hasReceivedItems(record: AfterSaleCase) {
    return record.items.some((item) => item.received_quantity > 0);
  }

  receive(record: AfterSaleCase, item: AfterSaleCaseItem) {
    const quantity = Number(this.formFor(item).received);
    this.run(record, `${item.id}:receive`, this.api.receiveAfterSale(record.id, [
      { item_id: item.id, received_quantity: quantity },
    ]), 'Recebimento registrado. A peça ainda não voltou ao estoque: falta inspecioná-la.');
  }

  inspect(record: AfterSaleCase, item: AfterSaleCaseItem) {
    const form = this.formFor(item);
    this.run(record, `${item.id}:inspect`, this.api.inspectAfterSale(record.id, [
      {
        item_id: item.id,
        restock_quantity: Number(form.restock),
        disposition: form.disposition,
        notes: form.notes || undefined,
      },
    ]), 'Inspeção registrada e saldo de estoque atualizado.');
  }

  closeWithoutStock(record: AfterSaleCase) {
    this.run(record, `${record.id}:close`, this.api.closeAfterSaleWithoutStock(
      record.id,
      'Caso encerrado no marketplace sem retorno físico da peça.',
    ), 'Pós-venda encerrado sem movimentar o estoque.');
  }

  private run(record: AfterSaleCase, busyKey: string, request: ReturnType<ApiService['receiveAfterSale']>, success: string) {
    this.busy.set(busyKey);
    this.message.set('');
    request.subscribe({
      next: (updated) => {
        this.cases.update((current) => current.map((item) => item.id === record.id ? updated : item));
        this.busy.set('');
        this.messageIsError.set(false);
        this.message.set(success);
      },
      error: (error: { error?: { detail?: string } }) => {
        this.busy.set('');
        this.messageIsError.set(true);
        this.message.set(error.error?.detail ?? 'Não foi possível atualizar o pós-venda. Tente novamente.');
      },
    });
  }
}
