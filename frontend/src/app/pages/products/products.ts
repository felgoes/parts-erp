import { CurrencyPipe, DatePipe, DecimalPipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { finalize } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { Product, ProductDetail, StockMovement } from '../../core/models';
import { PageHeader } from '../../shared/page-header';

@Component({
  selector: 'app-products',
  imports: [CurrencyPipe, DatePipe, DecimalPipe, ReactiveFormsModule, PageHeader],
  template: `
    <app-page-header
      eyebrow="Catálogo"
      title="Produtos e estoque"
      subtitle="Peças, preços e disponibilidade em um só lugar."
      ><button class="primary" (click)="openNew()">+ Novo produto</button></app-page-header
    >
    <section class="toolbar">
      <div class="search">
        <span>⌕</span
        ><input
          placeholder="Buscar por peça ou SKU…"
          [value]="search()"
          (input)="search.set($any($event.target).value)"
        />
      </div>
      <label class="check"
        ><input
          type="checkbox"
          [checked]="onlyLow()"
          (change)="onlyLow.set($any($event.target).checked)"
        />
        Apenas estoque baixo</label
      ><span class="count">{{ filtered().length }} produtos</span>
    </section>
    <section class="card table-card">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Produto</th>
              <th>SKU</th>
              <th>Preço</th>
              <th>Estoque</th>
              <th>Condição</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            @for (product of filtered(); track product.id) {
              <tr class="clickable-row" (click)="openDetails(product)">
                <td>
                  <div class="product">
                    <span>{{ product.name[0] }}</span>
                    <div>
                      <strong>{{ product.name }}</strong
                      ><small>{{ product.description || 'Sem descrição' }}</small>
                    </div>
                  </div>
                </td>
                <td>
                  <code>{{ product.sku }}</code>
                </td>
                <td>{{ product.sale_price | currency: 'BRL' }}</td>
                <td>
                  <strong>{{ product.current_stock | number: '1.0-3' }}</strong> un.
                </td>
                <td>
                  <span
                    class="badge"
                    [class.warning]="product.current_stock <= product.minimum_stock"
                    [class.success]="product.current_stock > product.minimum_stock"
                    >{{
                      product.current_stock <= product.minimum_stock ? 'Baixo' : 'Disponível'
                    }}</span
                  >
                </td>
                <td class="right">
                  <button class="secondary small" (click)="$event.stopPropagation(); openDetails(product)">Detalhes</button>
                  <button class="secondary small" (click)="$event.stopPropagation(); openAdjust(product)">Ajustar</button>
                </td>
              </tr>
            } @empty {
              <tr>
                <td colspan="6"><div class="empty">Nenhum produto encontrado.</div></td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    </section>
    @if (modal()) {
      <div class="modal-backdrop" (click)="close()">
        <section class="modal" (click)="$event.stopPropagation()">
          <div class="modal-head">
            <div>
              <p class="eyebrow">{{ adjusting() ? 'Movimentação' : 'Catálogo' }}</p>
              <h2>{{ adjusting() ? 'Ajustar estoque' : 'Novo produto' }}</h2>
            </div>
            <button class="close" (click)="close()">×</button>
          </div>
          @if (adjusting(); as product) {
            <form [formGroup]="adjustForm" (ngSubmit)="saveAdjustment(product)">
              <div class="selected-product">
                <strong>{{ product.name }}</strong
                ><span>Saldo atual: {{ product.current_stock }} un.</span>
              </div>
              <label
                >Quantidade <input type="number" step="0.001" formControlName="quantity" /><small
                  >Use valor negativo para dar baixa.</small
                ></label
              ><label
                >Motivo
                <input formControlName="reason" placeholder="Ex.: Inventário mensal" /></label
              ><button class="primary full" [disabled]="adjustForm.invalid || saving()">
                Salvar ajuste
              </button>
            </form>
          } @else {
            <form [formGroup]="productForm" (ngSubmit)="saveProduct()">
              <div class="form-grid">
                <label>SKU<input formControlName="sku" placeholder="PAST-001" /></label
                ><label
                  >Nome<input
                    formControlName="name"
                    placeholder="Pastilha de freio dianteira" /></label
                ><label class="span-2"
                  >Descrição<textarea formControlName="description" rows="2"></textarea></label
                ><label
                  >Preço de venda<input
                    type="number"
                    step="0.01"
                    formControlName="sale_price" /></label
                ><label>Custo<input type="number" step="0.01" formControlName="cost_price" /></label
                ><label
                  >Estoque inicial<input
                    type="number"
                    step="0.001"
                    formControlName="current_stock" /></label
                ><label
                  >Estoque mínimo<input type="number" step="0.001" formControlName="minimum_stock"
                /></label>
              </div>
              <button class="primary full" [disabled]="productForm.invalid || saving()">
                Cadastrar produto
              </button>
            </form>
          }
        </section>
      </div>
    }
    @if (detail(); as product) {
      <div class="modal-backdrop" (click)="detail.set(null)">
        <section class="modal wide" (click)="$event.stopPropagation()">
          <div class="modal-head"><div><p class="eyebrow">Catálogo</p><h2>{{ product.name }}</h2></div><button class="close" (click)="detail.set(null)">×</button></div>
          <div class="detail-grid"><div><small>SKU</small><strong>{{ product.sku }}</strong></div><div><small>Preço</small><strong>{{ product.sale_price | currency:'BRL' }}</strong></div><div><small>Estoque atual</small><strong>{{ product.current_stock | number:'1.0-3' }} un.</strong></div></div>
          <p>{{ product.description || 'Sem descrição cadastrada.' }}</p>
          <h3>Anúncios vinculados</h3>
          @for (listing of product.listings; track listing.id) {
            <div class="listing-detail">@if (listing.thumbnail) { <img [src]="listing.thumbnail" alt="" /> }<div><strong>{{ listing.title || listing.external_item_id }}</strong><small>Item {{ listing.external_item_id }} · estoque ML {{ listing.available_quantity ?? '—' }} · vendidos {{ listing.sold_quantity ?? 0 }} · visitas {{ listing.visits ?? 0 }}</small><span>{{ listing.status || '—' }} · R$ {{ listing.marketplace_price ?? 0 }}</span>@if (listing.permalink) { <a [href]="listing.permalink" target="_blank" rel="noopener">Abrir anúncio</a> }</div></div>
          } @empty { <p class="muted">Nenhum anúncio do Mercado Livre vinculado a este SKU.</p> }
          @if (product.listings.length) { <button class="secondary full" (click)="syncMarketplace(product)">Atualizar estoque no Mercado Livre</button> }
          <h3>Histórico de estoque</h3>
          <div class="movement-list">@for (movement of movements(); track movement.id) { <div><span>{{ movement.created_at | date:'dd/MM/yyyy HH:mm' }}</span><strong [class.negative]="movement.quantity < 0">{{ movement.quantity > 0 ? '+' : '' }}{{ movement.quantity }}</strong><span>{{ movement.reason }}</span><small>Saldo: {{ movement.balance_after }}</small></div> } @empty { <p class="muted">Nenhuma movimentação registrada.</p> }</div>
        </section>
      </div>
    }
  `,
  styleUrl: './products.scss',
})
export class ProductsPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  readonly products = signal<Product[]>([]);
  readonly search = signal('');
  readonly onlyLow = signal(false);
  readonly modal = signal(false);
  readonly adjusting = signal<Product | null>(null);
  readonly detail = signal<ProductDetail | null>(null);
  readonly movements = signal<StockMovement[]>([]);
  readonly saving = signal(false);
  readonly filtered = computed(() => {
    const q = this.search().toLowerCase();
    return this.products().filter(
      (p) =>
        (!q || p.name.toLowerCase().includes(q) || p.sku.toLowerCase().includes(q)) &&
        (!this.onlyLow() || p.current_stock <= p.minimum_stock),
    );
  });
  readonly productForm = this.fb.nonNullable.group({
    sku: ['', Validators.required],
    name: ['', Validators.required],
    description: [''],
    sale_price: [0, [Validators.required, Validators.min(0)]],
    cost_price: [0, Validators.min(0)],
    current_stock: [0],
    minimum_stock: [0, Validators.min(0)],
  });
  readonly adjustForm = this.fb.nonNullable.group({
    quantity: [0, [Validators.required]],
    reason: ['', [Validators.required, Validators.minLength(3)]],
  });
  ngOnInit() {
    this.load();
  }
  load() {
    this.api.products().subscribe((v) => this.products.set(v));
  }
  openNew() {
    this.adjusting.set(null);
    this.productForm.reset({
      sku: '',
      name: '',
      description: '',
      sale_price: 0,
      cost_price: 0,
      current_stock: 0,
      minimum_stock: 0,
    });
    this.modal.set(true);
  }
  openAdjust(p: Product) {
    this.adjusting.set(p);
    this.adjustForm.reset({ quantity: 0, reason: '' });
    this.modal.set(true);
  }
  openDetails(p: Product) {
    this.detail.set(null);
    this.movements.set([]);
    this.api.productDetail(p.id).subscribe((v) => this.detail.set(v));
    this.api.productMovements(p.id).subscribe((v) => this.movements.set(v));
  }
  syncMarketplace(p: ProductDetail) {
    this.api.syncMarketplaceStock(p.id).subscribe((updated) => {
      this.detail.update((current) => current ? { ...current, current_stock: updated.current_stock } : current);
      this.load();
    });
  }
  close() {
    this.modal.set(false);
  }
  saveProduct() {
    if (this.productForm.invalid) return;
    this.saving.set(true);
    this.api
      .createProduct(this.productForm.getRawValue())
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe(() => {
        this.close();
        this.load();
      });
  }
  saveAdjustment(p: Product) {
    if (this.adjustForm.invalid) return;
    this.saving.set(true);
    const v = this.adjustForm.getRawValue();
    this.api
      .adjustStock(p.id, v.quantity, v.reason)
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe(() => {
        this.close();
        this.load();
      });
  }
}
