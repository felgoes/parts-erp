import { CurrencyPipe, DatePipe, DecimalPipe, LowerCasePipe } from '@angular/common';
import { Component, Input, OnChanges, SimpleChanges, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../core/api.service';
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
  template: `
    @if (afterSale; as summary) {
      <section class="detail-section after-sale-workflow">
        <div class="section-heading">
          <div>
            <p class="eyebrow">Acompanhamento</p>
            <h3>{{ summary.kind === 'return' ? 'Devolução' : summary.kind === 'claim' ? 'Reclamação' : 'Cancelamento' }}</h3>
          </div>
          <span class="badge cancelled">{{ statusLabel(summary.status) }}</span>
        </div>
        <div class="after-sale-cards">
          <div><span>Status no Mercado Livre</span><strong>{{ statusLabel(summary.status) }}</strong></div>
          @if (summary.reason) { <div><span>Motivo</span><strong>{{ summary.reason }}</strong></div> }
          @if (summary.requested_by) { <div><span>Solicitado por</span><strong>{{ requesterLabel(summary.requested_by) }}</strong></div> }
          @if (summary.payment_status) { <div><span>Pagamento</span><strong>{{ statusLabel(summary.payment_status) }}</strong></div> }
          @if (summary.refund_amount !== null) { <div><span>Valor reembolsado</span><strong>{{ summary.refund_amount | currency:'BRL' }}</strong></div> }
          @if (summary.return_id) { <div><span>Protocolo</span><strong>{{ summary.return_id }}</strong></div> }
        </div>

        @for (caseRecord of cases(); track caseRecord.id) {
          <section class="return-case" [class.is-resolved]="caseRecord.workflow_status === 'resolved'">
            <div class="section-heading return-case-heading">
              <div><p class="eyebrow">{{ caseRecord.kind === 'return' ? 'Devolução Mercado Livre' : 'Reclamação Mercado Livre' }} · #{{ caseRecord.external_case_id }}</p><h4>{{ workflowLabel(caseRecord.workflow_status) }}</h4></div>
              @if (caseRecord.completed_at) { <small>Encerrada em {{ caseRecord.completed_at | date:'dd/MM/yyyy HH:mm' }}</small> }
            </div>
            <p class="return-guidance">O pedido do cliente não altera o estoque sozinho. Registre o recebimento físico e inspecione cada peça; só unidades aprovadas para revenda entram no saldo.</p>

            @for (item of caseRecord.items; track item.id) {
              <article class="return-item">
                <div class="return-item-title"><div><strong>{{ item.description }}</strong><small>SKU {{ item.sku }} · limite do pedido {{ item.requested_quantity | number:'1.0-3' }} un.</small></div><span class="badge" [class.success]="item.disposition === 'restock'">{{ item.disposition === 'pending' ? 'Aguardando conferência' : statusLabel(item.disposition) }}</span></div>
                <div class="return-quantities"><div><small>Recebidas</small><strong>{{ item.received_quantity | number:'1.0-3' }} un.</strong></div><div><small>Inspecionadas</small><strong>{{ item.inspected_quantity | number:'1.0-3' }} un.</strong></div><div><small>Devolvidas ao estoque</small><strong>{{ item.restocked_quantity | number:'1.0-3' }} un.</strong></div></div>
                @if (caseRecord.workflow_status !== 'resolved') {
                  <div class="return-actions">
                    @if (item.received_quantity < item.requested_quantity) {
                      <label>Recebida fisicamente (total acumulado)<input type="number" min="{{ item.received_quantity }}" max="{{ item.requested_quantity }}" step="0.001" [ngModel]="formFor(item).received" (ngModelChange)="setForm(item.id, 'received', $event)" /></label>
                      <button class="secondary small" [disabled]="busy() === item.id + ':receive'" (click)="receive(caseRecord, item)">{{ busy() === item.id + ':receive' ? 'Salvando…' : 'Registrar recebimento' }}</button>
                    }
                    @if (item.received_quantity > item.inspected_quantity) {
                      <label>Unidades aptas para revenda<input type="number" min="{{ item.restocked_quantity }}" max="{{ item.received_quantity }}" step="0.001" [ngModel]="formFor(item).restock" (ngModelChange)="setForm(item.id, 'restock', $event)" /></label>
                      <label>Condição<select [ngModel]="formFor(item).disposition" (ngModelChange)="setForm(item.id, 'disposition', $event)"><option value="restock">Todas aptas para revenda</option><option value="mixed">Parte apta, parte sem condição de revenda</option><option value="damaged">Danificada</option><option value="discarded">Descarte</option></select></label>
                      <label class="return-notes">Observação da inspeção<input [ngModel]="formFor(item).notes" (ngModelChange)="setForm(item.id, 'notes', $event)" placeholder="Ex.: embalagem aberta, peça sem uso" /></label>
                      <button class="primary small" [disabled]="busy() === item.id + ':inspect'" (click)="inspect(caseRecord, item)">{{ busy() === item.id + ':inspect' ? 'Atualizando…' : 'Inspecionar e atualizar estoque' }}</button>
                    }
                  </div>
                } @else {
                  <p class="return-outcome">{{ item.restocked_quantity | number:'1.0-3' }} unidade(s) reintegrada(s) ao estoque. O restante foi registrado como {{ statusLabel(item.disposition) | lowercase }}.</p>
                }
                @if (item.notes) { <small class="return-item-notes">{{ item.notes }}</small> }
              </article>
            } @empty {
              <p class="muted">A devolução ainda não trouxe itens conciliáveis. Confira o pedido no Mercado Livre antes de registrar entrada de estoque.</p>
            }
            @if (caseRecord.workflow_status !== 'resolved' && canCloseWithoutStock(caseRecord)) {
              <button class="secondary small close-return" [disabled]="busy() === caseRecord.id + ':close'" (click)="closeWithoutStock(caseRecord)">{{ hasReceivedItems(caseRecord) ? 'Encerrar sem outras peças recebidas' : 'Encerrar sem retorno físico da peça' }}</button>
            }
            @if (caseRecord.events.length) {
              <div class="return-history"><p class="eyebrow">Histórico do caso</p><div class="timeline">@for (event of caseRecord.events; track event.event_type + event.status + event.created_at) { <div><strong>{{ statusLabel(event.status) }}{{ event.detail ? ' · ' + event.detail : '' }}</strong><span>{{ event.created_at | date:'dd/MM/yyyy HH:mm' }}</span></div> }</div></div>
            }
          </section>
        } @empty {
          <div class="return-empty">O Mercado Livre registrou o pós-venda, mas o caso ainda não foi estruturado para operação de estoque. Sincronize a notificação de devolução para criar o processo vinculado.</div>
        }
        @if (summary.history.length) {
          <div class="return-history"><p class="eyebrow">Etapas recebidas do Mercado Livre</p><div class="timeline">@for (event of summary.history; track event.created_at + event.status) { <div><strong>{{ statusLabel(event.status) }}{{ event.detail ? ' · ' + event.detail : '' }}</strong><span>{{ event.created_at | date:'dd/MM/yyyy HH:mm' }}</span></div> }</div></div>
        }
        @if (message()) { <p class="return-message" [class.error]="messageIsError()">{{ message() }}</p> }
      </section>
    }
  `,
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
