import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { MarketStudiesApi } from '../../core/api/market-studies-api';
import { MarketStudy, MarketStudyCandidate } from '../../core/models';
import { MarketStudyResult } from './market-study-result';
import { decisionLabel } from './market-study-view';

@Component({
  selector: 'app-market-study-detail',
  imports: [DatePipe, DecimalPipe, FormsModule, MarketStudyResult, RouterLink],
  templateUrl: './market-study-detail.html',
  styleUrl: './market-studies.scss',
})
export class MarketStudyDetailPage implements OnInit, OnDestroy {
  private readonly api = inject(MarketStudiesApi);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  readonly study = signal<MarketStudy | null>(null);
  readonly loading = signal(true);
  readonly error = signal('');
  readonly purchaseOpen = signal(false);
  readonly purchase = { sku: '', quantity: 1 };
  readonly purchaseBusy = signal(false);
  readonly message = signal('');
  readonly expanded = signal<Record<string, boolean>>({});
  private pollTimer?: ReturnType<typeof setTimeout>;

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (!id) {
      this.error.set('Estudo não informado.');
      this.loading.set(false);
      return;
    }
    this.loadStudy(id);
  }

  ngOnDestroy(): void {
    if (this.pollTimer) clearTimeout(this.pollTimer);
  }

  private loadStudy(id: string): void {
    this.api
      .marketStudy(id)
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: (study) => {
          this.study.set(study);
          this.purchase.sku = study.result.best_candidate?.sku ?? '';
          if (study.status === 'generating') {
            this.pollTimer = setTimeout(() => this.loadStudy(id), 1800);
          }
        },
        error: () => this.error.set('Estudo não encontrado ou indisponível.'),
      });
  }

  get isOpportunity(): boolean {
    return this.study()?.result.schema_version === 'market_opportunity_result.v1';
  }

  get canCreatePurchase(): boolean {
    return !!this.study()?.result.best_candidate?.sku;
  }

  decisionLabel(value: string | undefined): string {
    return decisionLabel(value);
  }

  toggleCandidate(candidate: MarketStudyCandidate): void {
    this.expanded.update((rows) => ({
      ...rows,
      [candidate.candidate_id]: !rows[candidate.candidate_id],
    }));
  }

  duplicate(): void {
    const study = this.study();
    if (!study) return;
    const scope = study.result.scope;
    void this.router.navigate(['/market-studies/new'], {
      queryParams: scope
        ? {
            mode: scope.mode,
            brand: scope.brand || undefined,
            nationality: scope.nationality || undefined,
          }
        : {},
    });
  }

  backToLibrary(): void {
    const state = sessionStorage.getItem('market-studies-list-state');
    let queryParams: Record<string, string> = {};
    if (state) {
      try {
        const parsed = JSON.parse(state) as {
          tab?: string;
          filters?: Record<string, string>;
          carFilters?: Record<string, string>;
        };
        const values = parsed.tab === 'cars' ? parsed.carFilters : parsed.filters;
        queryParams = { ...(parsed.tab === 'cars' ? { tab: 'cars' } : {}), ...values };
        queryParams = Object.fromEntries(
          Object.entries(queryParams).filter(([, value]) => Boolean(value)),
        );
      } catch {
        queryParams = {};
      }
    }
    void this.router.navigate(['/market-studies'], { queryParams });
  }

  exportStudy(): void {
    const study = this.study();
    if (!study) return;
    const blob = new Blob([JSON.stringify(study, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `estudo-mercado-${study.id}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  createPurchase(): void {
    const study = this.study();
    if (!study || !this.purchase.sku.trim()) return;
    this.purchaseBusy.set(true);
    this.api
      .createPurchaseFromMarketStudy(
        study.id,
        this.purchase.sku.trim(),
        Number(this.purchase.quantity),
      )
      .pipe(finalize(() => this.purchaseBusy.set(false)))
      .subscribe({
        next: (created) => {
          this.message.set('Negociação de compra criada. O estudo não fez nenhum pedido.');
          this.study.update((row) =>
            row ? { ...row, linked_purchase_id: created.id } : row,
          );
          this.purchaseOpen.set(false);
        },
        error: (err: { error?: { detail?: string } }) =>
          this.error.set(err.error?.detail || 'Não foi possível criar a negociação.'),
      });
  }
}
