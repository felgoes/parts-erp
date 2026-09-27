import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ApiService } from '../../core/api.service';
import { Customer } from '../../core/models';
import { PageHeader } from '../../shared/page-header';

@Component({
  selector: 'app-customers',
  imports: [DatePipe, ReactiveFormsModule, PageHeader],
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
              <tr>
                <td>
                  <strong>{{ c.name }}</strong>
                </td>
                <td>{{ c.document || '—' }}</td>
                <td>
                  <div>{{ c.email || '—' }}</div>
                  <small>{{ c.phone }}</small>
                </td>
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
  `,
  styleUrl: '../products/products.scss',
})
export class CustomersPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  readonly customers = signal<Customer[]>([]);
  readonly search = signal('');
  readonly modal = signal(false);
  readonly filtered = computed(() => {
    const q = this.search().toLowerCase();
    return this.customers().filter(
      (c) => !q || c.name.toLowerCase().includes(q) || (c.document ?? '').includes(q),
    );
  });
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
