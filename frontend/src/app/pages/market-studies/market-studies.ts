import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { MarketStudiesApi } from '../../core/api/market-studies-api';
import { AuthService } from '../../core/auth.service';
import { MarketStudySummary } from '../../core/models';
import { PageHeader } from '../../shared/page-header';
import { decisionLabel } from './market-study-view';

@Component({
  selector: 'app-market-studies',
  imports: [DatePipe, FormsModule, PageHeader, RouterLink],
  templateUrl: './market-studies.html',
  styleUrl: './market-studies.scss',
})
export class MarketStudiesPage implements OnInit {
  private readonly api = inject(MarketStudiesApi);
  private readonly router = inject(Router);
  readonly auth = inject(AuthService);
  readonly studies = signal<MarketStudySummary[]>([]);
  readonly total = signal(0);
  readonly loading = signal(true);
  readonly error = signal('');
  readonly filters = { search: '', status: '', decision: '' };

  ngOnInit(): void {
    const params = new URLSearchParams(window.location.search);
    this.filters.search = params.get('search') ?? '';
    this.filters.status = params.get('status') ?? '';
    this.filters.decision = params.get('decision') ?? '';
    this.saveListState();
    this.loadStudies();
  }

  get canRun(): boolean {
    return ['admin', 'manager'].includes(this.auth.user()?.role ?? '');
  }

  loadStudies(): void {
    this.loading.set(true);
    this.error.set('');
    this.api
      .marketStudies({
        search: this.filters.search.trim() || undefined,
        status: this.filters.status || undefined,
        decision: this.filters.decision || undefined,
        limit: 50,
      })
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: (result) => {
          this.studies.set(result.items);
          this.total.set(result.total);
        },
        error: () => this.error.set('Não foi possível carregar a biblioteca de estudos.'),
      });
  }

  applyFilters(): void {
    this.saveListState();
    void this.router.navigate(['/market-studies'], {
      queryParams: Object.fromEntries(
        Object.entries(this.filters).filter(([, value]) => Boolean(value)),
      ),
    });
    this.loadStudies();
  }

  clearFilters(): void {
    this.filters.search = '';
    this.filters.status = '';
    this.filters.decision = '';
    this.applyFilters();
  }

  selectionQuery(study: MarketStudySummary): Record<string, string> {
    return study.brand
      ? { mode: 'brand', brand: study.brand }
      : study.nationality
        ? { mode: 'nationality', nationality: study.nationality }
        : {};
  }

  decisionLabel(value: string | null): string {
    return decisionLabel(value);
  }

  private saveListState(): void {
    sessionStorage.setItem(
      'market-studies-list-state',
      JSON.stringify({ tab: 'studies', filters: this.filters }),
    );
  }
}
