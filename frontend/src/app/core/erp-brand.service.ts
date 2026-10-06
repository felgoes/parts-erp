import { Injectable, inject, signal } from '@angular/core';
import { ApiService } from './api.service';
import { ErpSettings } from './models';

@Injectable({ providedIn: 'root' })
export class ErpBrandService {
  private readonly api = inject(ApiService);
  readonly shortName = signal('Parts');
  readonly suffix = signal('ERP');
  readonly logo = signal<string | null>(null);

  load(): void {
    this.api.erpSettings().subscribe({ next: (settings) => this.apply(settings) });
  }

  apply(settings: ErpSettings): void {
    this.shortName.set(settings.company_short_name || 'Parts');
    this.suffix.set(settings.company_name.replace(settings.company_short_name, '').trim() || 'ERP');
    this.logo.set(settings.logo_data_url);
  }
}
