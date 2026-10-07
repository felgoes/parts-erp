import { CurrencyPipe, DatePipe, DecimalPipe } from '@angular/common';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { debounceTime, finalize } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { ApiService } from '../../core/api.service';
import { LiveUpdatesService } from '../../core/live-updates.service';
import { AuthService } from '../../core/auth.service';
import { Product, ProductChannelDraft, ProductChannelMetadata, ProductDetail, ProductFitment, ProductImage, StockMovement } from '../../core/models';
import { canAdjustStock, canManageCatalog, canReadCosts } from '../../core/user-access';
import { PageHeader } from '../../shared/page-header';

@Component({
  selector: 'app-products',
  imports: [CurrencyPipe, DatePipe, DecimalPipe, ReactiveFormsModule, PageHeader],
  template: `
    <app-page-header
      eyebrow="Catálogo"
      title="Produtos e estoque"
      subtitle="Peças, preços e disponibilidade em um só lugar."
      >@if (canManageCatalog()) { <button class="primary" (click)="openNew()">+ Novo produto</button> }</app-page-header
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
                  @if (canAdjustStock()) { <button class="secondary small" (click)="$event.stopPropagation(); openAdjust(product)">Ajustar</button> }
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
              <h2>{{ adjusting() ? 'Ajustar estoque' : editing() ? 'Editar peça' : 'Nova peça' }}</h2>
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
                <label>SKU<input formControlName="sku" placeholder="PAST-001" [readonly]="!!editing()" /></label
                ><label
                  >Nome<input
                    formControlName="name"
                    placeholder="Pastilha de freio dianteira" /></label
                ><label>Marca<input formControlName="brand" placeholder="Ex.: Chery" /></label
                ><label>Fabricante<input formControlName="manufacturer" /></label
                ><label>Número OEM / MPN<input formControlName="manufacturer_part_number" /></label
                ><label>GTIN / EAN<input formControlName="barcode" inputmode="numeric" /></label
                ><label>Categoria da peça<input formControlName="category" placeholder="Motor, freios…" /></label
                ><label>Condição<select formControlName="item_condition"><option value="new">Nova</option><option value="used">Usada</option><option value="refurbished">Recondicionada</option></select></label
                ><label>Garantia (dias)<input type="number" min="0" formControlName="warranty_days" /></label
                ><label>País de origem<input formControlName="origin_country" placeholder="Brasil" /></label
                ><label class="span-2"
                  >Descrição<textarea formControlName="description" rows="2"></textarea></label
                ><label
                  >Preço de venda<input
                    type="number"
                    step="0.01"
                    formControlName="sale_price" /></label
                >@if (canReadCosts()) { <label>Custo<input type="number" step="0.01" formControlName="cost_price" /></label> }
                ><label
                  >Estoque inicial<input
                    type="number"
                    step="0.001"
                    formControlName="current_stock" /></label
                ><label
                  >Estoque mínimo<input type="number" step="0.001" formControlName="minimum_stock"
                /></label>
                <label>Peso embalado (g)<input type="number" step="0.001" formControlName="weight_g" /></label>
                <label>Comprimento (cm)<input type="number" step="0.01" formControlName="package_length_cm" /></label>
                <label>Largura (cm)<input type="number" step="0.01" formControlName="package_width_cm" /></label>
                <label>Altura (cm)<input type="number" step="0.01" formControlName="package_height_cm" /></label>
                <label class="span-2">Especificações (uma por linha: chave: valor)<textarea rows="3" [value]="attributesText()" (input)="attributesText.set($any($event.target).value)" placeholder="Modelo: Tiggo 7\nMaterial: Borracha"></textarea></label>
                <label class="span-2">Aplicação veicular (uma por linha: marca | modelo | ano inicial | ano final | motor)<textarea rows="3" [value]="fitmentsText()" (input)="fitmentsText.set($any($event.target).value)" placeholder="Chery | Tiggo 7 | 2020 | 2024 | 1.5 Turbo"></textarea></label>
                <label class="span-2">Fotos da peça <input type="file" accept="image/jpeg,image/png,image/webp" multiple (change)="selectPhotos($event)" /><small>JPEG, PNG ou WebP. Até 10 MB por arquivo; as imagens são otimizadas para remover metadados e reduzir tamanho.</small></label>
                @if (photoPreviews().length) { <div class="span-2 photo-preview-grid">@for (photo of photoPreviews(); track photo) { <img [src]="photo" alt="Prévia da foto selecionada" /> }</div> }
              </div>
              <button class="primary full" [disabled]="productForm.invalid || saving()">
                {{ saving() ? 'Salvando…' : editing() ? 'Salvar alterações' : 'Cadastrar peça' }}
              </button>
            </form>
          }
        </section>
      </div>
    }
    @if (detail(); as product) {
      <div class="modal-backdrop" (click)="detail.set(null)">
        <section class="modal wide object-modal" (click)="$event.stopPropagation()">
          <div class="modal-head product-hero"><div><p class="eyebrow">Catálogo · Produto</p><h2>{{ product.name }}</h2><p class="detail-subtitle">SKU {{ product.sku }} · atualizado no estoque</p></div><button class="close" aria-label="Fechar produto" (click)="detail.set(null)">×</button></div>
          @if (canManageCatalog()) { <div class="detail-actions"><button class="secondary small" (click)="openEdit(product)">Editar ficha</button><button class="secondary small" (click)="detailPhotoInput.click()">Adicionar fotos</button><input #detailPhotoInput hidden type="file" accept="image/jpeg,image/png,image/webp" multiple (change)="uploadDetailPhotos(product, $event)" /></div> }
          <div class="product-detail-summary"><div><span>SKU</span><strong>{{ product.sku }}</strong></div><div><span>Preço de venda</span><strong>{{ product.sale_price | currency:'BRL' }}</strong></div><div><span>Estoque atual</span><strong>{{ product.current_stock | number:'1.0-3' }} un.</strong><small>mínimo {{ product.minimum_stock | number:'1.0-3' }} un.</small></div></div>
          @if (product.images.length) { <div class="master-photo-grid">@for (photo of product.images; track photo.id) { <figure><a [href]="photo.url" target="_blank" rel="noopener"><img [src]="photo.url" [alt]="product.name" /></a>@if (canManageCatalog()) { <button class="photo-remove" aria-label="Remover foto" (click)="removePhoto(product, photo)">×</button> }</figure> }</div> }
          <div class="product-detail-summary product-spec-grid">@if (product.brand) { <div><span>Marca</span><strong>{{ product.brand }}</strong></div> }@if (product.manufacturer_part_number) { <div><span>OEM / MPN</span><strong>{{ product.manufacturer_part_number }}</strong></div> }@if (product.barcode) { <div><span>GTIN / EAN</span><strong>{{ product.barcode }}</strong></div> }@if (product.category) { <div><span>Categoria</span><strong>{{ product.category }}</strong></div> }@if (product.weight_g) { <div><span>Peso embalado</span><strong>{{ product.weight_g }} g</strong></div> }@if (product.warranty_days !== null) { <div><span>Garantia</span><strong>{{ product.warranty_days }} dias</strong></div> }</div>
          @if (product.fitments.length) { <section class="product-section"><div class="section-heading"><div><p class="eyebrow">Aplicação</p><h3>Veículos compatíveis</h3></div></div><div class="fitment-chips">@for (fit of product.fitments; track $index) { <span>{{ fit.make }} {{ fit.model }} · {{ fit.year_from || '—' }}–{{ fit.year_to || '—' }}{{ fit.engine ? ' · ' + fit.engine : '' }}</span> }</div></section> }
          <div class="product-description"><span class="eyebrow">Descrição</span><p>{{ product.description || 'Este produto ainda não possui uma descrição cadastrada.' }}</p></div>
          <section class="product-section"><div class="section-heading"><div><p class="eyebrow">Canais de venda</p><h3>Anúncios vinculados</h3></div>@if (canAdjustStock() && product.listings.some(hasExternalListing)) { <button class="secondary small" (click)="syncMarketplace(product)">Sincronizar estoque nos anúncios</button> }</div>
            @for (listing of product.listings; track listing.id) {
              <article class="listing-card">@if (listing.thumbnail) { <img [src]="listing.thumbnail" [alt]="listing.title || 'Imagem do anúncio'" /> } @else { <div class="listing-placeholder">{{ listing.provider === 'shopee' ? 'S' : 'ML' }}</div> }<div class="listing-content"><div class="listing-title"><div><span class="eyebrow">{{ listing.provider === 'shopee' ? 'Shopee' : 'Mercado Livre' }} · {{ listing.external_item_id || 'rascunho' }}</span><strong>{{ listing.title || 'Rascunho sem título' }}</strong></div><span class="badge" [class.success]="listing.sync_status === 'published'">{{ syncStatusLabel(listing.sync_status) }}</span></div><div class="listing-metrics"><div><small>Estoque no canal</small><strong>{{ listing.available_quantity ?? '—' }}</strong></div><div><small>Vendidos</small><strong>{{ listing.sold_quantity ?? 0 }}</strong></div><div><small>Visitas</small><strong>{{ listing.visits ?? 0 }}</strong></div><div><small>Preço</small><strong>{{ listing.marketplace_price | currency:'BRL' }}</strong></div></div>@if (listing.sync_error) { <p class="channel-notice">{{ listing.sync_error }}</p> }@if (listing.permalink) { <a class="listing-link" [href]="listing.permalink" target="_blank" rel="noopener">Abrir anúncio <span>↗</span></a> }</div></article>
            } @empty { <div class="empty">Nenhum anúncio do Mercado Livre vinculado a este SKU.</div> }
          </section>
          @if (canManageCatalog()) { <section class="product-section channel-publish">
            <div class="section-heading"><div><p class="eyebrow">Cadastro multicanal</p><h3>Preparar anúncio</h3><p class="muted">Cada plataforma tem campos, categorias e políticas próprias. Salvar rascunho não publica nem altera anúncios.</p></div></div>
            <div class="channel-tabs"><button [class.active]="channelProvider() === 'mercadolivre'" (click)="selectProvider('mercadolivre')">Mercado Livre</button><button [class.active]="channelProvider() === 'shopee'" (click)="selectProvider('shopee')">Shopee</button></div>
            @if (channelMetadata(); as meta) {
              @if (!meta.connected) {
                <p class="channel-notice">Conecte esta conta em Integrações para consultar categorias e publicar.</p>
              } @else {
                <label>Buscar categoria na plataforma<input [value]="categoryQuery()" (input)="categoryQuery.set($any($event.target).value)" placeholder="Pesquise pelo nome da peça ou categoria" /><button class="secondary small" (click)="searchCategories()">Buscar categorias</button></label>
                @if (meta.categories.length) { <label>Categoria<select [value]="selectedCategory()" (change)="loadCategory($any($event.target).value)"><option value="">Selecione a categoria sugerida</option>@for (category of meta.categories; track category.id) { <option [value]="category.id">{{ category.name }} · {{ category.id }}</option> }</select></label> }
                @if (selectedCategory()) {
                  <div class="channel-form-grid">
                    <label>{{ channelProvider() === 'mercadolivre' && meta.user_product_seller ? 'Nome da família no Mercado Livre' : 'Título do anúncio' }}<input [value]="channelTitle()" (input)="channelTitle.set($any($event.target).value)" [attr.maxlength]="meta.limits.max_title_length || 200" /><small>{{ channelTitle().length }}/{{ meta.limits.max_title_length || 200 }} caracteres{{ channelProvider() === 'mercadolivre' && meta.user_product_seller ? ' · o título será gerado pelo Mercado Livre' : '' }}</small></label>
                    <label>Preço neste canal<input type="number" min="0.01" step="0.01" [value]="channelPrice()" (input)="channelPrice.set(+$any($event.target).value)" /></label>
                    @if (channelProvider() === 'mercadolivre') { <label>Tipo de anúncio<select [value]="listingType()" (change)="listingType.set($any($event.target).value)">@for (type of meta.listing_types; track type.id) { <option [value]="type.id">{{ type.name || type.id }}</option> }</select></label> }
                    @for (attribute of meta.attributes; track attribute.id) {
                      <label>{{ attribute.name }} @if (attribute.required || (channelProvider() === 'mercadolivre' && attribute.new_required)) {<em>Obrigatório</em>}
                        @if (attribute.values.length) { <select [value]="channelAttributes()[attribute.id] || ''" (change)="setChannelAttribute(attribute.id, $any($event.target).value)"><option value="">Selecione…</option>@for (value of attribute.values; track value.id || value.value_id || value.name) { <option [value]="value.id || value.value_id || value.name">{{ value.name || value.original_value_name }}</option> }</select> }
                        @else { <input [value]="channelAttributes()[attribute.id] || ''" (input)="setChannelAttribute(attribute.id, $any($event.target).value)" [required]="attribute.required || (channelProvider() === 'mercadolivre' && attribute.new_required)" /> }
                      </label>
                    }
                    @if (channelProvider() === 'shopee') { <fieldset class="channel-logistics"><legend>Formas de envio habilitadas</legend>@for (logistics of meta.logistics; track logistics.id) { <label><input type="checkbox" [checked]="selectedLogistics().includes(logistics.id)" (change)="toggleLogistics(logistics.id, $any($event.target).checked)" />{{ logistics.name }}</label> }</fieldset> }
                  </div>
                  <label>Descrição comercial para este canal<textarea rows="4" [value]="channelDescription()" (input)="channelDescription.set($any($event.target).value)" placeholder="Descrição clara, aplicação e conteúdo da embalagem"></textarea></label>
                  <div class="channel-actions"><button class="secondary" [disabled]="saving()" (click)="saveChannelDraft(product)">Salvar rascunho</button><button class="primary" [disabled]="saving()" (click)="publishChannel(product)">Validar e publicar / sincronizar</button></div>
                }
              }
            } @else {
              <button class="secondary small" (click)="loadChannelMetadata()">Carregar requisitos do canal</button>
            }
            @if (channelMessage()) { <p class="channel-notice">{{ channelMessage() }}</p> }
          </section> }
          <section class="product-section stock-section"><div class="section-heading"><div><p class="eyebrow">Movimentações</p><h3>Histórico de estoque</h3>@if (canReadCosts()) { <p class="muted">Cada saída usa o custo médio vigente no momento do movimento.</p> }</div><span class="muted">{{ movements().length }} registro(s)</span></div><div class="movement-list">@for (movement of movements(); track movement.id) { <div class="movement-row"><span class="movement-date">{{ movement.created_at | date:'dd/MM/yyyy HH:mm' }}</span><strong [class.negative]="movement.quantity < 0" [class.positive]="movement.quantity > 0">{{ movement.quantity > 0 ? '+' : '' }}{{ movement.quantity | number:'1.0-3' }}</strong><span class="movement-reason">{{ movement.reason }}</span>@if (canReadCosts()) { <span class="movement-value">@if (movement.movement_value !== null) { <strong>{{ movement.movement_value | currency:'BRL' }}</strong><small>{{ movement.unit_cost | currency:'BRL' }} / un.</small> } @else { <small>Custo histórico indisponível</small> }</span> }<small>Saldo <b>{{ movement.balance_after | number:'1.0-3' }}</b></small></div> } @empty { <p class="muted">Nenhuma movimentação registrada.</p> }</div></section>
        </section>
      </div>
    }
  `,
  styleUrl: './products.scss',
})
export class ProductsPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly live = inject(LiveUpdatesService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly auth = inject(AuthService);
  private readonly fb = inject(FormBuilder);
  readonly products = signal<Product[]>([]);
  readonly search = signal('');
  readonly onlyLow = signal(false);
  readonly modal = signal(false);
  readonly adjusting = signal<Product | null>(null);
  readonly detail = signal<ProductDetail | null>(null);
  readonly movements = signal<StockMovement[]>([]);
  readonly saving = signal(false);
  readonly editing = signal<Product | null>(null);
  readonly selectedFiles = signal<File[]>([]);
  readonly photoPreviews = signal<string[]>([]);
  readonly attributesText = signal('');
  readonly fitmentsText = signal('');
  readonly channelProvider = signal<'mercadolivre' | 'shopee'>('mercadolivre');
  canManageCatalog() { return canManageCatalog(this.auth.user()?.role); }
  canAdjustStock() { return canAdjustStock(this.auth.user()?.role); }
  canReadCosts() { return canReadCosts(this.auth.user()?.role); }
  readonly channelMetadata = signal<ProductChannelMetadata | null>(null);
  readonly categoryQuery = signal('');
  readonly selectedCategory = signal('');
  readonly channelTitle = signal('');
  readonly channelDescription = signal('');
  readonly channelPrice = signal(0);
  readonly listingType = signal('gold_special');
  readonly channelAttributes = signal<Record<string, string>>({});
  readonly selectedLogistics = signal<number[]>([]);
  readonly channelMessage = signal('');
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
    brand: [''], manufacturer: [''], manufacturer_part_number: [''], barcode: [''], category: [''],
    item_condition: ['new' as 'new' | 'used' | 'refurbished'], warranty_days: [null as number | null], origin_country: [''],
    weight_g: [null as number | null], package_length_cm: [null as number | null], package_width_cm: [null as number | null], package_height_cm: [null as number | null],
  });
  readonly adjustForm = this.fb.nonNullable.group({
    quantity: [0, [Validators.required]],
    reason: ['', [Validators.required, Validators.minLength(3)]],
  });
  ngOnInit() {
    this.load();
    this.live.changes$.pipe(debounceTime(250), takeUntilDestroyed(this.destroyRef)).subscribe(() => this.load());
  }
  load() {
    this.api.products().subscribe((v) => this.products.set(v));
    const detailId = this.detail()?.id;
    if (detailId) {
      this.api.productDetail(detailId).subscribe((full) => {
        if (this.detail()?.id === detailId) this.detail.set(full);
      });
      this.api.productMovements(detailId).subscribe((movements) => {
        if (this.detail()?.id === detailId) this.movements.set(movements);
      });
    }
  }
  openNew() {
    this.adjusting.set(null);
    this.editing.set(null);
    this.selectedFiles.set([]); this.photoPreviews.set([]); this.attributesText.set(''); this.fitmentsText.set('');
    this.productForm.reset({
      sku: '',
      name: '',
      description: '',
      sale_price: 0,
      cost_price: 0,
      current_stock: 0,
      minimum_stock: 0,
      brand: '', manufacturer: '', manufacturer_part_number: '', barcode: '', category: '', item_condition: 'new', warranty_days: null,
      origin_country: '', weight_g: null, package_length_cm: null, package_width_cm: null, package_height_cm: null,
    });
    this.modal.set(true);
  }
  openEdit(product: ProductDetail) {
    this.detail.set(null); this.adjusting.set(null); this.editing.set(product); this.selectedFiles.set([]); this.photoPreviews.set([]);
    this.attributesText.set(Object.entries(product.attributes || {}).map(([key, value]) => `${key}: ${value}`).join('\n'));
    this.fitmentsText.set((product.fitments || []).map((fit) => [fit.make, fit.model, fit.year_from || '', fit.year_to || '', fit.engine || ''].join(' | ')).join('\n'));
    this.productForm.reset({ sku: product.sku, name: product.name, description: product.description || '', sale_price: product.sale_price, cost_price: product.cost_price ?? 0, current_stock: product.current_stock, minimum_stock: product.minimum_stock, brand: product.brand || '', manufacturer: product.manufacturer || '', manufacturer_part_number: product.manufacturer_part_number || '', barcode: product.barcode || '', category: product.category || '', item_condition: product.item_condition, warranty_days: product.warranty_days, origin_country: product.origin_country || '', weight_g: product.weight_g, package_length_cm: product.package_length_cm, package_width_cm: product.package_width_cm, package_height_cm: product.package_height_cm });
    this.modal.set(true);
  }
  selectPhotos(event: Event) { const files = Array.from((event.target as HTMLInputElement).files || []); this.selectedFiles.set(files); this.photoPreviews.set(files.map((file) => URL.createObjectURL(file))); }
  uploadDetailPhotos(product: ProductDetail, event: Event) { const files = Array.from((event.target as HTMLInputElement).files || []); if (files.length) this.api.uploadProductImages(product.id, files).subscribe((updated) => { this.openDetails(updated); }); }
  removePhoto(product: ProductDetail, photo: ProductImage) { if (!confirm('Remover esta foto do cadastro?')) return; this.api.deleteProductImage(product.id, photo.id).subscribe((updated) => this.openDetails(updated)); }
  private parseAttributes(): Record<string, string> { return Object.fromEntries(this.attributesText().split('\n').map((line) => line.split(/:\s*/, 2)).filter(([key, value]) => key?.trim() && value?.trim()).map(([key, value]) => [key.trim(), value.trim()])); }
  private parseFitments(): ProductFitment[] { return this.fitmentsText().split('\n').map((line) => line.split('|').map((part) => part.trim())).filter((parts) => parts[0] && parts[1]).map(([make, model, from, to, engine]) => ({ make, model, year_from: Number(from) || null, year_to: Number(to) || null, engine: engine || null })); }
  private saveProductPayload() {
    if (this.productForm.invalid) return;
    const { current_stock, ...values } = this.productForm.getRawValue();
    const payload = { ...values, attributes: this.parseAttributes(), fitments: this.parseFitments() } as Partial<Product>;
    this.saving.set(true);
    const edited = this.editing();
    const request = edited ? this.api.updateProduct(edited.id, payload) : this.api.createProduct({ ...payload, current_stock });
    request.subscribe({ next: (product) => { const finish = () => { const files = this.selectedFiles(); const complete = () => { this.saving.set(false); this.modal.set(false); this.load(); this.openDetails(product); }; if (files.length) this.api.uploadProductImages(product.id, files).subscribe({ next: () => complete(), error: () => { this.saving.set(false); this.modal.set(false); this.openDetails(product); this.channelMessage.set('Peça salva, mas uma ou mais fotos não foram enviadas. Abra a peça e tente novamente.'); } }); else complete(); }; const difference = Number(current_stock) - Number(product.current_stock); if (edited && difference !== 0) this.api.adjustStock(product.id, difference, 'Ajuste de saldo pela edição da peça').subscribe({ next: () => finish(), error: () => { this.saving.set(false); this.modal.set(false); this.openDetails(product); this.channelMessage.set('A ficha foi salva, mas não foi possível registrar o ajuste de estoque. Revise o saldo.'); } }); else finish(); }, error: () => this.saving.set(false) });
  }
  selectProvider(provider: 'mercadolivre' | 'shopee') { this.channelProvider.set(provider); this.channelMetadata.set(null); this.channelMessage.set(''); this.selectedCategory.set(''); this.channelAttributes.set({}); this.loadChannelMetadata(); }
  hasExternalListing(listing: ProductDetail['listings'][number]) { return !!listing.external_item_id; }
  syncStatusLabel(status: string) { return ({ draft: 'Rascunho', published: 'Publicado', partial: 'Parcial', blocked: 'Bloqueado', error: 'Erro', imported: 'Importado' } as Record<string, string>)[status] || status; }
  loadChannelMetadata() { const product = this.detail(); if (!product) return; this.api.productChannelMetadata(this.channelProvider()).subscribe({ next: (meta) => this.channelMetadata.set(meta), error: () => this.channelMessage.set('Não foi possível carregar os requisitos. Verifique a conexão e tente novamente.') }); }
  searchCategories() { this.api.productChannelMetadata(this.channelProvider(), this.categoryQuery()).subscribe({ next: (meta) => this.channelMetadata.set(meta), error: () => this.channelMessage.set('Falha ao buscar categorias no canal.') }); }
  loadCategory(categoryId: string) { this.selectedCategory.set(categoryId); this.channelAttributes.set({}); this.selectedLogistics.set([]); if (!categoryId) return; const categories = this.channelMetadata()?.categories || []; this.api.productChannelMetadata(this.channelProvider(), '', categoryId).subscribe({ next: (meta) => { this.channelMetadata.set({ ...meta, categories }); this.channelTitle.set(this.detail()?.name || ''); this.channelDescription.set(this.detail()?.description || ''); this.channelPrice.set(this.detail()?.sale_price || 0); }, error: () => this.channelMessage.set('Não foi possível consultar os campos obrigatórios da categoria.') }); }
  setChannelAttribute(id: string, value: string) { this.channelAttributes.update((current) => ({ ...current, [id]: value })); }
  toggleLogistics(id: number, checked: boolean) { this.selectedLogistics.update((rows) => checked ? [...new Set([...rows, id])] : rows.filter((value) => value !== id)); }
  private channelDraft(): ProductChannelDraft { const meta = this.channelMetadata(); const attrs = Object.entries(this.channelAttributes()).filter(([, value]) => value).map(([id, value]) => { const field = meta?.attributes.find((row) => row.id === id); const option = field?.values?.find((row) => String(row.id || row.value_id || row.name) === value); return { id, ...(option?.id || option?.value_id ? { value_id: String(option.id || option.value_id) } : { value_name: option?.name || option?.original_value_name || value }) }; }); return { category_id: this.selectedCategory(), title: this.channelTitle(), family_name: meta?.user_product_seller ? this.channelTitle() : null, description: this.channelDescription(), price: this.channelPrice(), listing_type_id: this.listingType(), attributes: attrs, sale_terms: [], shipping: {}, logistic_info: this.selectedLogistics().map((id) => ({ logistic_id: id, enabled: true, is_free: false })) }; }
  saveChannelDraft(product: ProductDetail) { this.saving.set(true); this.api.saveProductChannelDraft(product.id, this.channelProvider(), this.channelDraft()).subscribe({ next: (updated) => { this.saving.set(false); this.detail.set(updated); this.channelMessage.set('Rascunho salvo. Nada foi enviado à plataforma.'); }, error: () => { this.saving.set(false); this.channelMessage.set('Não foi possível salvar o rascunho. Confira os campos e tente novamente.'); } }); }
  publishChannel(product: ProductDetail) { if (!confirm(`Confirma enviar ou atualizar este anúncio na ${this.channelProvider() === 'mercadolivre' ? 'Mercado Livre' : 'Shopee'}? Esta ação altera dados reais da conta conectada.`)) return; this.saving.set(true); this.api.saveProductChannelDraft(product.id, this.channelProvider(), this.channelDraft()).subscribe({ next: () => this.api.publishProductChannel(product.id, this.channelProvider()).subscribe({ next: (updated) => { this.saving.set(false); this.detail.set(updated); this.channelMessage.set('Sincronização concluída. Confira o status do anúncio e eventuais avisos abaixo.'); }, error: () => { this.saving.set(false); this.channelMessage.set('Falha ao publicar/sincronizar. Confira a conta e o anúncio na plataforma antes de repetir.'); } }), error: () => { this.saving.set(false); this.channelMessage.set('Não foi possível validar e salvar o rascunho.'); } }); }
  openAdjust(p: Product) {
    this.adjusting.set(p);
    this.adjustForm.reset({ quantity: 0, reason: '' });
    this.modal.set(true);
  }
  openDetails(p: Product) {
    this.detail.set(null);
    this.movements.set([]);
    this.channelMetadata.set(null); this.channelMessage.set('');
    this.api.productDetail(p.id).subscribe((v) => { this.detail.set(v); if (this.canManageCatalog()) this.loadChannelMetadata(); });
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
    this.saveProductPayload();
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
