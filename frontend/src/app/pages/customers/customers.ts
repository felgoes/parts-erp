import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { debounceTime } from 'rxjs';
import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ApiService } from '../../core/api.service';
import { LiveUpdatesService } from '../../core/live-updates.service';
import { AuthService } from '../../core/auth.service';
import { Customer, CustomerDetail } from '../../core/models';
import { canSell } from '../../core/user-access';
import { statusLabel } from '../../core/status-labels';
import { PageHeader } from '../../shared/page-header';

@Component({
  selector: 'app-customers',
  imports: [CurrencyPipe, DatePipe, ReactiveFormsModule, PageHeader],
  templateUrl: './customers.html',
  styleUrl: './customers.scss',
})
export class CustomersPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly live = inject(LiveUpdatesService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly auth = inject(AuthService);
  canSell() { return canSell(this.auth.user()?.role); }
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
    this.live.changes$.pipe(debounceTime(250), takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.load();
      const id = this.detail()?.id;
      if (id) this.api.customerDetail(id).subscribe((value) => { if (this.detail()?.id === id) this.detail.set(value); });
    });
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
