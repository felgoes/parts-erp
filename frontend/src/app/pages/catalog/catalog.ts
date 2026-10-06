import { CurrencyPipe, KeyValuePipe } from '@angular/common';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { apiUrl } from '../../core/api-url';
import { CatalogProduct } from '../../core/models';

@Component({
  selector: 'app-catalog',
  imports: [CurrencyPipe, FormsModule, KeyValuePipe],
  template: `
    <main class="catalog-shell">
      <header class="catalog-header">
        <a class="brand" href="/" aria-label="Goes Auto Parts">
          <img src="/brand/goes-mark.png" alt="" />
          <span>GOES <small>AUTO PARTS</small></span>
        </a>
        <nav>
          <a href="#catalogo">Catálogo</a>
          <a href="#como-comprar">Como comprar</a>
          <a class="header-cta" [href]="whatsappUrl()">Falar com especialista</a>
        </nav>
      </header>

      <section class="hero">
        <div class="hero-copy">
          <p class="kicker">GOES AUTO PARTS / PEÇAS PARA VEÍCULOS CHINESES</p>
          <h1>Encontre a peça certa. Com orientação de quem entende.</h1>
          <p class="hero-text">
            Peças para BYD, GWM, Chery, JAC e outros veículos chineses. Busque pelo nome ou SKU, informe marca, modelo e ano e confirme a aplicação com a nossa equipe.
          </p>
          <div class="hero-actions">
            <a class="button button-red" href="#catalogo">Explorar catálogo</a>
            <a class="button button-quiet" [href]="whatsappUrl()">Falar com especialista</a>
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
            <p class="kicker">CATÁLOGO DE PEÇAS</p>
            <h2>Encontre pelo nome, SKU ou aplicação.</h2>
          </div>
          <p class="section-note">Disponibilidade atualizada conforme os anúncios. Antes de comprar, confirme aplicação, marca, modelo e ano com a equipe.</p>
        </div>
        <div class="search-row">
          <label class="search-box">
            <span>O que você procura?</span>
            <input [ngModel]="search" (ngModelChange)="onSearch($event)" (keyup.enter)="load()" placeholder="Ex.: filtro de óleo, Tiggo 7, LR174890" />
          </label>
          <button class="button button-dark" (click)="load()">Buscar peças</button>
        </div>
        @if (loading()) {
          <div class="catalog-state">Atualizando o catálogo...</div>
        } @else if (error()) {
          <div class="catalog-state error"><strong>Não conseguimos carregar o catálogo.</strong><span>Tente novamente em instantes ou fale com a equipe pelo WhatsApp.</span></div>
        } @else if (!products().length) {
          <div class="catalog-state"><strong>Nenhuma peça encontrada.</strong><span>Tente outro nome, SKU, marca ou modelo. Se preferir, nossa equipe encontra a peça com você.</span><a class="button button-quiet" [href]="whatsappUrl()">Pedir ajuda no WhatsApp</a></div>
        } @else {
          <div class="product-grid">
            @for (product of products(); track product.id) {
              <article class="product-card" tabindex="0" (click)="selected.set(product)" (keydown.enter)="selected.set(product)">
                <div class="product-code">{{ product.sku }}</div>
                @if (product.images[0]?.url || product.listings[0]?.thumbnail) { <img class="product-image" [src]="product.images[0]?.url || product.listings[0].thumbnail" [alt]="product.name" loading="lazy" /> } @else { <div class="product-glyph">{{ glyph(product.name) }}</div> }
                <div class="product-body">
                  <h3>{{ product.name }}</h3>
                  @if (product.description) { <p>{{ product.description }}</p> }
                  <div class="product-foot">
                    <strong>{{ product.sale_price | currency: 'BRL' }}</strong>
                    <span [class.out]="!product.in_stock">
                      {{ product.in_stock ? 'Disponível' : 'Consulte disponibilidade' }}
                    </span>
                  </div>
                  <a class="product-link" [href]="whatsappUrl(product)" (click)="track('whatsapp_click', { sku: product.sku, placement: 'product_card' })">Tenho interesse nesta peça ↗</a>
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
            <div class="catalog-modal-head"><div><p class="kicker">DETALHES DA PEÇA</p><h2>{{ product.name }}</h2><p class="modal-sku">SKU {{ product.sku }}</p></div><span [class.out]="!product.in_stock" class="modal-stock">{{ product.in_stock ? 'Disponível' : 'Consulte disponibilidade' }}</span></div>
            <p class="modal-description">{{ product.description || 'Fale com a equipe para confirmar aplicação, compatibilidade e disponibilidade antes de fechar o pedido.' }}</p>
            @if (product.images.length) { <div class="master-photo-gallery" aria-label="Fotos da peça">@for (image of product.images; track image.id) { <img [src]="image.url" [alt]="product.name" loading="lazy" /> }</div> }
            @if (product.brand || product.manufacturer_part_number || product.barcode || product.category) { <div class="attribute-list master-attributes">@if (product.brand) { <span><small>Marca</small><b>{{ product.brand }}</b></span> } @if (product.manufacturer_part_number) { <span><small>Código OEM</small><b>{{ product.manufacturer_part_number }}</b></span> } @if (product.barcode) { <span><small>EAN/GTIN</small><b>{{ product.barcode }}</b></span> } @if (product.category) { <span><small>Categoria</small><b>{{ product.category }}</b></span> } @for (entry of product.attributes | keyvalue; track entry.key) { <span><small>{{ entry.key }}</small><b>{{ entry.value }}</b></span> }</div> }
            @if (product.fitments.length) { <section class="catalog-fitments"><p class="kicker">APLICAÇÃO VEICULAR</p><div>@for (fitment of product.fitments; track $index) { <article><strong>{{ fitment.make }} {{ fitment.model }}</strong><span>{{ fitment.year_from || '—' }}{{ fitment.year_to && fitment.year_to !== fitment.year_from ? '–' + fitment.year_to : '' }}{{ fitment.engine ? ' · ' + fitment.engine : '' }}{{ fitment.version ? ' · ' + fitment.version : '' }}</span></article> }</div><small>Confirme a aplicação pelo chassi com nossa equipe antes de comprar.</small></section> }
            @for (listing of product.listings; track listing.external_item_id) {
              <article class="catalog-listing"><div class="listing-media">@if (listing.thumbnail) { <img [src]="listing.thumbnail" [alt]="listing.title || product.name" /> } @else { <span>{{ glyph(product.name) }}</span> }</div><div class="listing-info"><div class="listing-top"><div><small>Anúncio no Mercado Livre · {{ listing.external_item_id }}</small><h3>{{ listing.title || product.name }}</h3></div><strong>{{ (listing.marketplace_price ?? product.sale_price) | currency:'BRL' }}</strong></div><div class="listing-stats"><span>Disponibilidade <b>{{ listing.available_quantity ?? '—' }}</b></span><span>Vendas no anúncio <b>{{ listing.sold_quantity ?? 0 }}</b></span><span>Visualizações <b>{{ listing.visits ?? 0 }}</b></span></div>@if (listing.attributes.length) { <div class="attribute-list">@for (attribute of listing.attributes; track attribute.name) { <span><small>{{ attribute.name }}</small><b>{{ attribute.value }}</b></span> }</div> }<div class="listing-actions"><a class="button button-red" [href]="whatsappUrl(product)" (click)="track('whatsapp_click', { sku: product.sku, placement: 'product_detail' })">Tenho interesse nesta peça</a>@if (listing.permalink) { <a class="button button-quiet listing-external" [href]="listing.permalink" target="_blank" rel="noopener">Abrir anúncio no Mercado Livre ↗</a> }</div></div></article>
            } @empty { <div class="catalog-state">Este produto ainda não possui um anúncio vinculado. Fale com a equipe para consultar alternativas.</div> }
          </section>
        </div>
      }

      <section class="how-section" id="como-comprar">
        <div>
          <p class="kicker">COMO COMPRAR</p>
          <h2>Uma conversa objetiva. A peça certa para o seu carro.</h2>
        </div>
        <div class="steps">
          <div><b>01</b><span>Encontre a peça pelo nome, SKU ou anúncio.</span></div>
          <div><b>02</b><span>Envie marca, modelo e ano do veículo.</span></div>
          <div><b>03</b><span>Receba confirmação de aplicação e disponibilidade.</span></div>
        </div>
      </section>

      <footer class="catalog-footer">
        <div class="brand footer-brand">
          <img src="/brand/goes-mark.png" alt="" />
          <span>GOES <small>AUTO PARTS</small></span>
        </div>
        <p>Peças para veículos chineses, com orientação de verdade.</p>
        <a [href]="whatsappUrl()">Falar com a equipe</a>
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
