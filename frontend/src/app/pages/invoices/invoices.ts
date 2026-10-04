import { CurrencyPipe, DatePipe, UpperCasePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { forkJoin } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { Customer, Invoice, Product } from '../../core/models';
import { statusLabel, trackingEventLabel } from '../../core/status-labels';
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
              <th>Cliente</th>
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
                <td class="customer-cell">
                  <strong>{{ i.customer?.name || 'Consumidor não identificado' }}</strong>
                  <small>{{ i.customer?.document || i.customer?.email || 'Sem cadastro vinculado' }}</small>
                </td>
                <td>{{ i.source === 'mercadolivre' ? 'Mercado Livre' : 'Manual' }}</td>
                <td>{{ i.issued_at || i.created_at | date: 'dd/MM/yyyy HH:mm' }}</td>
                <td>
                  <span class="badge" [class]="i.status">{{ label(i.status) }}</span>
                </td>
                <td>
                  @if (i.documents.length) {
                    @for (doc of i.documents; track doc.id) {
                      <button class="doc" (click)="$event.stopPropagation(); openDocument(i.id, doc.id)">
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
                <td colspan="8"><div class="empty">Nenhuma fatura registrada.</div></td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    </section>
    @if (modal()) {
      <div class="modal-backdrop" (click)="modal.set(false)">
        <section class="modal wide object-modal" (click)="$event.stopPropagation()">
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
        <section class="modal wide object-modal" (click)="$event.stopPropagation()">
          <div class="modal-head detail-hero"><div><p class="eyebrow">Venda {{ invoice.source === 'mercadolivre' ? 'Mercado Livre' : 'manual' }}</p><h2>{{ invoice.number }}</h2><p class="detail-subtitle">Criada em {{ invoice.created_at | date:'dd/MM/yyyy HH:mm' }}{{ invoice.issued_at ? ' · emitida em ' + (invoice.issued_at | date:'dd/MM/yyyy HH:mm') : '' }}</p></div><div class="hero-actions"><span class="badge" [class]="invoice.status">{{ label(invoice.status) }}</span><button class="close" aria-label="Fechar detalhe" (click)="detail.set(null)">×</button></div></div>
          <div class="detail-summary"><div><span>Cliente</span><strong>{{ invoice.customer?.name || 'Consumidor não identificado' }}</strong><small>{{ invoice.customer?.document || invoice.customer?.email || 'Sem cadastro vinculado' }}</small></div><div><span>Pedido relacionado</span><strong>{{ invoice.marketplace_order_id ? '#' + invoice.marketplace_order_id : 'Venda local' }}</strong><small>{{ invoice.items.length }} item(ns) · {{ invoice.total | currency:'BRL' }}</small></div></div>
          <nav class="detail-tabs" aria-label="Detalhes da venda"><button [class.active]="invoiceTab() === 'items'" (click)="invoiceTab.set('items')">Itens <small>{{ invoice.items.length }}</small></button><button [class.active]="invoiceTab() === 'tracking'" (click)="invoiceTab.set('tracking')">Rastreio</button><button [class.active]="invoiceTab() === 'documents'" (click)="invoiceTab.set('documents')">Documentos <small>{{ invoice.documents.length }}</small></button></nav>
          @if (invoiceTab() === 'items') { <section class="detail-section"><div class="section-heading"><div><p class="eyebrow">Composição</p><h3>Itens vendidos</h3></div><strong>{{ invoice.total | currency:'BRL' }}</strong></div><div class="invoice-detail-lines">@for (item of invoice.items; track item.id) { <div><span class="item-main"><strong>{{ item.description }}</strong><small>SKU {{ item.sku }} · {{ item.quantity }} unidade(s) · {{ item.unit_price | currency:'BRL' }} cada</small></span><strong>{{ item.total | currency:'BRL' }}</strong></div> }</div></section> }
          @if (invoiceTab() === 'tracking') { <section class="detail-section">@if (invoice.tracking; as tracking) { <div class="tracking-cards"><div><span>Status do pedido</span><strong>{{ statusLabel(tracking.status) }}</strong></div><div><span>Envio</span><strong>{{ statusLabel(tracking.shipping_status) }}</strong></div><div><span>Etiqueta</span><strong>{{ statusLabel(tracking.label_status) }}</strong></div><div><span>Código de rastreio</span><strong>{{ tracking.shipment_id || '—' }}</strong></div></div><div class="section-heading"><div><p class="eyebrow">Mercado Envios</p><h3>Linha do tempo do rastreio</h3></div><small>{{ tracking.last_update ? ('Atualizado ' + (tracking.last_update | date:'dd/MM/yyyy HH:mm')) : '' }}</small></div><div class="timeline">@for (event of tracking.history; track event.created_at + event.status) { <div><strong>{{ trackingEventLabel(event.status, event.detail) }}</strong><span>{{ event.created_at | date:'dd/MM/yyyy HH:mm' }}</span></div> } @empty { <p class="muted">Ainda não há eventos de rastreio registrados.</p> }</div> } @else { <div class="empty">Esta venda não está vinculada a um pedido de marketplace.</div> }</section> }
          @if (invoiceTab() === 'documents') { <section class="detail-section"><div class="section-heading"><div><p class="eyebrow">Fiscal</p><h3>Documentos da venda</h3></div><span class="muted">Clique para abrir em nova guia</span></div>@if (invoice.documents.length) { <div class="document-list">@for (doc of invoice.documents; track doc.id) { <button class="document-card" (click)="openDocument(invoice.id, doc.id)"><span class="document-icon">{{ doc.document_type === 'pdf' ? 'PDF' : 'XML' }}</span><span><strong>{{ doc.filename }}</strong><small>{{ doc.document_type === 'pdf' ? 'DANFE para visualização' : 'Nota fiscal eletrônica' }}</small></span><b>↗</b></button> }</div> } @else { <div class="empty">Nenhum documento anexado ainda.</div> }</section> }
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
  readonly statusLabel = statusLabel;
  readonly trackingEventLabel = trackingEventLabel;
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
  openDocument(invoiceId: string, documentId: string) {
    this.api.downloadInvoiceDocument(invoiceId, documentId).subscribe((blob) => {
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank', 'noopener,noreferrer');
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    });
  }
  label(s: string) {
    return ({ draft: 'Rascunho', confirmed: 'Confirmada', cancelled: 'Cancelada' } as Record<string, string>)[s] ?? statusLabel(s);
  }
}
