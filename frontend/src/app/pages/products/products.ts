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
import { MoneyInputDirective } from '../../shared/money-input.directive';

@Component({
  selector: 'app-products',
  imports: [CurrencyPipe, DatePipe, DecimalPipe, MoneyInputDirective, ReactiveFormsModule, PageHeader],
  templateUrl: './products.html',
  styleUrl: './products.scss',
})
export class ProductsPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly live = inject(LiveUpdatesService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly auth = inject(AuthService);
  private readonly fb = inject(FormBuilder);
  readonly products = signal<Product[]>([]);
  readonly stockTab = signal<'product' | 'warehouse'>('product');
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
  readonly channelPriceInvalid = signal(false);
  readonly listingType = signal('gold_special');
  readonly channelAttributes = signal<Record<string, string>>({});
  readonly selectedLogistics = signal<number[]>([]);
  readonly channelMessage = signal('');
  isLowStock(product: Product): boolean {
    return product.stock_type === 'product' && Number(product.current_stock) < Number(product.minimum_stock);
  }

  readonly filtered = computed(() => {
    const q = this.search().toLowerCase();
    return this.products().filter(
      (p) =>
        p.stock_type === this.stockTab() &&
        (!q || p.name.toLowerCase().includes(q) || p.sku.toLowerCase().includes(q)) &&
        (this.stockTab() !== 'product' || !this.onlyLow() || this.isLowStock(p)),
    );
  });
  readonly productForm = this.fb.nonNullable.group({
    sku: ['', Validators.required],
    stock_type: ['product' as 'product' | 'warehouse'],
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
  setStockTab(value: 'product' | 'warehouse') { this.stockTab.set(value); this.onlyLow.set(false); this.load(); }
  load() {
    this.api.products('', false, this.stockTab()).subscribe((v) => this.products.set(v));
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
      stock_type: this.stockTab(),
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
    this.productForm.reset({ sku: product.sku, stock_type: product.stock_type, name: product.name, description: product.description || '', sale_price: product.sale_price, cost_price: product.cost_price ?? 0, current_stock: product.current_stock, minimum_stock: product.minimum_stock, brand: product.brand || '', manufacturer: product.manufacturer || '', manufacturer_part_number: product.manufacturer_part_number || '', barcode: product.barcode || '', category: product.category || '', item_condition: product.item_condition, warranty_days: product.warranty_days, origin_country: product.origin_country || '', weight_g: product.weight_g, package_length_cm: product.package_length_cm, package_width_cm: product.package_width_cm, package_height_cm: product.package_height_cm });
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
