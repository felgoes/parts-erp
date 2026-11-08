import { CurrencyPipe, DatePipe, DecimalPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { createTimeline } from 'animejs/timeline';
import { debounceTime, filter, switchMap, tap, catchError, of } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { invoiceDocumentLabel } from '../../core/document-labels';
import { LiveUpdatesService } from '../../core/live-updates.service';
import { Invoice } from '../../core/models';
import { invoiceProgress } from './invoice-progress';
import { canSell } from '../../core/user-access';
import { AfterSaleWorkflow } from '../../shared/after-sale-workflow';
import { EntryMotion, type EntrySequence } from '../../shared/entry-motion';
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
  imports: [AfterSaleWorkflow, CurrencyPipe, DatePipe, DecimalPipe, EntryMotion, RouterLink, TrackingPanel],
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
  readonly trackingOpen = signal(false);
  readonly afterSaleOpen = signal(false);
  readonly progress = computed(() => {
    const sale = this.invoice();
    return sale ? invoiceProgress(sale) : null;
  });
  readonly labelDocument = computed(() => this.invoice()?.documents.find((doc) => doc.document_type === 'label_pdf'));
  readonly channel = computed(() => {
    const source = this.invoice()?.source;
    return source === 'mercadolivre' ? 'Mercado Livre' : source === 'shopee' ? 'Shopee' : 'Balcão';
  });
  readonly canConfirm = computed(() => this.invoice()?.status === 'draft' && canSell(this.auth.user()?.role));
  readonly documentLabel = invoiceDocumentLabel;

  readonly drawSteps: EntrySequence = (list) => {
    const showFinal = () => list.classList.remove('is-drawing');
    list.classList.add('is-drawing');
    const timeline = createTimeline({ autoplay: false, onComplete: showFinal });
    list.querySelectorAll('li').forEach((step, index) => {
      const badge = step.querySelector<HTMLElement>('.step-check');
      if (!badge) return;
      const stroke = badge.querySelector('path')!;
      const connector = step.querySelector<HTMLElement>('.step-connector');
      const start = 180 + index * 510;
      timeline
        .add(badge, { opacity: [0, 1], scale: [.66, 1], duration: 260, ease: 'outBack(1.5)' }, start)
        .add(stroke, { strokeDashoffset: [1, 0], duration: 210, ease: 'outQuad' }, start + 125);
      if (connector) {
        timeline.add(connector, { scaleX: [0, 1], duration: 300, ease: 'inOutSine' }, start + 210);
      }
    });
    timeline.play();
    return () => {
      timeline.revert();
      showFinal();
    };
  };

  ngOnInit(): void {
    this.route.paramMap.pipe(
      tap(() => {
        this.invoice.set(null);
        this.trackingOpen.set(false);
        this.afterSaleOpen.set(false);
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

  reveal(section: 'tracking' | 'after-sale', record: HTMLElement): void {
    const panel = record.querySelector<HTMLDetailsElement>(section === 'tracking' ? '#sale-tracking' : '#sale-after-sale');
    if (!panel) return;
    panel.open = true;
    (section === 'tracking' ? this.trackingOpen : this.afterSaleOpen).set(true);
    panel.querySelector('summary')?.focus({ preventScroll: true });
    panel.scrollIntoView({ block: 'nearest', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
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
