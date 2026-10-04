import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ApiService } from '../../core/api.service';
import { Customer, CustomerDetail } from '../../core/models';
import { statusLabel } from '../../core/status-labels';
import { PageHeader } from '../../shared/page-header';

@Component({
  selector: 'app-customers',
  imports: [CurrencyPipe, DatePipe, ReactiveFormsModule, PageHeader],
  template: `
    <app-page-header
      eyebrow="Relacionamento"
      title="Clientes"
      subtitle="Dados essenciais para vendas e faturamento."
      ><button class="primary" (click)="modal.set(true)">+ Novo cliente</button></app-page-header
    >
    <div class="toolbar">
      <div class="search">
        <span>⌕</span
        ><input
          placeholder="Buscar cliente…"
          [value]="search()"
          (input)="search.set($any($event.target).value)"
        />
      </div>
      <span class="count">{{ filtered().length }} clientes</span>
    </div>
    <section class="card table-card">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Cliente</th>
              <th>Documento</th>
              <th>Contato</th>
              <th>Desde</th>
            </tr>
          </thead>
          <tbody>
            @for (c of filtered(); track c.id) {
              <tr class="clickable-row" (click)="openDetails(c)">
                <td><button class="customer-link" type="button" [attr.aria-label]="'Abrir cliente ' + c.name" (click)="$event.stopPropagation(); openDetails(c)"><span class="customer-avatar">{{ c.name.charAt(0) }}</span><span class="customer-main"><strong>{{ c.name }}</strong><small>{{ c.email || 'Cliente cadastrado' }}</small></span><span class="customer-chevron" aria-hidden="true">›</span></button></td>
                <td>{{ c.document || '—' }}</td>
                <td><span class="contact-main">{{ c.phone || 'Sem telefone' }}</span><small>{{ c.email || 'Sem e-mail' }}</small></td>
                <td>{{ c.created_at | date: 'dd/MM/yyyy' }}</td>
              </tr>
            } @empty {
              <tr>
                <td colspan="4"><div class="empty">Nenhum cliente cadastrado.</div></td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    </section>
    @if (modal()) {
      <div class="modal-backdrop" (click)="modal.set(false)">
        <section class="modal" (click)="$event.stopPropagation()">
          <div class="modal-head">
            <div>
              <p class="eyebrow">Relacionamento</p>
              <h2>Novo cliente</h2>
            </div>
            <button class="close" (click)="modal.set(false)">×</button>
          </div>
          <form [formGroup]="form" (ngSubmit)="save()">
            <label>Nome<input formControlName="name" /></label>
            <div class="form-grid">
              <label>CPF ou CNPJ<input formControlName="document" /></label
              ><label>Telefone<input formControlName="phone" /></label
              ><label class="span-2">E-mail<input type="email" formControlName="email" /></label>
            </div>
            <button class="primary full" [disabled]="form.invalid">Cadastrar cliente</button>
          </form>
        </section>
      </div>
    }
    @if (detail(); as customer) {
      <div class="modal-backdrop" (click)="detail.set(null)">
        <section class="modal wide object-modal" (click)="$event.stopPropagation()">
          <div class="modal-head customer-detail-head"><div class="customer-detail-title"><span class="detail-avatar">{{ customer.name.charAt(0) }}</span><div><p class="eyebrow">Relacionamento · Cliente</p><h2>{{ customer.name }}</h2><p class="detail-subtitle">{{ customer.email || 'Sem e-mail' }} · {{ customer.phone || 'Sem telefone' }}</p></div></div><button class="close" aria-label="Fechar cliente" (click)="detail.set(null)">×</button></div>
          <div class="detail-grid customer-metrics"><div><small>Total comprado</small><strong>{{ customer.total_purchased | currency:'BRL' }}</strong></div><div><small>Compras</small><strong>{{ customer.purchase_count }}</strong></div><div><small>Ticket médio</small><strong>{{ customer.average_purchase | currency:'BRL' }}</strong></div><div><small>Pedidos Mercado Livre</small><strong>{{ customer.marketplace_order_count }}</strong></div><div><small>Cancelados</small><strong>{{ customer.cancelled_order_count }}</strong></div><div><small>Última compra</small><strong>{{ customer.last_purchase_at ? (customer.last_purchase_at | date:'dd/MM/yyyy HH:mm') : '—' }}</strong></div></div>
          <div class="object-section-heading"><div><p class="eyebrow">Atividade comercial</p><h3>Histórico de compras</h3></div><span class="muted">{{ customer.purchases.length }} registro(s)</span></div><div class="movement-list customer-purchases">@for (purchase of customer.purchases; track purchase.id) { <div><span>{{ purchase.created_at | date:'dd/MM/yyyy HH:mm' }}</span><strong>{{ purchase.number }}</strong><span>{{ purchase.source === 'mercadolivre' ? 'Mercado Livre' : 'Venda manual' }} · {{ statusLabel(purchase.status) }}</span><small>{{ purchase.item_count }} item(ns) · {{ purchase.total | currency:'BRL' }}</small></div> } @empty { <p class="muted">Nenhuma compra registrada.</p> }</div>
        </section>
      </div>
    }
  `,
  styleUrl: './customers.scss',
})
export class CustomersPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  readonly customers = signal<Customer[]>([]);
  readonly search = signal('');
  readonly modal = signal(false);
  readonly detail = signal<CustomerDetail | null>(null);
  readonly filtered = computed(() => {
    const q = this.search().toLowerCase();
    return this.customers().filter(
      (c) => !q || c.name.toLowerCase().includes(q) || (c.document ?? '').includes(q),
    );
  });
  readonly statusLabel = statusLabel;
  readonly form = this.fb.nonNullable.group({
    name: ['', Validators.required],
    document: [''],
    phone: [''],
    email: ['', Validators.email],
  });
  ngOnInit() {
    this.load();
  }
  load() {
    this.api.customers().subscribe((v) => this.customers.set(v));
  }
  openDetails(customer: Customer) {
    this.detail.set(null);
    this.api.customerDetail(customer.id).subscribe((v) => this.detail.set(v));
  }
  save() {
    if (this.form.invalid) return;
    const raw = this.form.getRawValue();
    this.api
      .createCustomer({
        name: raw.name,
        document: raw.document || null,
        phone: raw.phone || null,
        email: raw.email || null,
      })
      .subscribe(() => {
        this.modal.set(false);
        this.form.reset();
        this.load();
      });
  }
}
