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
          <p class="kicker">GOES AUTO PARTS / PECAS CERTAS</p>
          <h1>Encontre a peca certa para o seu carro.</h1>
          <p class="hero-text">
            Consulte o catalogo atualizado, confirme a disponibilidade e fale com a nossa equipe
            pelo WhatsApp.
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
            <h2>Estoque disponivel, sem misterio.</h2>
          </div>
          <p class="section-note">A disponibilidade muda em tempo real. Confirme a aplicacao com a equipe.</p>
        </div>
        <div class="search-row">
          <label class="search-box">
            <span>Buscar por nome ou SKU</span>
            <input [(ngModel)]="search" (keyup.enter)="load()" placeholder="Ex.: pastilha, filtro, PAST-001" />
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
              <article class="product-card">
                <div class="product-code">{{ product.sku }}</div>
                <div class="product-glyph">{{ glyph(product.name) }}</div>
                <div class="product-body">
                  <h3>{{ product.name }}</h3>
                  @if (product.description) { <p>{{ product.description }}</p> }
                  <div class="product-foot">
                    <strong>{{ product.sale_price | currency: 'BRL' }}</strong>
                    <span [class.out]="!product.in_stock">
                      {{ product.in_stock ? 'Em estoque' : 'Sob consulta' }}
                    </span>
                  </div>
                  <a class="product-link" [href]="whatsappUrl(product)">Pedir esta peca</a>
                </div>
              </article>
            }
          </div>
        }
      </section>

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
  search = '';

  ngOnInit() {
    this.load();
  }

  load() {
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
