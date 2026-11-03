import { CurrencyPipe, DatePipe, DecimalPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { Location } from '@angular/common';
import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { ProductDetail, StockMovement } from '../../core/models';
import { canAdjustStock, canManageCatalog, canReadCosts } from '../../core/user-access';
import { PageHeader } from '../../shared/page-header';

@Component({
  selector: 'app-product-detail',
  imports: [CurrencyPipe, DatePipe, DecimalPipe, PageHeader],
  templateUrl: './product-detail.html',
  styleUrl: './product-detail.scss',
})
export class ProductDetailPage implements OnInit, OnDestroy {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly location = inject(Location);
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);

  readonly product = signal<ProductDetail | null>(null);
  readonly movements = signal<StockMovement[]>([]);
  readonly loading = signal(true);
  readonly error = signal('');
  readonly copied = signal(false);
  private copiedTimer: ReturnType<typeof setTimeout> | null = null;

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (!id) {
      this.error.set('Produto não encontrado.');
      this.loading.set(false);
      return;
    }
    this.load(id);
  }

  ngOnDestroy(): void {
    if (this.copiedTimer) clearTimeout(this.copiedTimer);
  }

  private load(id: string): void {
    this.loading.set(true);
    this.error.set('');
    this.api.productDetail(id).subscribe({
      next: (product) => {
        this.product.set(product);
        this.loading.set(false);
      },
      error: (response: HttpErrorResponse) => {
        this.product.set(null);
        this.loading.set(false);
        if (response.status === 403) this.error.set('Você não tem acesso a este produto.');
        else if (response.status === 404) this.error.set('Este produto não existe ou foi removido.');
        else this.error.set('Não foi possível carregar o produto. Verifique a conexão e tente novamente.');
      },
    });
    this.api.productMovements(id).subscribe({
      next: (items) => this.movements.set(items),
      error: () => this.movements.set([]),
    });
  }

  canManageCatalog(): boolean {
    return canManageCatalog(this.auth.user()?.role);
  }

  canAdjustStock(): boolean {
    return canAdjustStock(this.auth.user()?.role);
  }

  canReadCosts(): boolean {
    return canReadCosts(this.auth.user()?.role);
  }

  entries(value: Record<string, string>): [string, string][] {
    return Object.entries(value ?? {});
  }

  copySku(value: string): void {
    if (!navigator.clipboard) return;
    navigator.clipboard.writeText(value).then(() => {
      this.copied.set(true);
      if (this.copiedTimer) clearTimeout(this.copiedTimer);
      this.copiedTimer = setTimeout(() => this.copied.set(false), 1800);
    });
  }

  back(): void {
    if (window.history.state?.productListOrigin) this.location.back();
    else {
      sessionStorage.removeItem('parts-erp.products-list-view');
      void this.router.navigateByUrl('/products');
    }
  }

  edit(): void {
    const id = this.product()?.id;
    if (id) void this.router.navigateByUrl('/products', { state: { productAction: 'edit', productId: id } });
  }

  adjust(): void {
    const id = this.product()?.id;
    if (id) void this.router.navigateByUrl('/products', { state: { productAction: 'adjust', productId: id } });
  }

  prepareListing(): void {
    const id = this.product()?.id;
    if (id) void this.router.navigateByUrl('/products', { state: { productAction: 'listing', productId: id } });
  }

  retry(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (id) this.load(id);
  }
}
