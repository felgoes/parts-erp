import { CurrencyPipe } from '@angular/common';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CatalogProduct } from '../../core/models';

@Component({
  selector: 'app-catalog',
  imports: [CurrencyPipe, FormsModule],
  template: `
    <main class="catalog-shell">
      <header class="catalog-header">
        <a class="brand" href="/" aria-label="Goes Auto Parts">
          <img src="/brand/goes-mark.png" alt="" />
          <span>GOES <small>AUTO PARTS</small></span>
        </a>
        <nav>
          <a href="#catalogo">Catalogo</a>
          <a href="#como-comprar">Como comprar</a>
          <a class="header-cta" [href]="whatsappUrl()">Pedir no WhatsApp</a>
        </nav>
      </header>

      <section class="hero">
        <div class="hero-copy">
          <p class="kicker">GOES AUTO PARTS / VEICULOS CHINESES</p>
          <h1>A peca certa para o seu carro chines.</h1>
          <p class="hero-text">
            Especialistas em pecas para BYD, GWM, Chery, JAC e outros veiculos chineses. Consulte por marca, modelo e ano, confirme a disponibilidade e fale com a nossa equipe pelo WhatsApp.
          </p>
          <div class="hero-actions">
            <a class="button button-red" href="#catalogo">Ver catalogo</a>
            <a class="button button-quiet" [href]="whatsappUrl()">Falar com a equipe</a>
          </div>
        </div>
        <div class="hero-mark" aria-hidden="true">
          <img src="/brand/goes-mark.png" alt="" />
          <span>PARTS<br />THAT<br />MOVE</span>
        </div>
      </section>

      <section class="catalog-section" id="catalogo">
        <div class="section-head">
          <div>
            <p class="kicker">CATALOGO ONLINE</p>
            <h2>Pecas para veiculos chineses, sem misterio.</h2>
          </div>
          <p class="section-note">A disponibilidade muda em tempo real. Confirme marca, modelo, ano e aplicacao com a equipe.</p>
        </div>
        <div class="search-row">
          <label class="search-box">
            <span>Buscar por nome ou SKU</span>
            <input [ngModel]="search" (ngModelChange)="onSearch($event)" (keyup.enter)="load()" placeholder="Ex.: pastilha, filtro, PAST-001" />
          </label>
          <button class="button button-dark" (click)="load()">Buscar</button>
        </div>
        @if (loading()) {
          <div class="catalog-state">Carregando catalogo...</div>
        } @else if (error()) {
          <div class="catalog-state error">Nao foi possivel carregar o catalogo agora.</div>
        } @else if (!products().length) {
          <div class="catalog-state">Nenhuma peca encontrada. Tente outro nome ou SKU.</div>
        } @else {
          <div class="product-grid">
            @for (product of products(); track product.id) {
              <article class="product-card" tabindex="0" (click)="selected.set(product)" (keydown.enter)="selected.set(product)">
                <div class="product-code">{{ product.sku }}</div>
                @if (product.listings[0]?.thumbnail) { <img class="product-image" [src]="product.listings[0].thumbnail" [alt]="product.name" /> } @else { <div class="product-glyph">{{ glyph(product.name) }}</div> }
                <div class="product-body">
                  <h3>{{ product.name }}</h3>
                  @if (product.description) { <p>{{ product.description }}</p> }
                  <div class="product-foot">
                    <strong>{{ product.sale_price | currency: 'BRL' }}</strong>
                    <span [class.out]="!product.in_stock">
                      {{ product.in_stock ? 'Em estoque' : 'Sob consulta' }}
                    </span>
                  </div>
                  <a class="product-link" [href]="whatsappUrl(product)" (click)="track('whatsapp_click', { sku: product.sku, placement: 'product_card' })">Pedir esta peca</a>
                </div>
              </article>
            }
          </div>
        }
      </section>

      @if (selected(); as product) {
        <div class="catalog-modal-backdrop" (click)="selected.set(null)">
          <section class="catalog-modal" (click)="$event.stopPropagation()">
            <button class="catalog-modal-close" type="button" aria-label="Fechar detalhes" (click)="selected.set(null)">×</button>
            <div class="catalog-modal-head"><div><p class="kicker">DETALHES DA PEÇA</p><h2>{{ product.name }}</h2><p class="modal-sku">SKU {{ product.sku }}</p></div><span [class.out]="!product.in_stock" class="modal-stock">{{ product.in_stock ? 'Em estoque' : 'Sob consulta' }}</span></div>
            <p class="modal-description">{{ product.description || 'Consulte a equipe para confirmar aplicação, compatibilidade e disponibilidade.' }}</p>
            @for (listing of product.listings; track listing.external_item_id) {
              <article class="catalog-listing"><div class="listing-media">@if (listing.thumbnail) { <img [src]="listing.thumbnail" [alt]="listing.title || product.name" /> } @else { <span>{{ glyph(product.name) }}</span> }</div><div class="listing-info"><div class="listing-top"><div><small>Mercado Livre · {{ listing.external_item_id }}</small><h3>{{ listing.title || product.name }}</h3></div><strong>{{ (listing.marketplace_price ?? product.sale_price) | currency:'BRL' }}</strong></div><div class="listing-stats"><span>Estoque <b>{{ listing.available_quantity ?? '—' }}</b></span><span>Vendidos <b>{{ listing.sold_quantity ?? 0 }}</b></span><span>Visitas <b>{{ listing.visits ?? 0 }}</b></span></div>@if (listing.attributes.length) { <div class="attribute-list">@for (attribute of listing.attributes; track attribute.name) { <span><small>{{ attribute.name }}</small><b>{{ attribute.value }}</b></span> }</div> }<div class="listing-actions"><a class="button button-red" [href]="whatsappUrl(product)" (click)="track('whatsapp_click', { sku: product.sku, placement: 'product_detail' })">Pedir esta peça</a>@if (listing.permalink) { <a class="button button-quiet listing-external" [href]="listing.permalink" target="_blank" rel="noopener">Ver anúncio no Mercado Livre ↗</a> }</div></div></article>
            } @empty { <div class="catalog-state">Este produto ainda não possui anúncio vinculado.</div> }
          </section>
        </div>
      }

      <section class="how-section" id="como-comprar">
        <div>
          <p class="kicker">COMO FUNCIONA</p>
          <h2>Uma conversa objetiva. Uma peca que encaixa.</h2>
        </div>
        <div class="steps">
          <div><b>01</b><span>Busque pelo nome ou SKU.</span></div>
          <div><b>02</b><span>Envie o modelo e o ano do seu carro.</span></div>
          <div><b>03</b><span>Receba confirmacao de aplicacao e disponibilidade.</span></div>
        </div>
      </section>

      <footer class="catalog-footer">
        <div class="brand footer-brand">
          <img src="/brand/goes-mark.png" alt="" />
          <span>GOES <small>AUTO PARTS</small></span>
        </div>
        <p>Auto pecas para quem prefere resolver certo.</p>
        <a [href]="whatsappUrl()">Atendimento pelo WhatsApp</a>
      </footer>
    </main>
  `,
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
    void fetch('/api/v1/telemetry/events', {
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
      ? `Ola! Tenho interesse na peca ${product.name} (SKU ${product.sku}). Pode confirmar a aplicacao?`
      : 'Ola! Preciso de ajuda para encontrar uma peca.';
    return `https://wa.me/?text=${encodeURIComponent(text)}`;
  }
}
