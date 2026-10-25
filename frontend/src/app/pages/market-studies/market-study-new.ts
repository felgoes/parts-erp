import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { MarketStudiesApi } from '../../core/api/market-studies-api';
import { PageHeader } from '../../shared/page-header';

@Component({
  selector: 'app-market-study-new',
  imports: [FormsModule, PageHeader, RouterLink],
  templateUrl: './market-study-new.html',
  styleUrl: './market-studies.scss',
})
export class MarketStudyNewPage implements OnInit {
  private readonly api = inject(MarketStudiesApi);
  private readonly router = inject(Router);
  readonly form = {
    mode: 'brand' as 'brand' | 'nationality',
    selection: '',
    region: '',
    category: '',
    includeSuppliersChina: false,
  };
  readonly loading = signal(false);
  readonly error = signal('');
  readonly brandNationalities = signal<Record<string, string>>({});
  readonly missingCompanyFields = signal<string[]>([]);
  readonly profileVersion = signal<number | null>(null);

  ngOnInit(): void {
    const params = new URLSearchParams(window.location.search);
    const mode = params.get('mode');
    if (mode === 'nationality') this.form.mode = 'nationality';
    this.form.selection = params.get(mode === 'nationality' ? 'nationality' : 'brand') ?? '';
    this.api.vehicleMarket().subscribe({
      next: (overview) => this.brandNationalities.set(overview.brand_nationalities),
    });
    this.api.marketStudyDefaults().subscribe({
      next: (defaults) => {
        this.missingCompanyFields.set(defaults.missing_company_fields);
        this.profileVersion.set(defaults.profile_version);
      },
    });
  }

  get brandOptions(): string[] {
    return Object.keys(this.brandNationalities()).sort();
  }

  get nationalityOptions(): string[] {
    return [...new Set(Object.values(this.brandNationalities()))].sort();
  }

  get derivedNationality(): string | null {
    return this.form.mode === 'brand'
      ? (this.brandNationalities()[this.form.selection] ?? null)
      : this.form.selection || null;
  }

  setMode(mode: 'brand' | 'nationality'): void {
    this.form.mode = mode;
    this.form.selection = '';
  }

  submit(): void {
    if (!this.form.selection) {
      this.error.set(
        this.form.mode === 'brand' ? 'Escolha uma marca.' : 'Escolha uma nacionalidade.',
      );
      return;
    }
    this.loading.set(true);
    this.error.set('');
    this.api
      .createMarketStudy({
        mode: this.form.mode,
        brand: this.form.mode === 'brand' ? this.form.selection : undefined,
        nationality:
          this.form.mode === 'nationality' ? this.form.selection : undefined,
        region: this.form.region.trim() || undefined,
        vehicle_categories: this.form.category ? [this.form.category] : undefined,
        include_suppliers_china: this.form.includeSuppliersChina,
        include_competitor_links: true,
      })
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: (study) => void this.router.navigate(['/market-studies', study.id]),
        error: (err: { error?: { detail?: string } }) => {
          this.error.set(
            err.error?.detail ||
              'Não foi possível gerar o estudo. Sua seleção foi mantida para nova tentativa.',
          );
        },
      });
  }
}
