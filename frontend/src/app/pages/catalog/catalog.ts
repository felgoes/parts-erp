import { CurrencyPipe, KeyValuePipe } from '@angular/common';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { apiUrl } from '../../core/api-url';
import { CatalogProduct } from '../../core/models';

@Component({
  selector: 'app-catalog',
  imports: [CurrencyPipe, FormsModule, KeyValuePipe],
  templateUrl: './catalog.html',
  styleUrl: './catalog.scss',
})
export class CatalogPage implements OnInit {
  private readonly http = inject(HttpClient);
  readonly products = signal<CatalogProduct[]>([]);
  readonly loading = signal(true);
  readonly error = signal(false);
  readonly selected = signal<CatalogProduct | null>(null);
  search = '';
  private searchTimer?: ReturnType<typeof setTimeout>;

  ngOnInit() {
    this.track('landing_view');
    this.load();
  }

  load() {
    if (this.search.trim()) this.track('catalog_search', { source: 'site' });
    this.loading.set(true);
    this.error.set(false);
    let params = new HttpParams();
    if (this.search.trim()) params = params.set('search', this.search.trim());
    this.http.get<CatalogProduct[]>('/api/v1/catalog/products', { params }).subscribe({
      next: (products) => {
        this.products.set(products);
        this.loading.set(false);
      },
      error: () => {
        this.error.set(true);
        this.loading.set(false);
      },
    });
  }

  onSearch(value: string) {
    this.search = value;
    clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => this.load(), 280);
  }

  track(name: string, properties: Record<string, string> = {}) {
    const key = 'goes_visitor';
    const anonymousId = localStorage.getItem(key) ?? crypto.randomUUID();
    localStorage.setItem(key, anonymousId);
    void fetch(apiUrl('/telemetry/events'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, anonymous_id: anonymousId, properties }),
    });
  }

  glyph(name: string) {
    return name.trim().slice(0, 2).toUpperCase();
  }

  whatsappUrl(product?: CatalogProduct) {
    const text = product
      ? `Olá! Tenho interesse na peça ${product.name} (SKU ${product.sku}). Pode confirmar a aplicação para o meu veículo?`
      : 'Olá! Preciso de ajuda para encontrar uma peça para o meu veículo.';
    return `https://wa.me/?text=${encodeURIComponent(text)}`;
  }
}
