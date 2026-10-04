import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../core/api.service';
import { MarketplaceConfig, MarketplaceStatus, ShopeeConfig, ShopeeStatus } from '../../core/models';
import { PageHeader } from '../../shared/page-header';

type Rules = { import_orders: boolean; automatic_stock: boolean; sync_documents: boolean };
type MlForm = Rules & { client_id: string; client_secret: string; redirect_uri: string; site_id: string };
type ShopeeForm = Rules & { partner_id: string; partner_key: string; shop_id: string; redirect_uri: string; region: string };

@Component({
  selector: 'app-integrations',
  imports: [FormsModule, PageHeader],
  templateUrl: './integrations.html',
  styleUrl: './integrations.scss',
})
export class IntegrationsPage implements OnInit {
  private readonly api = inject(ApiService);
  readonly mlStatus = signal<MarketplaceStatus | null>(null);
  readonly mlConfig = signal<MarketplaceConfig | null>(null);
  readonly mlSaving = signal(false);
  readonly mlConnecting = signal(false);
  readonly mlSyncing = signal(false);
  readonly mlMessage = signal('');
  readonly shopeeStatus = signal<ShopeeStatus | null>(null);
  readonly shopeeConfig = signal<ShopeeConfig | null>(null);
  readonly shopeeSaving = signal(false);
  readonly shopeeConnecting = signal(false);
  readonly shopeeMessage = signal('');

  mlForm: MlForm = { client_id: '', client_secret: '', redirect_uri: '', site_id: 'MLB', import_orders: true, automatic_stock: true, sync_documents: true };
  shopeeForm: ShopeeForm = { partner_id: '', partner_key: '', shop_id: '', redirect_uri: '', region: 'BR', import_orders: true, automatic_stock: true, sync_documents: true };

  ngOnInit() {
    const connectedReturn = new URLSearchParams(window.location.search).get('connected') === 'true';
    this.api.marketplaceStatus().subscribe((v) => {
      this.mlStatus.set(v);
      if (connectedReturn && v.connected) {
        window.history.replaceState({}, '', window.location.pathname);
        if (window.confirm('Conta do Mercado Livre conectada. Deseja sincronizar produtos, pedidos e documentos agora?')) {
          this.syncMercadoLivre();
        }
      }
    });
    this.api.marketplaceConfig().subscribe((v) => { this.mlConfig.set(v); this.mlForm = { ...this.mlForm, ...v, client_secret: '' }; });
    this.api.shopeeStatus().subscribe((v) => this.shopeeStatus.set(v));
    this.api.shopeeConfig().subscribe((v) => { this.shopeeConfig.set(v); this.shopeeForm = { ...this.shopeeForm, ...v, partner_key: '', shop_id: v.shop_id || '' }; });
  }

  saveMercadoLivre() {
    this.mlSaving.set(true); this.mlMessage.set('');
    this.api.saveMarketplaceConfig({ ...this.mlForm, client_secret: this.mlForm.client_secret || undefined }).subscribe({
      next: (v) => { this.mlConfig.set(v); this.mlForm = { ...this.mlForm, ...v, client_secret: '' }; this.mlStatus.update((s) => s ? { ...s, configured: true } : s); this.mlMessage.set('Configuração do Mercado Livre salva.'); this.mlSaving.set(false); },
      error: () => { this.mlMessage.set('Não foi possível salvar o Mercado Livre.'); this.mlSaving.set(false); },
    });
  }

  connectMercadoLivre() {
    this.mlConnecting.set(true);
    this.api.connectMarketplace().subscribe({ next: (v) => location.assign(v.authorization_url), error: () => this.mlConnecting.set(false) });
  }

  syncMercadoLivre() {
    this.mlSyncing.set(true); this.mlMessage.set('');
    this.api.syncMarketplace().subscribe({
      next: (v) => { this.mlMessage.set(v.message); this.mlSyncing.set(false); },
      error: (err) => { this.mlMessage.set(err?.error?.detail || 'Não foi possível iniciar a sincronização.'); this.mlSyncing.set(false); },
    });
  }

  saveShopee() {
    this.shopeeSaving.set(true); this.shopeeMessage.set('');
    this.api.saveShopeeConfig({ ...this.shopeeForm, partner_key: this.shopeeForm.partner_key || undefined, shop_id: this.shopeeForm.shop_id || undefined }).subscribe({
      next: (v) => { this.shopeeConfig.set(v); this.shopeeForm = { ...this.shopeeForm, ...v, partner_key: '', shop_id: v.shop_id || '' }; this.shopeeStatus.update((s) => s ? { ...s, configured: true } : s); this.shopeeMessage.set('Configuração da Shopee salva.'); this.shopeeSaving.set(false); },
      error: () => { this.shopeeMessage.set('Não foi possível salvar a Shopee.'); this.shopeeSaving.set(false); },
    });
  }

  connectShopee() {
    this.shopeeConnecting.set(true);
    this.api.connectShopee().subscribe({ next: (v) => location.assign(v.authorization_url), error: () => this.shopeeConnecting.set(false) });
  }
}
