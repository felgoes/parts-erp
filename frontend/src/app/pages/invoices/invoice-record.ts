import { CurrencyPipe, DatePipe, DecimalPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { debounceTime, filter, switchMap, tap, catchError, of } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { invoiceDocumentLabel } from '../../core/document-labels';
import { LiveUpdatesService } from '../../core/live-updates.service';
import { Invoice } from '../../core/models';
import { saleStageForInvoice, saleStageLabel } from '../../core/sale-stage';
import { canSell } from '../../core/user-access';
import { AfterSaleWorkflow } from '../../shared/after-sale-workflow';
import { readRecordOrigin } from '../../shared/record-origin';
import { TrackingPanel } from '../../shared/tracking-panel';

const ORIGINS = {
  '/invoices': 'Vendas',
  '/dashboard': 'Visão geral',
  '/marketplace': 'Pedidos online',
  '/notifications': 'Notificações',
};

@Component({
  selector: 'app-invoice-record',
  imports: [AfterSaleWorkflow, CurrencyPipe, DatePipe, DecimalPipe, RouterLink, TrackingPanel],
  templateUrl: './invoice-record.html',
  styleUrl: './invoice-record.scss',
})
export class InvoiceRecord implements OnInit {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly live = inject(LiveUpdatesService);
  private readonly destroyRef = inject(DestroyRef);

  readonly origin = readRecordOrigin(ORIGINS, this.route.snapshot.queryParamMap.get('alerta') === '1' ? '/notifications' : '/invoices');
  readonly invoice = signal<Invoice | null>(null);
  readonly error = signal('');
  readonly confirming = signal(false);
  readonly tab = signal<'items' | 'delivery' | 'documents' | 'after-sale'>('items');
  readonly canConfirm = computed(() => this.invoice()?.status === 'draft' && canSell(this.auth.user()?.role));
  readonly documentLabel = invoiceDocumentLabel;
  readonly status = (invoice: Invoice) => saleStageLabel(saleStageForInvoice(invoice));

  ngOnInit(): void {
    this.route.paramMap.pipe(
      tap(() => {
        this.invoice.set(null);
        this.tab.set('items');
        this.error.set('');
      }),
      switchMap((params) => this.fetch(params.get('id')!)),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe((invoice) => this.invoice.set(invoice));
    this.live.changes$.pipe(
      debounceTime(250),
      filter(() => !!this.invoice()),
      switchMap(() => this.fetch(this.route.snapshot.paramMap.get('id')!)),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe((invoice) => { if (invoice?.id === this.route.snapshot.paramMap.get('id')) this.invoice.set(invoice); });
  }

  private fetch(id: string) {
    return this.api.invoice(id).pipe(catchError((error: HttpErrorResponse) => {
      if ((error.status === 403 || error.status === 404) && this.route.snapshot.queryParamMap.get('alerta') === '1') {
        void this.router.navigate(['/notifications'], { queryParams: { aviso: 'venda-indisponivel' }, replaceUrl: true });
        return of(null);
      }
      this.error.set(error.status === 403 ? 'Você não tem acesso a esta venda.'
        : error.status === 404 ? 'Venda não encontrada.' : 'Não foi possível carregar a venda.');
      return of(null);
    }));
  }

  back(event: MouseEvent): void {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    void this.router.navigateByUrl(this.origin.path, { state: { recordReturn: this.origin } });
  }

  confirm(invoice: Invoice): void {
    if (this.confirming() || !this.canConfirm()) return;
    this.confirming.set(true);
    this.api.confirmInvoice(invoice.id).pipe(
      switchMap(() => this.fetch(invoice.id)),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe({
      next: (updated) => {
        if (updated?.id === this.route.snapshot.paramMap.get('id')) this.invoice.set(updated);
        this.confirming.set(false);
      },
      error: () => {
        this.error.set('Não foi possível confirmar a venda.');
        this.confirming.set(false);
      },
    });
  }
}
