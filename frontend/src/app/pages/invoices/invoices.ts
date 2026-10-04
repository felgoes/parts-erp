import { CurrencyPipe, DatePipe, UpperCasePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { forkJoin } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { Customer, Invoice, Product } from '../../core/models';
import { PageHeader } from '../../shared/page-header';

@Component({
  selector: 'app-invoices',
  imports: [CurrencyPipe, DatePipe, UpperCasePipe, FormsModule, PageHeader],
  template: `
    <app-page-header
      eyebrow="Comercial"
      title="Faturas de venda"
      subtitle="Do orçamento à baixa de estoque, sem retrabalho."
      ><button class="primary" (click)="openNew()">+ Nova venda</button></app-page-header
    >
    <section class="card table-card">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Fatura</th>
              <th>Origem</th>
              <th>Emissão</th>
              <th>Status</th>
              <th>Documentos</th>
              <th class="right">Total</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            @for (i of invoices(); track i.id) {
              <tr class="clickable-row" (click)="openDetails(i)">
                <td>
                    <button class="link-button" (click)="$event.stopPropagation(); openDetails(i)">{{ i.number }}</button>
                  @if (i.marketplace_order_id) {
                    <small class="block">Pedido #{{ i.marketplace_order_id }}</small>
                  }
                </td>
                <td>{{ i.source === 'mercadolivre' ? 'Mercado Livre' : 'Manual' }}</td>
                <td>{{ i.issued_at || i.created_at | date: 'dd/MM/yyyy HH:mm' }}</td>
                <td>
                  <span class="badge" [class]="i.status">{{ label(i.status) }}</span>
                </td>
                <td>
                  @if (i.documents.length) {
                    @for (doc of i.documents; track doc.id) {
                      <button class="doc" (click)="$event.stopPropagation(); download(i.id, doc.id, doc.filename)">
                        {{ doc.document_type | uppercase }}
                      </button>
                    }
                  } @else {
                    <span class="muted">—</span>
                  }
                </td>
                <td class="right">
                  <strong>{{ i.total | currency: 'BRL' }}</strong>
                </td>
                <td class="right">
                  @if (i.status === 'draft') {
                    <button class="secondary small" (click)="$event.stopPropagation(); confirm(i)">Confirmar</button>
                  }
                </td>
              </tr>
            } @empty {
              <tr>
                <td colspan="7"><div class="empty">Nenhuma fatura registrada.</div></td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    </section>
    @if (modal()) {
      <div class="modal-backdrop" (click)="modal.set(false)">
        <section class="modal wide" (click)="$event.stopPropagation()">
          <div class="modal-head">
            <div>
              <p class="eyebrow">Nova operação</p>
              <h2>Fatura de venda</h2>
            </div>
            <button class="close" (click)="modal.set(false)">×</button>
          </div>
          <label
            >Cliente (opcional)<select [(ngModel)]="customerId">
              <option value="">Consumidor não identificado</option>
              @for (c of customers(); track c.id) {
                <option [value]="c.id">{{ c.name }}</option>
              }
            </select></label
          >
          <div class="line-builder">
            <label
              >Produto<select [(ngModel)]="selectedProduct">
                <option value="">Selecione…</option>
                @for (p of products(); track p.id) {
                  <option [value]="p.id">
                    {{ p.sku }} · {{ p.name }} ({{ p.current_stock }} un.)
                  </option>
                }
              </select></label
            ><label
              >Qtd.<input type="number" min="0.001" step="0.001" [(ngModel)]="quantity" /></label
            ><button class="secondary" (click)="addLine()">Adicionar</button>
          </div>
          <div class="invoice-lines">
            @for (line of lines(); track line.product.id) {
              <div>
                <span
                  ><strong>{{ line.product.name }}</strong
                  ><small
                    >{{ line.quantity }} × {{ line.product.sale_price | currency: 'BRL' }}</small
                  ></span
                ><strong>{{ line.quantity * line.product.sale_price | currency: 'BRL' }}</strong
                ><button class="close" (click)="removeLine(line.product.id)">×</button>
              </div>
            } @empty {
              <div class="empty">Adicione ao menos um produto.</div>
            }
          </div>
          <div class="invoice-total">
            <span>Total</span><strong>{{ total() | currency: 'BRL' }}</strong>
          </div>
          <button class="primary full" [disabled]="!lines().length" (click)="save()">
            Criar fatura em rascunho
          </button>
        </section>
      </div>
    }
    @if (detail(); as invoice) {
      <div class="modal-backdrop" (click)="detail.set(null)">
        <section class="modal wide" (click)="$event.stopPropagation()">
          <div class="modal-head"><div><p class="eyebrow">Fatura {{ invoice.number }}</p><h2>Detalhamento da venda</h2></div><button class="close" (click)="detail.set(null)">×</button></div>
          <nav class="detail-tabs" aria-label="Detalhes da venda"><button [class.active]="invoiceTab() === 'items'" (click)="invoiceTab.set('items')">Itens</button><button [class.active]="invoiceTab() === 'tracking'" (click)="invoiceTab.set('tracking')">Rastreio</button><button [class.active]="invoiceTab() === 'documents'" (click)="invoiceTab.set('documents')">Documentos</button></nav>
          <div class="detail-grid"><div><small>Status atual</small><strong>{{ label(invoice.status) }}</strong></div><div><small>Origem</small><strong>{{ invoice.source === 'mercadolivre' ? 'Mercado Livre' : 'Manual' }}</strong></div><div><small>Pedido</small><strong>{{ invoice.marketplace_order_id || '—' }}</strong></div></div>
          @if (invoiceTab() === 'items') { <h3>Itens vendidos</h3><div class="invoice-detail-lines">@for (item of invoice.items; track item.id) { <div><span><strong>{{ item.description }}</strong><small>{{ item.sku }} · {{ item.quantity }} un.</small></span><strong>{{ item.total | currency:'BRL' }}</strong></div> }</div><div class="invoice-total"><span>Total</span><strong>{{ invoice.total | currency:'BRL' }}</strong></div> }
          @if (invoiceTab() === 'tracking') { @if (invoice.tracking; as tracking) { <div class="detail-grid tracking-grid"><div><small>Status do pedido</small><strong>{{ tracking.status || '—' }}</strong></div><div><small>Status do envio</small><strong>{{ tracking.shipping_status || 'Aguardando atualização' }}</strong></div><div><small>Etiqueta</small><strong>{{ tracking.label_status || '—' }}</strong></div><div><small>ID do envio</small><strong>{{ tracking.shipment_id || '—' }}</strong></div></div><h3>Linha do tempo</h3><div class="timeline">@for (event of tracking.history; track event.created_at + event.status) { <div><strong>{{ event.status }}{{ event.detail ? ' · ' + event.detail : '' }}</strong><span>{{ event.created_at | date:'dd/MM/yyyy HH:mm' }}</span></div> } @empty { <p class="muted">Ainda não há eventos de rastreio registrados.</p> }</div> } @else { <div class="empty">Esta venda não está vinculada a um pedido de marketplace.</div> } }
          @if (invoiceTab() === 'documents') { <h3>Documentos e histórico</h3><p class="muted">Criada em {{ invoice.created_at | date:'dd/MM/yyyy HH:mm' }}{{ invoice.issued_at ? ' · Emitida em ' + (invoice.issued_at | date:'dd/MM/yyyy HH:mm') : '' }}</p>@if (invoice.documents.length) { @for (doc of invoice.documents; track doc.id) { <button class="doc" (click)="download(invoice.id, doc.id, doc.filename)">{{ doc.document_type | uppercase }} · {{ doc.filename }}</button> } } @else { <p class="muted">Nenhum documento anexado ainda.</p> } }
        </section>
      </div>
    }
  `,
  styleUrl: './invoices.scss',
})
export class InvoicesPage implements OnInit {
  private readonly api = inject(ApiService);
  readonly invoices = signal<Invoice[]>([]);
  readonly products = signal<Product[]>([]);
  readonly customers = signal<Customer[]>([]);
  readonly modal = signal(false);
  readonly detail = signal<Invoice | null>(null);
  readonly invoiceTab = signal<'items' | 'tracking' | 'documents'>('items');
  readonly lines = signal<{ product: Product; quantity: number }[]>([]);
  customerId = '';
  selectedProduct = '';
  quantity = 1;
  ngOnInit() {
    this.load();
  }
  load() {
    this.api.invoices().subscribe((v) => this.invoices.set(v));
  }
  openNew() {
    forkJoin([this.api.products(), this.api.customers()]).subscribe(([p, c]) => {
      this.products.set(p);
      this.customers.set(c);
      this.lines.set([]);
      this.modal.set(true);
    });
  }
  addLine() {
    const p = this.products().find((x) => x.id === this.selectedProduct);
    if (!p || this.quantity <= 0) return;
    this.lines.update((lines) => [
      ...lines.filter((x) => x.product.id !== p.id),
      { product: p, quantity: this.quantity },
    ]);
    this.selectedProduct = '';
    this.quantity = 1;
  }
  removeLine(id: string) {
    this.lines.update((v) => v.filter((x) => x.product.id !== id));
  }
  total() {
    return this.lines().reduce((sum, x) => sum + x.quantity * x.product.sale_price, 0);
  }
  save() {
    this.api
      .createInvoice({
        customer_id: this.customerId || null,
        items: this.lines().map((x) => ({ product_id: x.product.id, quantity: x.quantity })),
      })
      .subscribe(() => {
        this.modal.set(false);
        this.load();
      });
  }
  confirm(i: Invoice) {
    this.api.confirmInvoice(i.id).subscribe(() => this.load());
  }
  openDetails(i: Invoice) {
    this.invoiceTab.set('items');
    this.api.invoice(i.id).subscribe((full) => this.detail.set(full));
  }
  download(invoiceId: string, documentId: string, filename: string) {
    this.api.downloadInvoiceDocument(invoiceId, documentId).subscribe((blob) => {
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      URL.revokeObjectURL(url);
    });
  }
  label(s: string) {
    return (
      (
        { draft: 'Rascunho', confirmed: 'Confirmada', cancelled: 'Cancelada' } as Record<
          string,
          string
        >
      )[s] ?? s
    );
  }
}
